"""Cœur métier Virunga Smart Energy.

Signatures HMAC, tokens de recharge, règle de relais, détection d'anomalies,
reçus PDF, assistant contextuel et notifications temps réel.

Toutes les valeurs simulées sont produites par le simulateur (commande
``simulate_meter``) et marquées ``is_demo`` sur le compteur correspondant.
"""
import base64
import hashlib
import hmac
import io
import json
import os
import urllib.error
import urllib.request
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Alert, ManualToken, Meter, Recharge

# ---------------------------------------------------------------------------
# Bornes physiques et seuils (contrat du prompt d'ingénierie)
# ---------------------------------------------------------------------------
VOLTAGE_MIN, VOLTAGE_MAX = 0.0, 300.0
CURRENT_MAX = 100.0
POWER_MAX = 30000.0
ENERGY_MAX = 1_000_000.0
OVERVOLTAGE_V = 253.0
UNDERVOLTAGE_V = 207.0
SURCONSOMMATION_W = 5000.0
LOW_BALANCE_KWH = Decimal("5")
HEARTBEAT_TIMEOUT = timedelta(minutes=2)
STALE_WINDOW = timedelta(minutes=10)
FUTURE_WINDOW = timedelta(minutes=5)
ALERT_DEDUP_WINDOW = timedelta(minutes=15)
CDF_PER_KWH = Decimal("2500")            # tarif : prix de 1 kWh en francs congolais (FC)
CDF_PER_USD = Decimal("2500")            # taux de change officiel : 1 USD = 2500 FC
USD_PER_KWH = CDF_PER_KWH / CDF_PER_USD  # tarif en USD, cohérent avec le taux (1 kWh = 1 USD)


# ---------------------------------------------------------------------------
# Signature HMAC du canal compteur -> backend
# ---------------------------------------------------------------------------
def canonical_json(data) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def iot_secret() -> str:
    return os.getenv("VIRUNGA_IOT_HMAC_SECRET", "")


def compute_signature(payload) -> str:
    return hmac.new(iot_secret().encode(), canonical_json(payload), hashlib.sha256).hexdigest()


