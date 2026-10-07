import base64
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

import jwt
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .authentication import jwt_secret
from .notifications import dispatch_alerts, notification_channels, send_notification
from .models import Alert, BudgetSetting, Meter, NewsArticle, PaymentEvent, Recharge, RelayCommand, Sector, Telemetry
from .serializers import (
    AdminLoginSerializer,
    ManualTokenApplySerializer,
    ManualTokenIssueSerializer,
    NewsArticleSerializer,
    PaymentInitiateSerializer,
    RelayCommandRequestSerializer,
    SubscriberLoginSerializer,
    SubscriberProfileSerializer,
    TelemetryPayloadSerializer,
    TokenRefreshSerializer,
)
from .services import (
    CDF_PER_KWH,
    CDF_PER_USD,
    USD_PER_KWH,
    apply_recharge,
    apply_relay_rule,
    assistant_answer,
    assistant_system_prompt,
    CREDIT_THRESHOLDS,
    check_heartbeats,
    complete_pending_recharge,
    credit_status,
    deepseek_chat,
    detect_anomalies,
    estimate_hours,
    generate_receipt_pdf,
    issue_manual_token,
    notify_telemetry_refresh,
    parse_manual_token,
    payment_covers_recharge,
    pending_credits,
    pending_recharge_by_reference,
    verify_signature,
)

ACCESS_TOKEN_TTL = timedelta(hours=8)
REFRESH_TOKEN_TTL = timedelta(days=7)

# Endpoints sandbox DOCUMENTÉS (PawaPay / Flutterwave) — jamais inventés, contrats réels.
PAWAPAY_SANDBOX_DEPOSITS = "https://api.sandbox.pawapay.io/v2/deposits"
PAWAPAY_RDC_PROVIDERS = ["AIRTEL_COD", "ORANGE_COD", "VODACOM_MPESA_COD"]
# Libellés réseau affichables (mobile money RDC). Le code ci-dessus est le "correspondent" PawaPay.
PAWAPAY_PROVIDER_LABELS = {
    "AIRTEL_COD": "Airtel",
    "ORANGE_COD": "Orange",
    "VODACOM_MPESA_COD": "Vodacom",
}
FLUTTERWAVE_CHECKOUT = "https://api.flutterwave.com/v3/payments"
FLUTTERWAVE_VERIFY = "https://api.flutterwave.com/v3/transactions/{id}/verify"


def _http_post_json(url: str, headers: dict, payload: dict, timeout: int = 15) -> tuple[int, dict]:
    """POST JSON sans dépendance externe (urllib). Retourne (status, body)."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body


def _http_get_json(url: str, headers: dict, timeout: int = 15) -> tuple[int, dict]:
    """GET JSON sans dépendance externe (urllib). Retourne (status, body)."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body


def _normalize_msisdn_for_cod(raw: str) -> str:
    """Normalise un numéro DRC vers le format international E.164 sans '+' attendu par PawaPay.

    PawaPay attend un MSISDN au format international sans le '+', ex. '243993456789'.
    Accepte '0993...', '993...', '+243993...', '243993...'.
    """
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("243"):
        return digits
    if digits.startswith("00"):
        return "243" + digits[4:]
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 9:
        return "243" + digits
    return digits


def _valid_cod_msisdn(normalized: str) -> bool:
    """Un MSISDN DRC valide = '243' + 9 chiffres (Airtel/Orange/Vodacom mobiles RDC)."""
    return bool(re.fullmatch(r"243\d{9}", normalized))


def subscriber_meter_for(user):
    return Meter.objects.select_related("sector").filter(owner_open_id=user.username).first()


def _issue_token_pair(user, meter) -> tuple[str, str]:
    now = timezone.now()
    access = jwt.encode(
        {"sub": user.username, "meter_id": meter.meter_id, "domain_role": "abonné", "jti": str(uuid.uuid4()), "iat": now, "exp": now + ACCESS_TOKEN_TTL},
        jwt_secret(), algorithm="HS256",
    )
    refresh = jwt.encode(
        {"sub": user.username, "typ": "refresh", "jti": str(uuid.uuid4()), "iat": now, "exp": now + REFRESH_TOKEN_TTL},
        jwt_secret(), algorithm="HS256",
    )
    return access, refresh


REFRESH_COOKIE_NAME = "vse_refresh"


def _subscriber_payload(meter) -> dict:
    """Profil abonné renvoyé au client (identité + coordonnées de contact)."""
    return {
        "first_name": meter.subscriber_first_name,
        "last_name": meter.subscriber_last_name,
        "meter_id": meter.meter_id,
        "email": meter.subscriber_email,
        "phone": meter.subscriber_phone,
        "address": meter.subscriber_address,
    }


def _set_refresh_cookie(response, token: str) -> None:
    """Cookie HTTP-only persistant (refresh token) → reconnexion automatique sans ressaisie."""
    response.set_cookie(
        REFRESH_COOKIE_NAME, token,
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
        httponly=True, secure=not settings.DEBUG, samesite="Lax", path="/",
    )