def verify_signature(payload, provided) -> bool:
    secret = iot_secret()
    if not secret or not provided:
        return False
    expected = hmac.new(secret.encode(), canonical_json(payload), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


# ---------------------------------------------------------------------------
# Token de recharge hors ligne (scénario B du prompt)
# ---------------------------------------------------------------------------
def _token_secret() -> str:
    return os.getenv("VIRUNGA_TOKEN_SECRET", iot_secret() or settings.SECRET_KEY)


def issue_manual_token(meter: Meter, energy_kwh) -> tuple[str, dict]:
    """Émet un token signé HMAC-SHA256 lié au meter_id et à un numéro de séquence."""
    last = meter.manual_tokens.order_by("-sequence").first()
    sequence = (last.sequence + 1) if last else 1
    issued_at = timezone.now()
    payload = {
        "meter_id": meter.meter_id,
        "energy_kwh": float(energy_kwh),
        "sequence": sequence,
        "issued_at": issued_at.isoformat(),
    }
    body = base64.urlsafe_b64encode(canonical_json(payload)).decode("ascii").rstrip("=")
    signature = hmac.new(_token_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    token = f"VSE.{body}.{signature}"
    ManualToken.objects.create(meter=meter, token=token, sequence=sequence, energy_kwh=energy_kwh, issued_at=issued_at)
    return token, payload


def parse_manual_token(token: str) -> tuple[dict | None, str | None]:
    """Vérifie la signature HMAC d'un token saisi au clavier (simulation du compteur)."""
    parts = str(token).strip().split(".")
    if len(parts) != 3 or parts[0] != "VSE":
        return None, "Format de token invalide (attendu VSE.<payload>.<signature>)."
    body, signature = parts[1], parts[2]
    expected = hmac.new(_token_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None, "Signature HMAC du token invalide."
    try:
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None, "Contenu du token illisible."
    return payload, None


# ---------------------------------------------------------------------------
# Recharge et règle de relais automatique
# ---------------------------------------------------------------------------
def apply_relay_rule(meter: Meter) -> str:
    """Coupure automatique si solde <= 0, rétablissement si solde > 0."""
    desired = "OFF" if meter.balance_kwh <= 0 else "ON"
    if meter.relay_status != desired:
        meter.relay_status = desired
        meter.save(update_fields=["relay_status", "updated_at"])
    return desired


def apply_recharge(meter: Meter, source: str, energy_kwh, applied_at, provider_reference: str = "", notify: bool = True) -> Recharge:
    with transaction.atomic():
        meter = Meter.objects.select_for_update().get(pk=meter.pk)
        meter.balance_kwh += Decimal(str(energy_kwh))
        meter.save(update_fields=["balance_kwh", "updated_at"])
        recharge = Recharge.objects.create(
            meter=meter, source=source, energy_kwh=energy_kwh,
            status=Recharge.STATUS_APPLIED, applied_at=applied_at, provider_reference=provider_reference,
        )
        apply_relay_rule(meter)
    if notify:
        notify_telemetry_refresh(meter)
    return recharge


def pending_recharge_by_reference(reference: str, meter: Meter | None = None) -> Recharge | None:
    queryset = Recharge.objects.filter(provider_reference=reference, status=Recharge.STATUS_PENDING)
    if meter is not None:
        queryset = queryset.filter(meter=meter)
    return queryset.first()


def complete_pending_recharge(recharge: Recharge, applied_at=None) -> Recharge:
    with transaction.atomic():
        recharge = Recharge.objects.select_for_update().get(pk=recharge.pk)
        if recharge.status != Recharge.STATUS_PENDING:
            return recharge
        meter = Meter.objects.select_for_update().get(pk=recharge.meter_id)
        meter.balance_kwh += recharge.energy_kwh
        meter.save(update_fields=["balance_kwh", "updated_at"])
        recharge.status = Recharge.STATUS_APPLIED
        recharge.applied_at = applied_at or timezone.now()
        recharge.save(update_fields=["status", "applied_at"])
        apply_relay_rule(meter)
    notify_telemetry_refresh(meter)
    return recharge


# ---------------------------------------------------------------------------
# Détection d'anomalies (système automatique du prompt)
# ---------------------------------------------------------------------------
def _consumption_last_24h(meter: Meter) -> Decimal:
    since = timezone.now() - timedelta(hours=24)
    rows = list(meter.telemetry.filter(applied_at__gte=since).order_by("applied_at").values_list("energy_kwh", flat=True))
    if not rows:
        return Decimal("0")
    return Decimal(str(max(rows))) - Decimal(str(min(rows)))


def detect_anomalies(meter: Meter, data: dict) -> list[Alert]:
    """Crée des Alert pour les anomalies détectées sur la télémétrie reçue.

    Une alerte du même type déjà ouverte (non acquittée) depuis moins de
    ``ALERT_DEDUP_WINDOW`` n'est pas recréée : évite le bruit à chaque
    télémétrie de 5 secondes.
    """
    created: list[Alert] = []
    voltage = data.get("voltage")
    power = data.get("power")
    dedup_threshold = timezone.now() - ALERT_DEDUP_WINDOW
    open_kinds = set(
        meter.alerts.filter(acknowledged_at__isnull=True, created_at__gte=dedup_threshold)
        .values_list("kind", flat=True)
    )

    def add(kind, severity, message):
        if kind in open_kinds:
            return
        open_kinds.add(kind)
        created.append(Alert.objects.create(meter=meter, kind=kind, severity=severity, message=message))

    if voltage is not None and voltage > OVERVOLTAGE_V:
        add("SURTENSION", "CRITICAL", f"Tension {voltage} V au-dessus du seuil {OVERVOLTAGE_V} V.")
    if voltage is not None and 0 < voltage < UNDERVOLTAGE_V:
        add("SOUS_TENSION", "WARNING", f"Tension {voltage} V sous le seuil {UNDERVOLTAGE_V} V.")
    if power is not None and power > SURCONSOMMATION_W:
        add("SURCONSOMMATION", "WARNING", f"Puissance {power} W au-dessus du seuil {SURCONSOMMATION_W} W.")
    if meter.balance_kwh <= LOW_BALANCE_KWH:
        add("SOLDE_BAS", "WARNING", f"Solde bas : {meter.balance_kwh} kWh restants.")
    if meter.balance_kwh <= 0:
        add("SOLDE_EPUISE", "CRITICAL", "Solde épuisé : courant coupé automatiquement.")

    budget = getattr(meter, "budget", None)
    if budget is not None and budget.limit_kwh > 0:
        used_24h = _consumption_last_24h(meter)
        warning_at = budget.limit_kwh * (Decimal(budget.warning_percentage) / Decimal(100))
        if used_24h >= budget.limit_kwh:
            add("DEPASSEMENT_BUDGET", "WARNING", f"Budget dépassé : {used_24h} kWh consommés sur un plafond de {budget.limit_kwh} kWh.")
        elif used_24h >= warning_at:
            add("BUDGET_APPROCHE", "INFO", f"Budget presque atteint : {used_24h} kWh sur {budget.limit_kwh} kWh.")
    return created


def check_heartbeats() -> list[Meter]:
    """Marque OFFLINE les compteurs sans télémétrie depuis HEARTBEAT_TIMEOUT."""
    threshold = timezone.now() - HEARTBEAT_TIMEOUT
    stale = list(Meter.objects.filter(device_status="ONLINE", updated_at__lt=threshold))
    for meter in stale:
        Meter.objects.filter(pk=meter.pk).update(device_status="OFFLINE", updated_at=timezone.now())
        has_open = meter.alerts.filter(kind="PERTE_COMMUNICATION", acknowledged_at__isnull=True).exists()
        if not has_open:
            Alert.objects.create(meter=meter, kind="PERTE_COMMUNICATION", severity="CRITICAL",
                                 message="Absence de heartbeat : communication perdue avec le compteur.")
    return stale


# ---------------------------------------------------------------------------
# Estimation de durée restante
# ---------------------------------------------------------------------------
def estimate_hours(meter: Meter) -> float:
    if meter.balance_kwh <= 0:
        return 0.0
    last = meter.telemetry.order_by("-applied_at").first()
    power_w = float(last.power_w) if last else float(meter.power_w)
    if power_w <= 0:
        return 0.0
    return float(meter.balance_kwh) / (power_w / 1000.0)


# ---------------------------------------------------------------------------
# Reçu PDF réel (générateur pur Python, sans dépendance externe)
# ---------------------------------------------------------------------------
def _pdf_escape(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return text.encode("cp1252", errors="replace").decode("cp1252")


def generate_receipt_pdf(recharge: Recharge, meter: Meter, subscriber_name: str = "") -> bytes:
    """Génère un reçu PDF valide (structure PDF 1.4, police Helvetica)."""
    lines = [
        ("VIRUNGA SMART ENERGY — REÇU DE RECHARGE", 14, True),
        ("Simulation academique independante — source d'inspiration : Virunga Energies", 9, False),
        ("", 10, False),
        ("Recharge n°", 10, True),
        (f"Compteur : {meter.meter_id}", 10, False),
        (f"Abonne : {subscriber_name or (meter.subscriber_first_name + ' ' + meter.subscriber_last_name).strip()}", 10, False),
        (f"Source : {recharge.source}", 10, False),
        (f"Energie : {recharge.energy_kwh} kWh", 10, False),
        (f"Statut : {recharge.status}", 10, False),
        (f"Appliquee le (compteur) : {recharge.applied_at.strftime('%d/%m/%Y %H:%M:%S') if recharge.applied_at else '—'}", 10, False),
        (f"Synchronisee le (serveur) : {recharge.synced_at.strftime('%d/%m/%Y %H:%M:%S')}", 10, False),
        (f"Reference : {recharge.provider_reference or '—'}", 10, False),
        (f"Solde apres recharge : {meter.balance_kwh} kWh", 10, False),
    ]
    if meter.is_demo:
        lines.append(("", 10, False))
        lines.append(("Document DEMO genere par le simulateur — aucune valeur monetaire reelle.", 9, False))

    stream_parts = []
    y = 800
    for text, size, bold in lines:
        font = "/F2" if bold else "/F1"
        stream_parts.append(f"BT {font} {size} Tf 40 {y} Td ({_pdf_escape(text)}) Tj ET")
        y -= 22 if text else 10

    content_stream = "\n".join(stream_parts).encode("cp1252", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(content_stream)).encode() + b" >>\nstream\n" + content_stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_position = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_position}\n%%EOF\n".encode()
    )
    return bytes(output)


# ---------------------------------------------------------------------------
# Assistant contextuel (réponses à partir des données réelles uniquement)
# ---------------------------------------------------------------------------
def assistant_answer(meter: Meter, question: str) -> str:
    q = question.strip().lower()
    first = f"{meter.subscriber_first_name} {meter.subscriber_last_name}".strip() or "abonné"

    if any(word in q for word in ["bonjour", "salut", "hello", "coucou"]):
        return f"Bonjour {first} ! Je suis l'assistant Virunga Smart Energy. Je peux vous renseigner sur votre solde, votre consommation, vos recharges et les alertes de votre compteur {meter.meter_id}."

    if any(word in q for word in ["solde", "crédit", "sold"]):
        return (f"Votre solde est de {meter.balance_kwh:.2f} kWh, soit environ {float(meter.balance_kwh) * float(CDF_PER_KWH):,.0f} CDF "
                f"ou {float(meter.balance_kwh) * float(USD_PER_KWH):,.2f} USD.")

    if any(word in q for word in ["durée", "combien de temps", "jusqu'à", "encore"]):
        hours = estimate_hours(meter)
        if hours <= 0:
            return "Votre solde est épuisé ou la consommation actuelle est nulle : je ne peux pas estimer de durée restante."
        return f"Au rythme de consommation actuel, votre crédit restant ({meter.balance_kwh} kWh) devrait durer environ {hours:.1f} heures."

    if any(word in q for word in ["recharge", "paiement", "token"]):
        last = meter.recharges.filter(status=Recharge.STATUS_APPLIED).order_by("-applied_at").first()
        if not last:
            return "Aucune recharge n'est encore enregistrée sur votre compteur."
        return (f"Votre dernière recharge provient de la source {last.source} : {last.energy_kwh} kWh, "
                f"appliquée le {last.applied_at.strftime('%d/%m/%Y %H:%M')} (reçue par le serveur le {last.synced_at.strftime('%d/%m/%Y %H:%M')}).")

    if any(word in q for word in ["consommation", "consomme", "tension", "courant", "puissance"]):
        last = meter.telemetry.order_by("-applied_at").first()
        if not last:
            return "Aucune télémétrie n'a encore été reçue de votre compteur."
        return (f"Dernière mesure ({last.applied_at.strftime('%d/%m/%Y %H:%M')}) : tension {last.voltage_v} V, "
                f"courant {last.current_a} A, puissance {last.power_w} W, énergie cumulée {last.energy_kwh} kWh.")

    if any(word in q for word in ["alerte", "anomalie", "problème", "incident"]):
        alerts = list(meter.alerts.filter(acknowledged_at__isnull=True)[:5])
        if not alerts:
            return "Aucune anomalie ouverte sur votre compteur. Tout est nominal."
        lines = [f"Voici les {len(alerts)} anomalie(s) ouverte(s) :"]
        lines += [f"- [{a.kind}] {a.message}" for a in alerts]
        return "\n".join(lines)

    if any(word in q for word in ["relais", "coupé", "coupure", "isolement"]):
        state = "COUPÉ (OFF)" if meter.relay_status == "OFF" else "ACTIF (ON)"
        return f"Le relais de votre compteur est {state}. La coupure/le rétablissement est automatique selon votre solde."

    return (f"Je n'ai pas compris votre demande. Je peux répondre uniquement à partir des données réelles de votre compteur "
            f"({meter.meter_id}) : solde, durée restante estimée, consommation, recharges, alertes et état du relais. "
            f"Je ne peux pas inventer une information que je ne possède pas.")


# ---------------------------------------------------------------------------
# Agent IA — DeepSeek (API OpenAI-compatible, stdlib urllib, zéro dépendance)
# ---------------------------------------------------------------------------
def assistant_context(meter: Meter) -> dict:
    """Contexte réel du compteur injecté au LLM. Aucune valeur n'est inventée."""
    last = meter.telemetry.order_by("-applied_at").first()
    last_recharge = meter.recharges.filter(status=Recharge.STATUS_APPLIED).order_by("-applied_at").first()
    alerts = list(meter.alerts.filter(acknowledged_at__isnull=True)[:5])
    ctx = {
        "abonne": f"{meter.subscriber_first_name} {meter.subscriber_last_name}".strip() or "abonné",
        "compteur": meter.meter_id,
        "solde_kwh": round(float(meter.balance_kwh), 3),
        "solde_cdf": round(float(meter.balance_kwh) * float(CDF_PER_KWH), 2),
        "solde_usd": round(float(meter.balance_kwh) * float(USD_PER_KWH), 2),
        "duree_estimee_heures": round(estimate_hours(meter), 1),
        "relais": "ON (alimentation active)" if meter.relay_status == "ON" else "OFF (coupé)",
        "derniere_recharge": (
            f"{float(last_recharge.energy_kwh)} kWh (source {last_recharge.source}) "
            f"le {last_recharge.applied_at.strftime('%d/%m/%Y %H:%M')}"
            if last_recharge else "aucune recharge enregistrée"
        ),
        "alertes_ouvertes": [{"type": a.kind, "message": a.message} for a in alerts],
    }
    if last:
        ctx["derniere_mesure"] = {
            "horodatage": last.applied_at.strftime("%d/%m/%Y %H:%M"),
            "tension_v": float(last.voltage_v),
            "courant_a": float(last.current_a),
            "puissance_w": float(last.power_w),
            "energie_kwh_cumulee": float(last.energy_kwh),
        }
    return ctx


def assistant_system_prompt(meter: Meter) -> str:
    """Prompt système : identité, règles anti-hallucination et données réelles."""
    return (
        "Tu es l'assistant IA de « Virunga Smart Energy », une plateforme de compteurs "
        "électriques prépayés inspirée de Virunga Energies (Goma/Rutshuru, RDC). "
        "Réponds en français, de façon claire, concise et chaleureuse.\n\n"
        "RÈGLES STRICTES (anti-hallucination) :\n"
        "1. Tu réponds UNIQUEMENT à partir des données RÉELLES de l'abonné fournies ci-dessous. "
        "N'invente jamais un nombre, une date ou une information absente.\n"
        "2. Si la question sort de ce périmètre (solde, consommation, recharges, alertes, "
        "relais, budget, estimation de durée), réponds honnêtement que tu ne peux pas y répondre.\n"
        "3. Tu peux faire de simples calculs (ex. convertir kWh en CDF/USD) à partir des valeurs "
        "fournies, en restant cohérent avec elles.\n\n"
        f"DONNÉES RÉELLES DE L'ABONNÉ (compteur {meter.meter_id}) :\n"
        f"{json.dumps(assistant_context(meter), ensure_ascii=False, indent=2)}"
    )


def deepseek_chat(system_prompt: str, user_question: str,
                  api_key: str, base_url: str, model: str,
                  timeout: float = 30.0, max_tokens: int = 600) -> str:
    """Appelle l'API DeepSeek (compatible OpenAI) via urllib. Lève une exception en cas d'échec."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_question},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    choice = data["choices"][0]["message"]["content"] or ""
    return choice.strip()


# ---------------------------------------------------------------------------
# Notification temps réel (Django Channels)
# ---------------------------------------------------------------------------
def notify_telemetry_refresh(meter: Meter | None = None) -> None:
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if layer is None:
        return
    payload = {"type": "telemetry.refresh"}
    if meter is not None:
        payload["meter_id"] = meter.meter_id
    try:
        async_to_sync(layer.group_send)("telemetry", payload)
    except Exception:
        # Le temps réel ne doit jamais faire échouer le flux principal.
        pass