def _clear_refresh_cookie(response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")


class TelemetryIngestView(APIView):
    """Ingestion compteur -> backend : HTTPS POST signé (HMAC-SHA256), toutes les 5 s."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        # Signature HMAC d'abord : vérifiée sur le payload BRUT reçu (ce que le compteur a signé),
        # jamais sur la version re-sérialisée par DRF. Un appelant non authentifié n'obtient
        # ainsi aucun détail de validation.
        if not verify_signature(request.data, request.headers.get("X-Virunga-Signature", "")):
            return Response({"accepted": False, "error": "Signature HMAC invalide."}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = TelemetryPayloadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"accepted": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        payload = serializer.validated_data
        reported_relay = RelayCommand.ON if payload["relay_status"] else RelayCommand.OFF
        try:
            with transaction.atomic():
                meter = Meter.objects.select_for_update().get(meter_id=payload["meter_id"])
                # Unicité du message_id : le champ est unique en base (rejet 409).
                telemetry = Telemetry.objects.create(
                    meter=meter,
                    message_id=str(payload["message_id"]),
                    applied_at=payload["device_timestamp"],
                    voltage_v=payload["voltage"],
                    current_a=payload["current"],
                    power_w=payload["power"],
                    energy_kwh=payload["energy_consumed"],
                    balance_kwh=payload["balance_kwh"],
                    relay_status=reported_relay,
                    signal_gsm=payload["signal_strength"],
                )
                # Le compteur rapporte son solde local ; on y ajoute les recharges appliquées
                # côté serveur qu'il n'a pas encore confirmées (sinon elles seraient écrasées ici).
                credits = pending_credits(meter, payload.get("credit_acks") or [])
                credit_kwh = sum((recharge.energy_kwh for recharge in credits), Decimal("0"))
                meter.voltage_v = payload["voltage"]
                meter.current_a = payload["current"]
                meter.power_w = payload["power"]
                meter.energy_kwh = payload["energy_consumed"]
                meter.balance_kwh = Decimal(str(payload["balance_kwh"])) + credit_kwh
                meter.signal_gsm = payload["signal_strength"]
                meter.device_status = payload["device_status"]
                meter.firmware_version = payload["firmware_version"]
                meter.save()
                # Coupure / rétablissement automatique selon le solde et la commande de l'abonné
                apply_relay_rule(meter)
                pending_command = meter.relay_commands.filter(status=RelayCommand.PENDING).first()
                if pending_command and pending_command.requested_state == reported_relay:
                    pending_command.status = RelayCommand.APPLIED
                    pending_command.acknowledged_at = timezone.now()
                    pending_command.save(update_fields=["status", "acknowledged_at"])
                    pending_command = None
                # Détection d'anomalies sur les données reçues
                new_alerts = detect_anomalies(meter, payload)
        except Meter.DoesNotExist:
            return Response({"accepted": False, "error": "Compteur inconnu."}, status=status.HTTP_404_NOT_FOUND)
        except IntegrityError:
            return Response({"accepted": False, "error": "message_id déjà traité."}, status=status.HTTP_409_CONFLICT)
        except OperationalError:
            # SQLite en dev : écriture concurrente (base verrouillée) -> le compteur réessaie
            return Response({"accepted": False, "error": "Base temporairement verrouillée, réessayez."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        check_heartbeats()
        notify_telemetry_refresh(meter)
        # Alertes de crédit poussées vers l'abonné (e-mail, SMS, WhatsApp), hors transaction.
        dispatch_alerts(meter, new_alerts)

        # Ordre renvoyé au compteur dès que son relais diffère de l'état voulu.
        relay_command = None
        if meter.relay_status != reported_relay:
            if pending_command and pending_command.requested_state == meter.relay_status:
                relay_command = {"command_id": str(pending_command.id), "desired_state": meter.relay_status, "reason": "commande_abonne"}
            else:
                relay_command = {"command_id": f"auto-{telemetry.id}", "desired_state": meter.relay_status, "reason": "regle_solde"}
        return Response({
            "accepted": True,
            "message_id": str(telemetry.message_id),
            "relay_command": relay_command,
            # Crédits à intégrer au solde local, à accuser ensuite par `credit_acks` (une fois par id).
            "credits": [{"id": recharge.id, "energy_kwh": float(recharge.energy_kwh)} for recharge in credits],
            "credit_kwh": float(credit_kwh),
            "balance_kwh": float(meter.balance_kwh),
        }, status=status.HTTP_202_ACCEPTED)


class SubscriberLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SubscriberLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        meter = Meter.objects.select_related("sector").filter(subscriber_code=data["meter_code"]).first()
        if not meter:
            return Response({"detail": "Aucun abonnement ne correspond à ce code compteur."}, status=status.HTTP_401_UNAUTHORIZED)
        valid_identity = (
            meter.subscriber_first_name.strip().casefold() == data["first_name"].strip().casefold()
            and meter.subscriber_last_name.strip().casefold() == data["last_name"].strip().casefold()
        )
        if not valid_identity:
            return Response({"detail": "Les informations d'identité ne correspondent pas à cet abonnement."}, status=status.HTTP_401_UNAUTHORIZED)

        user_model = get_user_model()
        username = f"meter-{meter.meter_id}"[:150]
        user, _ = user_model.objects.get_or_create(username=username)
        user.first_name = meter.subscriber_first_name
        user.last_name = meter.subscriber_last_name
        user.set_unusable_password()
        user.save(update_fields=["first_name", "last_name", "password"])
        if meter.owner_open_id != user.username:
            meter.owner_open_id = user.username
            meter.save(update_fields=["owner_open_id"])

        # Enrichissement du profil abonné à la connexion (coordonnées optionnelles).
        contact_fields = []
        if data.get("email"):
            meter.subscriber_email = data["email"]
            contact_fields.append("subscriber_email")
        if data.get("phone"):
            meter.subscriber_phone = data["phone"]
            contact_fields.append("subscriber_phone")
        if data.get("address"):
            meter.subscriber_address = data["address"]
            contact_fields.append("subscriber_address")
        if contact_fields:
            meter.save(update_fields=contact_fields)

        access_token, refresh_token = _issue_token_pair(user, meter)
        response = Response({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": int(ACCESS_TOKEN_TTL.total_seconds()),
            "subscriber": _subscriber_payload(meter),
        })
        _set_refresh_cookie(response, refresh_token)
        return response


class AdminLoginView(APIView):
    """Connexion administrateur : compte Django `is_staff` (créé par `manage.py createsuperuser`)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "admin_login"

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, username=serializer.validated_data["username"], password=serializer.validated_data["password"])
        # Même réponse pour un mot de passe faux et un compte non administrateur.
        if user is None or not user.is_staff:
            return Response({"detail": "Identifiants administrateur invalides."}, status=status.HTTP_401_UNAUTHORIZED)
        now = timezone.now()
        access_token = jwt.encode(
            {"sub": user.username, "domain_role": "administrateur", "jti": str(uuid.uuid4()), "iat": now, "exp": now + ACCESS_TOKEN_TTL},
            jwt_secret(), algorithm="HS256",
        )
        return Response({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": int(ACCESS_TOKEN_TTL.total_seconds()),
            "admin": {"username": user.username},
        })


class TokenRefreshView(APIView):
    """Rafraîchit la paire access + refresh (rotation du refresh token)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Le refresh token peut venir du corps OU du cookie persistant (reconnexion automatique).
        token = serializer.validated_data.get("refresh_token", "") or request.COOKIES.get(REFRESH_COOKIE_NAME, "")
        if not token:
            return Response({"detail": "Aucun refresh token fourni (corps ou cookie)."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            payload = jwt.decode(token, jwt_secret(), algorithms=["HS256"])
        except jwt.PyJWTError:
            return Response({"detail": "Refresh token invalide ou expiré."}, status=status.HTTP_401_UNAUTHORIZED)
        if payload.get("typ") != "refresh":
            return Response({"detail": "Token non autorisé pour le rafraîchissement."}, status=status.HTTP_401_UNAUTHORIZED)
        meter = Meter.objects.filter(owner_open_id=payload.get("sub", "")).first()
        if not meter:
            return Response({"detail": "Compteur associé introuvable."}, status=status.HTTP_401_UNAUTHORIZED)
        user_model = get_user_model()
        user = user_model.objects.filter(username=payload.get("sub", "")).first()
        if not user:
            return Response({"detail": "Utilisateur introuvable."}, status=status.HTTP_401_UNAUTHORIZED)
        access_token, refresh_token = _issue_token_pair(user, meter)
        response = Response({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": int(ACCESS_TOKEN_TTL.total_seconds()),
            "subscriber": _subscriber_payload(meter),
        })
        _set_refresh_cookie(response, refresh_token)
        return response


class SubscriberLogoutView(APIView):
    """Déconnexion : révoque la session locale et efface le cookie persistant."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        response = Response({"logged_out": True})
        _clear_refresh_cookie(response)
        return response


class ManualTokenIssueView(APIView):
    """Scénario B — un revendeur émet un token signé (réservé à l'admin)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response({"detail": "Accès administrateur requis."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ManualTokenIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meter = Meter.objects.filter(meter_id=serializer.validated_data["meter_id"]).first()
        if not meter:
            return Response({"detail": "Compteur inconnu."}, status=status.HTTP_404_NOT_FOUND)
        token, payload = issue_manual_token(meter, serializer.validated_data["energy_kwh"])
        return Response({"token": token, "payload": payload, "message": "Token à transmettre au client pour saisie au clavier du compteur."}, status=status.HTTP_201_CREATED)


class ManualTokenApplyView(APIView):
    """Scénario B — saisie du token (simulation du clavier du compteur).

    Le compteur physique vérifie la signature HMAC localement (sans internet),
    applique le crédit immédiatement, puis envoie l'événement au backend qui
    réconcilie le solde officiel (source=SAISIE_MANUELLE). Ici, le backend joue
    ce rôle : vérification HMAC + anti-rejeu de séquence + application.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ManualTokenApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meter = subscriber_meter_for(request.user)
        if not meter:
            return Response({"detail": "Aucun compteur n'est associé à cet abonné."}, status=status.HTTP_403_FORBIDDEN)

        payload, error = parse_manual_token(serializer.validated_data["token"])
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
        if payload["meter_id"] != meter.meter_id:
            return Response({"detail": "Ce token ne correspond pas à votre compteur."}, status=status.HTTP_409_CONFLICT)

        with transaction.atomic():
            locked_meter = Meter.objects.select_for_update().get(pk=meter.pk)
            record = locked_meter.manual_tokens.filter(sequence=payload["sequence"]).first()
            if record is None:
                return Response({"detail": "Token inconnu en base (séquence non émise)."}, status=status.HTTP_409_CONFLICT)
            if record.used_at is not None:
                return Response({"detail": "Token déjà utilisé (anti-rejeu)."}, status=status.HTTP_409_CONFLICT)
            record.used_at = timezone.now()
            record.save(update_fields=["used_at"])
            # Même transaction que le marquage : un échec du crédit ne « brûle » pas le token.
            # L'énergie créditée est celle enregistrée à l'émission, pas celle relue du token.
            recharge = apply_recharge(locked_meter, Recharge.SOURCE_CHOICES[1][0], record.energy_kwh, record.used_at, provider_reference=f"token-seq-{record.sequence}", notify=False)

        notify_telemetry_refresh(meter)
        meter.refresh_from_db()
        return Response({
            "applied": True,
            "recharge_id": recharge.id,
            "source": recharge.source,
            "energy_kwh": float(recharge.energy_kwh),
            "balance_kwh": float(meter.balance_kwh),
            "applied_at": recharge.applied_at.isoformat(),
            "synced_at": recharge.synced_at.isoformat(),
            "relay_status": meter.relay_status,
        }, status=status.HTTP_202_ACCEPTED)


class PaymentInitiateView(APIView):
    """Scénario A — initiation d'un paiement en ligne (sandbox documentée).

    Aucune clé sandbox n'étant fournie, l'appel réel est tenté uniquement si la
    configuration existe ; sinon une erreur explicite est renvoyée (jamais de
    succès simulé).
    """

    permission_classes = [IsAuthenticated]

    def _fail(self, recharge, detail: str, http_status: int) -> Response:
        recharge.status = Recharge.STATUS_FAILED
        recharge.save(update_fields=["status"])
        return Response({"detail": detail}, status=http_status)

    def post(self, request):
        serializer = PaymentInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meter = subscriber_meter_for(request.user)
        if not meter:
            return Response({"detail": "Aucun compteur n'est associé à cet abonné."}, status=status.HTTP_403_FORBIDDEN)

        provider = serializer.validated_data["provider"]
        amount_cdf = serializer.validated_data["amount_cdf"]
        # Arrondi vers le bas : l'énergie créditée ne dépasse jamais le montant payé.
        energy_kwh = (Decimal(amount_cdf) / CDF_PER_KWH).quantize(Decimal("0.001"), rounding=ROUND_DOWN)
        # PawaPay impose un depositId au format UUID ; Flutterwave accepte une référence libre.
        reference = str(uuid.uuid4()) if provider == "pawapay" else f"VSE-{meter.meter_id}-{uuid.uuid4().hex[:12]}"

        # Recharge en attente, traçable par référence (sera complétée après confirmation du prestataire)
        recharge = Recharge.objects.create(
            meter=meter, source=Recharge.SOURCE_CHOICES[0][0], energy_kwh=energy_kwh,
            status=Recharge.STATUS_PENDING, applied_at=None, provider_reference=reference,
        )

        if provider == "pawapay":
            token = os.getenv("PAWAPAY_SANDBOX_TOKEN", "")
            if not token:
                return self._fail(recharge, "PawaPay non configuré : aucun token sandbox fourni. Aucun paiement n'a été débité.", status.HTTP_503_SERVICE_UNAVAILABLE)
            phone_raw = serializer.validated_data.get("phone_number", "")
            network = serializer.validated_data.get("network") or PAWAPAY_RDC_PROVIDERS[0]
            phone = _normalize_msisdn_for_cod(phone_raw)
            if not phone or not _valid_cod_msisdn(phone):
                return self._fail(recharge, "Numéro de téléphone mobile money invalide (format DRC attendu : 243 + 9 chiffres).", status.HTTP_400_BAD_REQUEST)
            # Contrat réel PawaPay V2 : payer.accountDetails.{phoneNumber, provider} (voir docs.pawapay.io/v2)
            try:
                status_code, body = _http_post_json(
                    PAWAPAY_SANDBOX_DEPOSITS,
                    {"Authorization": f"Bearer {token}"},
                    {
                        "depositId": reference,
                        "amount": str(amount_cdf),
                        "currency": "CDF",
                        "payer": {
                            "type": "MMO",
                            "accountDetails": {"phoneNumber": phone, "provider": network},
                        },
                        "statementDescription": "Virunga Smart Energy - recharge",
                    },
                )
            except Exception as exc:  # pragma: no cover - dépend du réseau
                return self._fail(recharge, f"Échec de l'appel PawaPay sandbox : {exc}", status.HTTP_502_BAD_GATEWAY)
            deposit_status = str(body.get("status") or "") if isinstance(body, dict) else ""
            # Le dépôt est accepté pour traitement : l'abonné autorise ensuite sur SON téléphone (USSD).
            if deposit_status.upper() not in ("ACCEPTED", "SUBMITTED", "COMPLETED"):
                # Refusé d'emblée : la recharge ne doit pas rester indéfiniment en attente.
                return self._fail(recharge, "Le dépôt n'a pas été accepté par PawaPay. Aucun paiement n'a été débité.", status.HTTP_502_BAD_GATEWAY)
            return Response({
                "provider": "pawapay", "deposit_id": reference, "http_status": status_code,
                "status": deposit_status, "accepted": True,
                "detail": "Demande de dépôt mobile money envoyée. Autorisez le paiement sur VOTRE téléphone (prompt USSD de l'opérateur).",
            }, status=status.HTTP_202_ACCEPTED)

        secret = os.getenv("FLUTTERWAVE_SECRET_KEY", "")
        if not secret:
            return self._fail(recharge, "Flutterwave non configuré : aucune clé sandbox fournie. Aucun paiement n'a été débité.", status.HTTP_503_SERVICE_UNAVAILABLE)
        amount_usd = Decimal(amount_cdf) / CDF_PER_USD  # taux officiel 1 USD = 2500 FC
        customer = {
            "email": meter.subscriber_email or os.getenv("FLUTTERWAVE_CUSTOMER_EMAIL", f"{meter.meter_id}@virunga-smart-energy.demo"),
            "name": f"{meter.subscriber_first_name} {meter.subscriber_last_name}".strip(),
        }
        if serializer.validated_data.get("phone_number"):
            customer["phonenumber"] = serializer.validated_data["phone_number"]
        try:
            status_code, body = _http_post_json(
                FLUTTERWAVE_CHECKOUT,
                {"Authorization": f"Bearer {secret}"},
                {
                    "tx_ref": reference,
                    "amount": f"{amount_usd:.2f}",
                    "currency": "USD",
                    "redirect_url": os.getenv("FLUTTERWAVE_REDIRECT_URL", "") or request.build_absolute_uri("/api/payments/flutterwave/verify/"),
                    "customer": customer,
                },
            )
        except Exception as exc:  # pragma: no cover - dépend du réseau
            return self._fail(recharge, f"Échec de l'appel Flutterwave sandbox : {exc}", status.HTTP_502_BAD_GATEWAY)
        data = body.get("data") if isinstance(body, dict) else None
        link = data.get("link") if isinstance(data, dict) else None
        if not link:
            return self._fail(recharge, "Flutterwave n'a pas fourni de page de paiement. Aucun paiement n'a été débité.", status.HTTP_502_BAD_GATEWAY)
        return Response({"provider": "flutterwave", "tx_ref": reference, "http_status": status_code, "status": body.get("status"), "link": link, "detail": "Complétez le paiement sur la page sécurisée Flutterwave ; le crédit sera ajouté après confirmation."}, status=status.HTTP_202_ACCEPTED)


class FlutterwaveWebhookView(APIView):
    """Webhook Flutterwave signé : vérification, idempotence, traçabilité."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        configured_hash = os.getenv("FLW_SECRET_HASH", "")
        provided_hash = request.headers.get("verif-hash", "")
        if not configured_hash or not provided_hash or not hmac.compare_digest(configured_hash.encode(), provided_hash.encode()):
            return Response({"received": False, "error": "Signature webhook invalide."}, status=status.HTTP_401_UNAUTHORIZED)

        body = request.data if isinstance(request.data, dict) else {}
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        event_id = str(body.get("webhook_id") or data.get("id") or "")
        if not event_id:
            return Response({"received": False, "error": "Identifiant d'événement manquant."}, status=status.HTTP_400_BAD_REQUEST)

        # Idempotence : un même événement est rejoué sans insertion multiple
        PaymentEvent.objects.update_or_create(
            event_id=f"flutterwave:{event_id}",
            defaults={"provider": "FLUTTERWAVE", "status": str(data.get("status") or body.get("event") or "RECEIVED"), "payload": body},
        )

        tx_ref = str(data.get("tx_ref") or "")
        if tx_ref and str(data.get("status") or "").lower() == "successful":
            recharge = pending_recharge_by_reference(tx_ref)
            # Crédit uniquement si le montant et la devise confirmés couvrent la recharge.
            if recharge is not None and payment_covers_recharge(recharge, data.get("amount"), data.get("currency")):
                complete_pending_recharge(recharge)
        return Response({"received": True}, status=status.HTTP_200_OK)


class FlutterwaveRedirectView(APIView):
    """Retour de la page hébergée Flutterwave (redirect_url) : vérifie via l'API Flutterwave
    et complète la recharge en attente. Contrat réel : GET /v3/transactions/{id}/verify.
    Permet à la recharge carte Visa de se compléter SANS webhook externe (utile en local).

    Les paramètres de l'URL de retour sont contrôlés par le navigateur de l'abonné : ils ne
    prouvent rien. Seule la réponse de l'API Flutterwave (appel serveur à serveur) crédite."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def _html(self, message: str, ok: bool) -> HttpResponse:
        color = "#059669" if ok else "#dc2626"
        title = "Paiement confirmé ✅" if ok else "Paiement non validé"
        return HttpResponse(
            f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Paiement — Virunga Smart Energy</title></head>"
            f"<body style='font-family:system-ui;text-align:center;padding:40px;background:#f8fafc'>"
            f"<div style='max-width:480px;margin:auto;background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:28px'>"
            f"<h2 style='color:{color}'>{title}</h2>"
            f"<p>{message}</p>"
            f"<a href='/' style='display:inline-block;margin-top:16px;background:#059669;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none'>Retour à mon espace abonné</a>"
            f"</div></body></html>"
        )

    def get(self, request):
        tx_ref = str(request.query_params.get("tx_ref", ""))
        transaction_id = str(request.query_params.get("transaction_id", ""))
        if not tx_ref:
            return self._html("Référence de transaction manquante : revenez à votre espace et réessayez.", False)

        recharge = pending_recharge_by_reference(tx_ref)
        if recharge is None:
            return self._html("Aucune recharge en attente pour cette référence.", False)

        secret = os.getenv("FLUTTERWAVE_SECRET_KEY", "")
        if not secret or not transaction_id.isdigit():
            return self._html("Le paiement n'a pas pu être vérifié auprès de Flutterwave. Aucun crédit n'a été ajouté.", False)
        try:
            _, body = _http_get_json(
                FLUTTERWAVE_VERIFY.format(id=transaction_id),
                {"Authorization": f"Bearer {secret}"},
            )
        except Exception:  # pragma: no cover - dépend du réseau
            return self._html("Flutterwave est momentanément injoignable. Aucun crédit n'a été ajouté ; réessayez dans un instant.", False)
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            data = {}
        verified = (
            str(data.get("status", "")).lower() == "successful"
            and str(data.get("tx_ref", "")) == tx_ref
            and payment_covers_recharge(recharge, data.get("amount"), data.get("currency"))
        )
        if verified:
            complete_pending_recharge(recharge)
            recharge.refresh_from_db()
            return self._html(f"Votre recharge de {float(recharge.energy_kwh)} kWh a été appliquée. Nouveau solde : {float(recharge.meter.balance_kwh)} kWh.", True)
        return self._html("Le paiement n'a pas été confirmé par Flutterwave. Aucun crédit n'a été ajouté.", False)


def _pawapay_digest_ok(request) -> bool:
    """Vérifie l'intégrité (Content-Digest) d'un callback PawaPay si la vérification est activée.

    La vérification RFC-9421 (signature asymétrique) reste optionnelle/en aval ; ici on valide
    que le corps reçu n'a pas été altéré, uniquement si PAWAPAY_VERIFY_CALLBACK=true.
    """
    if os.getenv("PAWAPAY_VERIFY_CALLBACK") != "true":
        return True
    header = request.META.get("HTTP_CONTENT_DIGEST", "")
    if not header:
        return False
    match = re.fullmatch(r"sha-(512|256)=:(.*):", header.strip())
    if not match:
        return False
    algo, digest_b64 = match.group(1), match.group(2)
    body_bytes = request.body
    if algo == "512":
        digest = base64.b64encode(hashlib.sha512(body_bytes).digest())
    else:
        digest = base64.b64encode(hashlib.sha256(body_bytes).digest())
    return hmac.compare_digest(digest, digest_b64.encode("utf-8"))


def _pawapay_fetch_deposit(deposit_id: str) -> tuple[int, dict]:
    """Statut d'un dépôt lu directement chez PawaPay (GET /v2/deposits/{depositId}).

    C'est la seule source de vérité avant de créditer : le callback entrant n'est pas
    authentifié par un secret partagé, son contenu seul ne suffit donc pas.
    """
    token = os.getenv("PAWAPAY_SANDBOX_TOKEN", "")
    status_code, body = _http_get_json(f"{PAWAPAY_SANDBOX_DEPOSITS}/{deposit_id}", {"Authorization": f"Bearer {token}"})
    data = body.get("data", body) if isinstance(body, dict) else body
    if isinstance(data, list):
        data = data[0] if data else {}
    return status_code, data if isinstance(data, dict) else {}


def _settle_pawapay_deposit(recharge: Recharge, data: dict) -> str:
    """Applique à la recharge le statut confirmé par PawaPay. Retourne APPLIED, FAILED, MISMATCH ou PENDING."""
    deposit_status = str(data.get("status") or "").upper()
    if deposit_status in ("COMPLETED", "SUCCESSFUL"):
        same_deposit = str(data.get("depositId") or recharge.provider_reference) == recharge.provider_reference
        if not same_deposit or not payment_covers_recharge(recharge, data.get("amount") or data.get("depositedAmount"), data.get("currency")):
            return "MISMATCH"
        complete_pending_recharge(recharge)
        return "APPLIED"
    if deposit_status in ("FAILED", "REJECTED"):
        Recharge.objects.filter(pk=recharge.pk, status=Recharge.STATUS_PENDING).update(status=Recharge.STATUS_FAILED)
        return "FAILED"
    return "PENDING"


class PawaPayCallbackView(APIView):
    """Callback (webhook) PawaPay : réception du statut final d'un dépôt, idempotent.

    Le corps suit le format réel (docs.pawapay.io) : {depositId, status, customerMessage, ...}.
    Le callback ne fait que DÉCLENCHER une vérification : le statut et le montant sont relus
    chez PawaPay avant tout crédit. Retourne 200 dès que l'événement est enregistré.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not _pawapay_digest_ok(request):
            return Response({"received": False, "error": "Intégrité du callback invalide."}, status=status.HTTP_401_UNAUTHORIZED)

        body = request.data if isinstance(request.data, dict) else {}
        deposit_id = str(body.get("depositId") or "")
        if not deposit_id:
            return Response({"received": False, "error": "depositId manquant."}, status=status.HTTP_400_BAD_REQUEST)
        status_val = str(body.get("status") or "").upper()

        # Idempotence : un même depositId rejoué n'entre qu'une fois (pas de double crédit).
        PaymentEvent.objects.update_or_create(
            event_id=f"pawapay:{deposit_id}",
            defaults={"provider": "PAWAPAY", "status": status_val, "payload": body},
        )

        recharge = pending_recharge_by_reference(deposit_id)
        if recharge is None or not os.getenv("PAWAPAY_SANDBOX_TOKEN", ""):
            return Response({"received": True, "verified": False}, status=status.HTTP_200_OK)
        try:
            _, data = _pawapay_fetch_deposit(deposit_id)
        except Exception:  # pragma: no cover - dépend du réseau
            # PawaPay injoignable : la recharge reste en attente, le polling de statut la complétera.
            return Response({"received": True, "verified": False}, status=status.HTTP_200_OK)
        outcome = _settle_pawapay_deposit(recharge, data)
        return Response({"received": True, "verified": outcome != "PENDING", "outcome": outcome}, status=status.HTTP_200_OK)


class PawaPayDepositStatusView(APIView):
    """Statut d'un dépôt PawaPay — utile en local (sans exposer de callback) et pour la page d'attente.

    Interroge GET /v2/deposits/{depositId} (check-deposit-status) côté abonné authentifié.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, deposit_id: str):
        meter = subscriber_meter_for(request.user)
        if meter is None:
            return Response({"detail": "Aucun compteur n'est associé à cet abonné."}, status=status.HTTP_403_FORBIDDEN)
        recharge = Recharge.objects.filter(meter=meter, provider_reference=deposit_id).first()
        if recharge is None:
            return Response({"detail": "Dépôt introuvable pour cet abonné."}, status=status.HTTP_404_NOT_FOUND)

        result = {"deposit_id": deposit_id, "status": recharge.status}
        # Déjà soldée (par le callback, par exemple) : inutile de réinterroger PawaPay.
        if recharge.status == Recharge.STATUS_PENDING:
            if not os.getenv("PAWAPAY_SANDBOX_TOKEN", ""):
                return Response({"detail": "PawaPay non configuré : aucun token sandbox."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            try:
                status_code, data = _pawapay_fetch_deposit(deposit_id)
            except Exception as exc:  # pragma: no cover - dépend du réseau
                return Response({"detail": f"Échec de la vérification du statut PawaPay : {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
            outcome = _settle_pawapay_deposit(recharge, data)
            result.update({
                "http_status": status_code,
                "status": str(data.get("status") or "").upper(),
                "customer_message": data.get("customerMessage", ""),
                "provider_transaction_id": data.get("providerTransactionId", ""),
            })
            if outcome == "MISMATCH":
                result["failed"] = True
                result["detail"] = "Le montant confirmé par PawaPay ne correspond pas à la recharge demandée. Aucun crédit n'a été ajouté ; contactez le support."
            recharge.refresh_from_db()

        if recharge.status == Recharge.STATUS_APPLIED:
            meter.refresh_from_db()
            result.update({"applied": True, "recharge_id": recharge.id, "balance_kwh": float(meter.balance_kwh)})
        elif recharge.status == Recharge.STATUS_FAILED:
            result["failed"] = True
            result.setdefault("detail", "Paiement refusé par le réseau.")
        return Response(result)


class ReceiptView(APIView):
    """Téléchargement d'un reçu PDF réel après chaque recharge."""

    permission_classes = [IsAuthenticated]

    def get(self, request, recharge_id):
        try:
            recharge = Recharge.objects.select_related("meter__sector").get(id=recharge_id)
        except Recharge.DoesNotExist:
            return Response({"detail": "Recharge introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if not request.user.is_staff and recharge.meter.owner_open_id != request.user.username:
            return Response({"detail": "Cette recharge ne vous appartient pas."}, status=status.HTTP_403_FORBIDDEN)

        subscriber_name = f"{recharge.meter.subscriber_first_name} {recharge.meter.subscriber_last_name}".strip()
        pdf_bytes = generate_receipt_pdf(recharge, recharge.meter, subscriber_name)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="recu-{recharge.id}.pdf"'
        return response


class AssistantView(APIView):
    """Agent IA : utilise DeepSeek (si configuré) sur les données réelles, sinon moteur de règles."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        question = str(request.data.get("question", "")).strip()
        if len(question) < 2:
            return Response({"answer": "Veuillez préciser votre question."}, status=status.HTTP_400_BAD_REQUEST)
        meter = subscriber_meter_for(request.user)
        if not meter:
            return Response({"answer": "Aucun compteur réel n'est associé à votre compte. Le mode DEMO ne peut pas fournir une réponse personnalisée."})
        # LLM DeepSeek : uniquement si une clé est configurée et hors mode test
        # (les tests restent déterministes sur le moteur de règles).
        if settings.DEEPSEEK_API_KEY and os.getenv("DJANGO_TESTING") != "true":
            try:
                answer = deepseek_chat(
                    system_prompt=assistant_system_prompt(meter),
                    user_question=question,
                    api_key=settings.DEEPSEEK_API_KEY,
                    base_url=settings.DEEPSEEK_BASE_URL,
                    model=settings.DEEPSEEK_MODEL,
                    timeout=settings.DEEPSEEK_TIMEOUT,
                )
                if answer:
                    return Response({"answer": answer, "engine": "deepseek"})
            except Exception as exc:
                # Repli honnête sur le moteur de règles si l'API est indisponible.
                return Response({
                    "answer": assistant_answer(meter, question),
                    "engine": "rules",
                    "note": f"DeepSeek momentanément indisponible : {exc}",
                })
        return Response({"answer": assistant_answer(meter, question)})


class AdminOverviewView(APIView):
    """Statistiques d'exploitation en lecture seule — uniquement des données réelles."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_staff:
            return Response({"detail": "Accès administrateur requis."}, status=status.HTTP_403_FORBIDDEN)
        check_heartbeats()
        total = Meter.objects.count()
        online = Meter.objects.filter(device_status="ONLINE").count()
        low_balance = Meter.objects.filter(balance_kwh__lt=5).count()
        # Calcul réel par secteur (agrégé en base)
        sectors = Sector.objects.annotate(
            total=Count("meters"),
            online=Count("meters", filter=Q(meters__device_status="ONLINE")),
            offline=Count("meters", filter=Q(meters__device_status="OFFLINE")),
        ).order_by("name")
        sector_rows = [
            {"name": sector.name, "territory": sector.territory, "online": sector.online, "offline": sector.offline, "total": sector.total}
            for sector in sectors
        ]
        open_alerts = Alert.objects.filter(acknowledged_at__isnull=True).count()
        return Response({
            "totalMeters": total,
            "onlineMeters": online,
            "lowBalanceMeters": low_balance,
            "sectors": sector_rows,
            "openAlerts": open_alerts,
        })


DAILY_PERIODS = [
    ("Nuit", range(0, 6)),
    ("Matin", range(6, 12)),
    ("Après-midi", range(12, 18)),
    ("Soirée", range(18, 24)),
]

WEEKDAY_LABELS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def daily_consumption_breakdown(hourly_entries):
    """Répartit la consommation horaire en 4 périodes de la journée.

    Les données proviennent des télémétries persistées (aucune valeur inventée) :
    chaque entrée horaire est affectée à sa période selon son heure.
    """
    totals = {name: 0.0 for name, _ in DAILY_PERIODS}
    for entry in hourly_entries:
        hour = int(entry.get("label", "00:00")[:2])
        for name, hours in DAILY_PERIODS:
            if hour in hours:
                totals[name] += float(entry.get("kwh", 0.0))
                break
    return [{"label": name, "kwh": round(value, 3)} for name, value in totals.items()]


def weekly_consumption_breakdown(telemetry_rows, reference=None):
    """Consommation par jour calendaire sur les 7 derniers jours.

    L'énergie cumulée du compteur ne fait qu'augmenter : la consommation d'un
    jour = énergie au dernier relevé du jour − énergie au premier relevé du
    jour. Les jours sans relevé sont renvoyés à 0 kWh (aucune donnée inventée).
    """
    reference = reference or timezone.now()
    by_day = {}
    for row in telemetry_rows:
        key = row.applied_at.strftime("%Y-%m-%d")
        energy = float(row.energy_kwh)
        low, high = by_day.get(key, (None, None))
        by_day[key] = (
            energy if low is None else min(low, energy),
            energy if high is None else max(high, energy),
        )
    breakdown = []
    for index in range(6, -1, -1):
        day = (reference - timedelta(days=index)).date()
        key = day.strftime("%Y-%m-%d")
        low, high = by_day.get(key, (None, None))
        kwh = 0.0 if low is None else round(max(high - low, 0.0), 3)
        breakdown.append({"label": WEEKDAY_LABELS[day.weekday()], "date": key, "kwh": kwh})
    return breakdown


class BudgetView(APIView):
    """Lecture et mise à jour du plafond de consommation (mode budget)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        meter = subscriber_meter_for(request.user)
        if not meter:
            return Response({"detail": "Aucun compteur n'est associé à cet abonné."}, status=status.HTTP_403_FORBIDDEN)
        budget = getattr(meter, "budget", None)
        meter.refresh_from_db()
        return Response({
            "limit_kwh": float(budget.limit_kwh) if budget else 0,
            "warning_percentage": budget.warning_percentage if budget else 80,
            "balance_kwh": float(meter.balance_kwh),
        })

    def post(self, request):
        meter = subscriber_meter_for(request.user)
        if not meter:
            return Response({"detail": "Aucun compteur n'est associé à cet abonné."}, status=status.HTTP_403_FORBIDDEN)
        try:
            limit = Decimal(str(request.data.get("limit_kwh", "")))
        except (TypeError, ValueError, ArithmeticError):
            return Response({"detail": "Plafond invalide."}, status=status.HTTP_400_BAD_REQUEST)
        if limit <= 0 or limit > 100000:
            return Response({"detail": "Plafond hors limites (0–100 000 kWh)."}, status=status.HTTP_400_BAD_REQUEST)
        budget, created = BudgetSetting.objects.get_or_create(meter=meter, defaults={"limit_kwh": limit})
        if not created:
            budget.limit_kwh = limit
            budget.save(update_fields=["limit_kwh"])
        detect_anomalies(meter)
        meter.refresh_from_db()
        return Response({"limit_kwh": float(budget.limit_kwh), "warning_percentage": budget.warning_percentage, "balance_kwh": float(meter.balance_kwh)}, status=status.HTTP_200_OK)


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        meter = subscriber_meter_for(request.user)
        if not meter:
            demo_consumption = [{"label": "06:00", "kwh": 0.42}, {"label": "09:00", "kwh": 0.86}, {"label": "12:00", "kwh": 0.68}, {"label": "15:00", "kwh": 0.92, "recharge": "APP_PAIEMENT"}, {"label": "18:00", "kwh": 1.32}, {"label": "21:00", "kwh": 1.74, "recharge": "SAISIE_MANUELLE"}, {"label": "00:00", "kwh": 1.05}]
            return Response({
                "mode": "DEMO",
                "meter": {"id": "VSF-000001", "location": "Quartier Himbi", "sector": "Goma — Karisimbi", "device_status": "ONLINE", "relay_status": True, "signal_strength": 86, "firmware_version": "v2.4.1"},
                "telemetry": {"voltage": 220.4, "current": 2.31, "power": 508.2, "energy_consumed": 0.084},
                "balance": {"kwh": 18.42, "cdf": 46050, "usd": 18.42},
                "cdf_per_usd": float(CDF_PER_USD),
                "estimate_hours": 82.4,
                "consumption": demo_consumption,
                "consumption_daily": daily_consumption_breakdown(demo_consumption),
                "consumption_weekly": [],
                "budget": {"used_kwh": 12.8, "limit_kwh": 40},
                "recharges": [{"id": "demo-app", "source": "APP_PAIEMENT", "energy_kwh": 10}, {"id": "demo-manual", "source": "SAISIE_MANUELLE", "energy_kwh": 5}],
                "alerts": [{"kind": "SOLDE_BAS", "severity": "WARNING", "message": "Solde bas : 18.42 kWh restants."}],
            })
        check_heartbeats()
        meter.refresh_from_db()
        pending_command = meter.relay_commands.filter(status=RelayCommand.PENDING).first()

        # Consommation des dernières 24 h, heure par heure, avec annotations de recharge.
        # L'énergie est CUMULÉE : la consommation d'une heure = différence d'énergie
        # cumulée entre la fin de l'heure et la fin de l'heure précédente.
        since = timezone.now() - timedelta(hours=24)
        telemetry_rows = list(meter.telemetry.filter(applied_at__gte=since).order_by("applied_at"))
        consumption = []
        if telemetry_rows:
            hourly_energy = {}
            for row in telemetry_rows:
                # Clé datée : évite de fusionner la même heure sur deux jours de la fenêtre
                hourly_energy[row.applied_at.strftime("%Y-%m-%d %H:00")] = float(row.energy_kwh)
            recharges_by_hour = {}
            for recharge in meter.recharges.filter(status=Recharge.STATUS_APPLIED, applied_at__gte=since):
                recharges_by_hour[recharge.applied_at.strftime("%Y-%m-%d %H:00")] = recharge.source
            previous_energy = None
            for key in sorted(hourly_energy):
                energy = hourly_energy[key]
                kwh = 0.0 if previous_energy is None else round(max(energy - previous_energy, 0), 3)
                entry = {"label": key[11:16], "kwh": kwh}
                if key in recharges_by_hour:
                    entry["recharge"] = recharges_by_hour[key]
                consumption.append(entry)
                previous_energy = energy

        # Répartition pour les camemberts : journalière (4 périodes) et
        # hebdomadaire (7 jours calendaires), calculées depuis les télémétries
        # persistées — jamais de valeur inventée.
        consumption_daily = daily_consumption_breakdown(consumption)
        week_rows = list(meter.telemetry.filter(applied_at__gte=timezone.now() - timedelta(days=7)).order_by("applied_at"))
        consumption_weekly = weekly_consumption_breakdown(week_rows)

        budget = getattr(meter, "budget", None)
        credit = credit_status(meter)
        last_telemetry = meter.telemetry.order_by("-applied_at").first()
        return Response({
            "mode": "DEMO" if meter.is_demo else "PERSISTED",
            "meter": {"id": meter.meter_id, "location": meter.sector.territory, "sector": meter.sector.name,
                      "device_status": meter.device_status, "relay_status": meter.relay_status == "ON",
                      "signal_strength": meter.signal_gsm, "firmware_version": meter.firmware_version},
            "telemetry": {"voltage": float(meter.voltage_v), "current": float(meter.current_a), "power": float(meter.power_w),
                          "energy_consumed": float(meter.energy_kwh)},
            "balance": {"kwh": float(meter.balance_kwh), "cdf": float(meter.balance_kwh * CDF_PER_KWH), "usd": float(meter.balance_kwh * USD_PER_KWH)},
            "cdf_per_usd": float(CDF_PER_USD),
            "tariff": {"cdf_per_kwh": float(CDF_PER_KWH), "usd_per_kwh": float(USD_PER_KWH)},
            "credit": {"percent": credit["percent"], "reference_kwh": credit["reference_kwh"],
                       "threshold": credit["threshold"], "thresholds": list(CREDIT_THRESHOLDS)},
            "notifications": notification_channels(meter),
            "estimate_hours": estimate_hours(meter),
            "consumption": consumption,
            "consumption_daily": consumption_daily,
            "consumption_weekly": consumption_weekly,
            "budget": {"used_kwh": round(sum(item["kwh"] for item in consumption), 3),
                       "limit_kwh": float(budget.limit_kwh) if budget else 0},
            "recharges": [
                {"id": str(recharge.id), "source": recharge.source, "energy_kwh": float(recharge.energy_kwh), "status": recharge.status,
                 "applied_at": recharge.applied_at.isoformat() if recharge.applied_at else None,
                 "synced_at": recharge.synced_at.isoformat()}
                for recharge in meter.recharges.filter(status=Recharge.STATUS_APPLIED).order_by("-applied_at")[:10]
            ],
            "alerts": [
                {"id": alert.id, "kind": alert.kind, "severity": alert.severity, "message": alert.message, "created_at": alert.created_at.isoformat()}
                for alert in meter.alerts.filter(acknowledged_at__isnull=True)[:10]
            ],
            "last_telemetry_at": last_telemetry.applied_at.isoformat() if last_telemetry else None,
            "relay_command": {"id": pending_command.id, "desired_state": pending_command.requested_state, "status": pending_command.status} if pending_command else None,
        })


class AlertAcknowledgeView(APIView):
    """L'abonné marque une alerte comme lue : elle quitte la liste des alertes ouvertes."""

    permission_classes = [IsAuthenticated]

    def post(self, request, alert_id: int):
        meter = subscriber_meter_for(request.user)
        if not meter:
            return Response({"detail": "Aucun compteur n'est associé à cet abonné."}, status=status.HTTP_403_FORBIDDEN)
        updated = meter.alerts.filter(pk=alert_id, acknowledged_at__isnull=True).update(acknowledged_at=timezone.now())
        if not updated and not meter.alerts.filter(pk=alert_id).exists():
            return Response({"detail": "Alerte introuvable."}, status=status.HTTP_404_NOT_FOUND)
        notify_telemetry_refresh(meter)
        return Response({"acknowledged": True, "open_alerts": meter.alerts.filter(acknowledged_at__isnull=True).count()})


class SubscriberProfileView(APIView):
    """Coordonnées de contact de l'abonné (destinataires des alertes) et état des canaux."""

    permission_classes = [IsAuthenticated]

    def _payload(self, meter) -> dict:
        return {**_subscriber_payload(meter), "channels": notification_channels(meter)}

    def get(self, request):
        meter = subscriber_meter_for(request.user)
        if not meter:
            return Response({"detail": "Aucun compteur n'est associé à cet abonné."}, status=status.HTTP_403_FORBIDDEN)
        return Response(self._payload(meter))

    def post(self, request):
        meter = subscriber_meter_for(request.user)
        if not meter:
            return Response({"detail": "Aucun compteur n'est associé à cet abonné."}, status=status.HTTP_403_FORBIDDEN)
        serializer = SubscriberProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = []
        for name in ("email", "phone", "address"):
            if name in serializer.validated_data:
                setattr(meter, f"subscriber_{name}", serializer.validated_data[name])
                fields.append(f"subscriber_{name}")
        if fields:
            meter.save(update_fields=fields)
        return Response(self._payload(meter))


class NotificationTestView(APIView):
    """Envoie un message d'essai sur les canaux prêts et rapporte le résultat réel de chacun."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "notification_test"

    def post(self, request):
        meter = subscriber_meter_for(request.user)
        if not meter:
            return Response({"detail": "Aucun compteur n'est associé à cet abonné."}, status=status.HTTP_403_FORBIDDEN)
        credit = credit_status(meter)
        level = f"{credit['percent']:.0f} %" if credit["percent"] is not None else "inconnu"
        results = send_notification(
            meter,
            f"Virunga Smart Energy — message d'essai (compteur {meter.meter_id})",
            f"Message d'essai Virunga Smart Energy. Compteur {meter.meter_id} : solde {Decimal(str(meter.balance_kwh)):.2f} kWh, niveau de crédit {level}.",
        )
        return Response({"results": results})


class RelayCommandView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RelayCommandRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meter = subscriber_meter_for(request.user)
        if not meter:
            return Response({"detail": "Aucun compteur n'est associé à cet abonné."}, status=status.HTTP_403_FORBIDDEN)
        desired_state = serializer.validated_data["desired_state"]
        if desired_state == RelayCommand.ON and meter.balance_kwh <= 0:
            return Response({"detail": "Solde épuisé : rechargez votre crédit pour rétablir le courant."}, status=status.HTTP_409_CONFLICT)
        with transaction.atomic():
            meter.relay_commands.filter(status=RelayCommand.PENDING).update(status=RelayCommand.SUPERSEDED)
            command = RelayCommand.objects.create(meter=meter, requested_state=desired_state, requested_by=request.user.username)
        return Response({"id": command.id, "status": command.status, "desired_state": command.requested_state, "message": "Commande enregistrée. Elle sera fournie au compteur lors de sa prochaine télémétrie HTTPS signée."}, status=status.HTTP_202_ACCEPTED)


class NewsViewSet(viewsets.ModelViewSet):
    serializer_class = NewsArticleSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = NewsArticle.objects.all()
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return queryset
        return queryset.filter(is_published=True)

    def _require_staff(self):
        if not self.request.user.is_staff:
            raise PermissionDenied("Accès administrateur requis.")

    def perform_create(self, serializer):
        self._require_staff()
        serializer.save()

    def perform_update(self, serializer):
        self._require_staff()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_staff()
        instance.delete()
