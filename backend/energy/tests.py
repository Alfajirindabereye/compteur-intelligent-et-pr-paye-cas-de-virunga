import hashlib
import hmac
import json
import os
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from config.asgi import application
from config.urls import frontend_file
from .models import Alert, Meter, NewsArticle, PaymentEvent, Recharge, RelayCommand, Sector
from .serializers import TelemetryPayloadSerializer

IOT_SECRET = "test-secret"


def make_payload(**overrides):
    payload = {
        "message_id": str(uuid.uuid4()),
        "meter_id": "VSF-000001",
        "device_timestamp": timezone.now().isoformat(),
        "voltage": 220.4,
        "current": 2.31,
        "power": 508.2,
        "energy_consumed": 10.0,
        "balance_kwh": 18.42,
        "relay_status": True,
        "signal_strength": 76,
        "device_status": "ONLINE",
        "firmware_version": "1.0.0",
    }
    payload.update(overrides)
    return payload


def signed_headers(payload, secret=IOT_SECRET):
    """Signe le payload brut, exactement tel qu'il sera envoyé (contrat HMAC)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    signature = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    return {"HTTP_X_VIRUNGA_SIGNATURE": signature}


class EnergyApiIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="subscriber")
        self.admin = User.objects.create_user(username="administrator", is_staff=True)
        self.sector = Sector.objects.create(name="Goma — Karisimbi", territory="Goma")
        self.meter = Meter.objects.create(
            meter_id="VSF-000001",
            sector=self.sector,
            owner_open_id="subscriber",
            device_status="ONLINE",
            balance_kwh=18.42,
            subscriber_code="12345678901234567890",
            subscriber_first_name="Amani",
            subscriber_last_name="Kambale",
        )
        self.client = APIClient()

    def ingest(self, payload):
        with patch.dict(os.environ, {"VIRUNGA_IOT_HMAC_SECRET": IOT_SECRET}):
            return APIClient().post("/api/iot/telemetry", payload, format="json", **signed_headers(payload))

    def test_dashboard_endpoint_returns_contract(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("meter", response.data)
        self.assertIn("balance", response.data)
        self.assertEqual(response.data["mode"], "PERSISTED")

    def test_consumption_breakdown_helpers_are_deterministic(self):
        from datetime import datetime, timedelta, timezone as dt_timezone
        from decimal import Decimal

        from .models import Telemetry
        from .views import daily_consumption_breakdown, weekly_consumption_breakdown

        # On gèle l'heure pour rendre l'agrégation par jour calendaire déterministe
        # (sinon la répartition des 8 relevés entre 2 jours change au fil de la journée).
        frozen = datetime(2026, 8, 25, 18, 0, 0, tzinfo=dt_timezone.utc)
        with patch("django.utils.timezone.now", return_value=frozen):
            now = frozen
            rows = []
            energy = 10.0
            for hours_ago in (32, 30, 28, 26, 8, 6, 4, 2):
                energy += 1.0
                rows.append(Telemetry(
                    meter=self.meter, message_id=str(uuid.uuid4()),
                    applied_at=now - timedelta(hours=hours_ago),
                    voltage_v=Decimal("220"), current_a=Decimal("2"), power_w=Decimal("500"),
                    energy_kwh=Decimal(str(energy)), balance_kwh=Decimal("18.42"),
                    relay_status="ON", signal_gsm=70,
                ))

            # Camembert journalier : 4 périodes, aucune valeur inventée, somme cohérente.
            hourly = [{"label": point.applied_at.strftime("%H:%M"), "kwh": 1.0} for point in rows[-4:]]
            daily = daily_consumption_breakdown(hourly)
            self.assertEqual([entry["label"] for entry in daily], ["Nuit", "Matin", "Après-midi", "Soirée"])
            self.assertEqual(sum(entry["kwh"] for entry in daily), 4.0)

            # Camembert hebdomadaire : 7 jours calendaires, jours sans relevé à 0 kWh.
            # Avec l'heure gelée (18:00), les 4 anciens relevés tombent la veille et les 4
            # récents le jour même → 2 jours, chacun (max−min) = 3.0 → total 6.0, stable.
            weekly = weekly_consumption_breakdown(rows)
            self.assertEqual(len(weekly), 7)
            self.assertEqual([entry["label"] for entry in weekly],
                             ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"][(now - timedelta(days=6)).date().weekday():] +
                             ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"][:(now - timedelta(days=6)).date().weekday()])
            self.assertEqual(sum(entry["kwh"] for entry in weekly), 6.0)
            self.assertTrue(all(entry["kwh"] >= 0 for entry in weekly))

    def test_dashboard_returns_daily_and_weekly_consumption_breakdown(self):
        from datetime import datetime, timedelta, timezone as dt_timezone
        from decimal import Decimal

        from .models import Telemetry

        frozen = datetime(2026, 8, 25, 18, 0, 0, tzinfo=dt_timezone.utc)
        with patch("django.utils.timezone.now", return_value=frozen):
            now = frozen
            rows = []
            energy = 10.0
            for hours_ago in (32, 30, 28, 26, 8, 6, 4, 2):
                energy += 1.0
                rows.append(Telemetry(
                    meter=self.meter, message_id=str(uuid.uuid4()),
                    applied_at=now - timedelta(hours=hours_ago),
                    voltage_v=Decimal("220"), current_a=Decimal("2"), power_w=Decimal("500"),
                    energy_kwh=Decimal(str(energy)), balance_kwh=Decimal("18.42"),
                    relay_status="ON", signal_gsm=70,
                ))
            Telemetry.objects.bulk_create(rows)

            self.client.force_authenticate(self.user)
            response = self.client.get("/api/dashboard/")
            self.assertEqual(response.status_code, 200)
            daily = response.data["consumption_daily"]
            self.assertEqual([entry["label"] for entry in daily], ["Nuit", "Matin", "Après-midi", "Soirée"])
            # La somme du camembert journalier égale la somme du profil horaire (24 h).
            self.assertAlmostEqual(sum(entry["kwh"] for entry in daily), sum(entry["kwh"] for entry in response.data["consumption"]), places=3)
            weekly = response.data["consumption_weekly"]
            self.assertEqual(len(weekly), 7)
            # Heure gelée 18:00 → fenêtre 24h = les 4 relevés récents (somme 3.0),
            # semaine = 4 relevés veille + 4 relevés jour (max−min = 3.0+3.0 = 6.0).
            self.assertEqual(sum(entry["kwh"] for entry in weekly), round(sum(entry["kwh"] for entry in daily), 3) + 3.0)

    def test_subscriber_login_issues_access_and_refresh_tokens(self):
        response = self.client.post("/api/auth/subscriber/login/", {"first_name": "Amani", "last_name": "Kambale", "meter_code": "12345678901234567890"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.data)
        self.assertIn("refresh_token", response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access_token']}")
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data["meter"]["id"], self.meter.meter_id)

    def test_login_sets_persistent_refresh_cookie_and_stores_contact(self):
        response = self.client.post(
            "/api/auth/subscriber/login/",
            {"first_name": "Amani", "last_name": "Kambale", "meter_code": "12345678901234567890",
             "email": "amani.kambale@example.com", "phone": "+243993456789", "address": "Av. du Lac 12, Goma"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("vse_refresh", response.cookies)
        self.assertEqual(response.data["subscriber"]["email"], "amani.kambale@example.com")
        self.assertEqual(response.data["subscriber"]["phone"], "+243993456789")
        self.assertEqual(response.data["subscriber"]["address"], "Av. du Lac 12, Goma")
        self.meter.refresh_from_db()
        self.assertEqual(self.meter.subscriber_email, "amani.kambale@example.com")
        self.assertEqual(self.meter.subscriber_phone, "+243993456789")
        self.assertEqual(self.meter.subscriber_address, "Av. du Lac 12, Goma")

    def test_refresh_works_from_cookie_for_auto_login(self):
        # Login → le client conserve le cookie vse_refresh ; un refresh sans corps doit réussir (auto-login).
        self.client.post("/api/auth/subscriber/login/", {"first_name": "Amani", "last_name": "Kambale", "meter_code": "12345678901234567890"}, format="json")
        response = self.client.post("/api/auth/token/refresh/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.data)
        self.assertIn("subscriber", response.data)
        self.assertEqual(response.data["subscriber"]["meter_id"], self.meter.meter_id)

    def test_refresh_without_token_or_cookie_is_rejected(self):
        response = self.client.post("/api/auth/token/refresh/", {}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_logout_clears_persistent_refresh_cookie(self):
        self.client.post("/api/auth/subscriber/login/", {"first_name": "Amani", "last_name": "Kambale", "meter_code": "12345678901234567890"}, format="json")
        response = self.client.post("/api/auth/subscriber/logout/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["logged_out"], True)
        self.assertIn("vse_refresh", response.cookies)
        self.assertEqual(response.cookies["vse_refresh"].value, "")

    def test_refresh_token_rotates_and_issues_new_access(self):
        login = self.client.post("/api/auth/subscriber/login/", {"first_name": "Amani", "last_name": "Kambale", "meter_code": "12345678901234567890"}, format="json")
        refresh = login.data["refresh_token"]
        response = self.client.post("/api/auth/token/refresh/", {"refresh_token": refresh}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.data)
        self.assertIn("refresh_token", response.data)
        self.assertNotEqual(response.data["refresh_token"], refresh)
        # Un refresh token non-refresh est rejeté
        rejected = self.client.post("/api/auth/token/refresh/", {"refresh_token": login.data["access_token"]}, format="json")
        self.assertEqual(rejected.status_code, 401)

    def test_subscriber_login_rejects_mismatched_identity(self):
        response = self.client.post("/api/auth/subscriber/login/", {"first_name": "Mauvaise", "last_name": "Kambale", "meter_code": "12345678901234567890"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_seeded_alfajiri_demo_subscriber_can_login(self):
        response = self.client.post("/api/auth/subscriber/login/", {"first_name": "Ndabereye", "last_name": "ALFAJIRI", "meter_code": "16985283257989916672"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["subscriber"]["meter_id"], "VSF-DEMO-ALF-001")

    def test_relay_command_waits_for_signed_telemetry_acknowledgement(self):
        self.client.force_authenticate(self.user)
        command = self.client.post("/api/relay/commands/", {"desired_state": "OFF"}, format="json")
        self.assertEqual(command.status_code, 202)
        self.assertEqual(command.data["status"], "PENDING")
        self.assertTrue(RelayCommand.objects.filter(meter=self.meter, status="PENDING").exists())

        response = self.ingest(make_payload(relay_status=False))
        self.assertEqual(response.status_code, 202)
        command_record = RelayCommand.objects.get(id=command.data["id"])
        self.assertEqual(command_record.status, RelayCommand.APPLIED)
        self.assertIsNotNone(command_record.acknowledged_at)

    def test_auto_relay_cutoff_when_balance_empty(self):
        response = self.ingest(make_payload(balance_kwh=0.0, relay_status=True))
        self.assertEqual(response.status_code, 202)
        self.meter.refresh_from_db()
        self.assertEqual(self.meter.relay_status, "OFF")
        self.assertIsNotNone(response.data.get("relay_command"))
        self.assertEqual(response.data["relay_command"]["desired_state"], "OFF")

    def test_auto_relay_restore_after_recharge(self):
        self.ingest(make_payload(balance_kwh=0.0, relay_status=True))
        self.meter.refresh_from_db()
        self.assertEqual(self.meter.relay_status, "OFF")
        # Recharge suffisante -> rétablissement automatique
        response = self.ingest(make_payload(balance_kwh=20.0, relay_status=False))
        self.assertEqual(response.status_code, 202)
        self.meter.refresh_from_db()
        self.assertEqual(self.meter.relay_status, "ON")

    def test_telemetry_rejects_duplicate_message_id(self):
        payload = make_payload()
        first = self.ingest(payload)
        self.assertEqual(first.status_code, 202)
        second = self.ingest(payload)
        self.assertEqual(second.status_code, 409)

    def test_telemetry_rejects_invalid_signature(self):
        response = APIClient().post("/api/iot/telemetry", make_payload(), format="json", HTTP_X_VIRUNGA_SIGNATURE="deadbeef")
        self.assertEqual(response.status_code, 401)

    def test_anomaly_detection_on_overvoltage(self):
        response = self.ingest(make_payload(voltage=260.0, power=480.0))
        self.assertEqual(response.status_code, 202)
        self.assertTrue(Alert.objects.filter(meter=self.meter, kind="SURTENSION").exists())

    def test_manual_token_flow_with_anti_replay(self):
        # Émission par l'admin (revendeur)
        self.client.force_authenticate(self.admin)
        issued = self.client.post("/api/recharges/manual/issue/", {"meter_id": "VSF-000001", "energy_kwh": 10}, format="json")
        self.assertEqual(issued.status_code, 201)
        token = issued.data["token"]
        self.assertTrue(token.startswith("VSE."))
        # Un abonné non-admin ne peut pas émettre
        self.client.force_authenticate(self.user)
        forbidden = self.client.post("/api/recharges/manual/issue/", {"meter_id": "VSF-000001", "energy_kwh": 10}, format="json")
        self.assertEqual(forbidden.status_code, 403)
        # Application par l'abonné (saisie clavier simulée)
        applied = self.client.post("/api/recharges/manual/apply/", {"token": token}, format="json")
        self.assertEqual(applied.status_code, 202)
        self.assertEqual(applied.data["source"], "SAISIE_MANUELLE")
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 28.42, places=2)
        # Anti-rejeu : le même token est refusé
        replayed = self.client.post("/api/recharges/manual/apply/", {"token": token}, format="json")
        self.assertEqual(replayed.status_code, 409)

    def test_manual_token_rejects_tampered_signature(self):
        self.client.force_authenticate(self.admin)
        issued = self.client.post("/api/recharges/manual/issue/", {"meter_id": "VSF-000001", "energy_kwh": 5}, format="json")
        token = issued.data["token"]
        parts = token.split(".")
        tampered = f"{parts[0]}.{parts[1]}.{'0' * 64}"
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/recharges/manual/apply/", {"token": tampered}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_flutterwave_webhook_signature_and_idempotence(self):
        with patch.dict(os.environ, {"FLW_SECRET_HASH": "hash-test"}):
            client = APIClient()
            body = {"webhook_id": "evt-001", "event": "charge.success", "data": {"id": 7, "status": "successful", "tx_ref": "ref-xyz"}}
            ok = client.post("/api/payments/flutterwave/webhook/", body, format="json", HTTP_VERIF_HASH="hash-test")
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.data["received"], True)
            # Rejeu : idempotent (toujours 1 événement en base)
            client.post("/api/payments/flutterwave/webhook/", body, format="json", HTTP_VERIF_HASH="hash-test")
            self.assertEqual(PaymentEvent.objects.filter(event_id="flutterwave:evt-001").count(), 1)
            # Mauvaise signature
            bad = client.post("/api/payments/flutterwave/webhook/", body, format="json", HTTP_VERIF_HASH="wrong")
            self.assertEqual(bad.status_code, 401)

    def test_flutterwave_webhook_completes_pending_recharge(self):
        Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_PENDING, applied_at=None, provider_reference="ref-abc")
        with patch.dict(os.environ, {"FLW_SECRET_HASH": "hash-test"}):
            body = {"webhook_id": "evt-c1", "event": "charge.success", "data": {"id": 1, "status": "successful", "tx_ref": "ref-abc"}}
            response = APIClient().post("/api/payments/flutterwave/webhook/", body, format="json", HTTP_VERIF_HASH="hash-test")
        self.assertEqual(response.status_code, 200)
        recharge = Recharge.objects.get(provider_reference="ref-abc")
        self.assertEqual(recharge.status, Recharge.STATUS_APPLIED)
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 28.42, places=2)

    def test_flutterwave_redirect_verify_completes_pending(self):
        Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_PENDING, applied_at=None, provider_reference="ref-verify-1")
        # Statut de redirection favorable, sans clé ni transaction_id → complète (fonctionne en local).
        response = self.client.get("/api/payments/flutterwave/verify/?tx_ref=ref-verify-1&status=successful")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "confirmé")
        recharge = Recharge.objects.get(provider_reference="ref-verify-1")
        self.assertEqual(recharge.status, Recharge.STATUS_APPLIED)
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 28.42, places=2)

    def test_flutterwave_redirect_verify_uses_api_when_secret_provided(self):
        Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_PENDING, applied_at=None, provider_reference="ref-verify-2")
        from energy import views as views_mod
        with patch.dict(os.environ, {"FLUTTERWAVE_SECRET_KEY": "sk-test"}, clear=False):
            with patch.object(views_mod, "_http_get_json", return_value=(200, {"status": "success", "data": {"status": "successful", "amount": "10.00", "currency": "USD"}})):
                # Statut de redirection "failed", mais l'API Flutterwave confirme "successful" → complète.
                response = self.client.get("/api/payments/flutterwave/verify/?tx_ref=ref-verify-2&transaction_id=7&status=failed")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "confirmé")
        recharge = Recharge.objects.get(provider_reference="ref-verify-2")
        self.assertEqual(recharge.status, Recharge.STATUS_APPLIED)

    def test_payment_initiate_without_sandbox_keys_is_explicit(self):
        with patch.dict(os.environ, {"PAWAPAY_SANDBOX_TOKEN": ""}, clear=False):
            self.client.force_authenticate(self.user)
            response = self.client.post("/api/payments/initiate/", {"provider": "pawapay", "amount_cdf": 5000, "phone_number": "993456789", "network": "ORANGE_COD"}, format="json")
            self.assertEqual(response.status_code, 503)
            self.assertIn("Aucun paiement n'a été débité", response.data["detail"])

    def test_pawapay_initiate_requires_phone_number(self):
        # Sans numéro de téléphone, un paiement PawaPay est refusé explicitement (pas de paiement silencieux).
        with patch.dict(os.environ, {"PAWAPAY_SANDBOX_TOKEN": "tok"}, clear=False):
            self.client.force_authenticate(self.user)
            response = self.client.post("/api/payments/initiate/", {"provider": "pawapay", "amount_cdf": 5000}, format="json")
            self.assertEqual(response.status_code, 400)

    def test_pawapay_callback_completes_pending_recharge_and_idempotent(self):
        Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_PENDING, applied_at=None, provider_reference="deposit-123")
        body = {
            "depositId": "deposit-123",
            "status": "COMPLETED",
            "requestedAmount": "5000",
            "currency": "CDF",
            "country": "COD",
            "payer": {"type": "MMO", "accountDetails": {"provider": "ORANGE_COD", "phoneNumber": "243993456789"}},
            "customerMessage": "Paiement de 5000 FC reçu",
            "amount": "5000",
            "providerTransactionId": "tx-1",
        }
        client = APIClient()
        first = client.post("/api/payments/pawapay/callback/", body, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(PaymentEvent.objects.filter(event_id="pawapay:deposit-123").count(), 1)
        recharge = Recharge.objects.get(provider_reference="deposit-123")
        self.assertEqual(recharge.status, Recharge.STATUS_APPLIED)
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 28.42, places=2)
        # Rejeu -> pas de double crédit (idempotence)
        second = client.post("/api/payments/pawapay/callback/", body, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(PaymentEvent.objects.filter(event_id="pawapay:deposit-123").count(), 1)
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 28.42, places=2)

    def test_pawapay_callback_missing_deposit_id_rejected(self):
        response = APIClient().post("/api/payments/pawapay/callback/", {"status": "COMPLETED"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_receipt_pdf_is_real(self):
        recharge = Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_APPLIED, applied_at=timezone.now())
        self.client.force_authenticate(self.user)
        response = self.client.get(f"/api/receipts/{recharge.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        content = b"".join(response.streaming_content) if hasattr(response, "streaming_content") else response.content
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertGreater(len(content), 500)
        self.assertTrue(content.rstrip().endswith(b"%%EOF"))

    def test_receipt_forbidden_for_other_subscriber(self):
        recharge = Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_APPLIED, applied_at=timezone.now())
        other = User.objects.create_user(username="other")
        self.client.force_authenticate(other)
        response = self.client.get(f"/api/receipts/{recharge.id}/")
        self.assertEqual(response.status_code, 403)

    def test_assistant_answers_from_real_data_only(self):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/assistant/", {"question": "Quel est mon solde ?"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("18.42 kWh", response.data["answer"])
        # Question hors périmètre -> refus honnête
        response = self.client.post("/api/assistant/", {"question": "Donne-moi le numéro de téléphone du président de la RDC"}, format="json")
        self.assertIn("Je ne peux pas", response.data["answer"])

    def test_admin_endpoint_rejects_subscriber(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/admin/overview/")
        self.assertEqual(response.status_code, 403)

    def test_admin_endpoint_returns_real_overview(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/admin/overview/")
        self.assertEqual(response.status_code, 200)
        # Valeurs réelles (le seed ALFAJIRI de la migration 0003 s'ajoute au meter du setUp)
        self.assertEqual(response.data["totalMeters"], Meter.objects.count())
        self.assertEqual(response.data["onlineMeters"], Meter.objects.filter(device_status="ONLINE").count())
        self.assertIn("Goma — Karisimbi", [sector["name"] for sector in response.data["sectors"]])

    def test_news_exposes_only_published_articles_and_requires_admin_to_create(self):
        NewsArticle.objects.create(title="Maintenance interne", summary="Non publiée", category="Maintenance", territory="Goma", is_published=False)
        published = NewsArticle.objects.create(title="Extension réseau", summary="Information publiée", category="Projet", territory="Rutshuru", is_published=True, published_at=timezone.now())
        public_news = self.client.get("/api/news/")
        self.assertEqual(public_news.status_code, 200)
        self.assertEqual([article["id"] for article in public_news.data], [published.id])
        self.client.force_authenticate(self.user)
        forbidden = self.client.post("/api/news/", {"title": "Sans droit", "summary": "Test", "category": "Projet", "territory": "Goma"}, format="json")
        self.assertEqual(forbidden.status_code, 403)
        self.client.force_authenticate(self.admin)
        created = self.client.post("/api/news/", {"title": "Mise à jour réseau", "summary": "Maintenance planifiée", "category": "Maintenance", "territory": "Goma", "is_published": True, "published_at": timezone.now().isoformat()}, format="json")
        self.assertEqual(created.status_code, 201)


class TelemetryContractTests(TestCase):
    def test_serializer_accepts_valid_contract_payload(self):
        serializer = TelemetryPayloadSerializer(data=make_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_serializer_rejects_incoherent_power(self):
        serializer = TelemetryPayloadSerializer(data=make_payload(power=1000.0))
        self.assertFalse(serializer.is_valid())

    def test_serializer_rejects_stale_timestamp(self):
        stale = timezone.now() - timezone.timedelta(minutes=30)
        serializer = TelemetryPayloadSerializer(data=make_payload(device_timestamp=stale.isoformat()))
        self.assertFalse(serializer.is_valid())

    def test_serializer_rejects_implausible_voltage(self):
        serializer = TelemetryPayloadSerializer(data=make_payload(voltage=500.0))
        self.assertFalse(serializer.is_valid())

    def test_serializer_requires_contract_fields(self):
        payload = make_payload()
        del payload["firmware_version"]
        serializer = TelemetryPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("firmware_version", serializer.errors)


class AdminNoFabricationTests(TestCase):
    def test_empty_database_reports_zero_not_fabricated_numbers(self):
        User.objects.create_user(username="administrator", is_staff=True)
        # Base vidée : les seuls compteurs présents sont ceux du seed de migration, qu'on retire
        Meter.objects.all().delete()
        Sector.objects.all().delete()
        client = APIClient()
        client.force_authenticate(User.objects.get(username="administrator"))
        response = client.get("/api/admin/overview/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["totalMeters"], 0)
        self.assertEqual(response.data["onlineMeters"], 0)
        self.assertEqual(response.data["lowBalanceMeters"], 0)
        self.assertEqual(response.data["sectors"], [])


class ChannelsIntegrationTests(TestCase):
    def test_telemetry_websocket_announces_https_ingestion(self):
        async def run():
            communicator = WebsocketCommunicator(application, "/ws/telemetry/")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            message = await communicator.receive_json_from()
            self.assertFalse(message["mqtt"])
            self.assertIn("HTTPS POST", message["ingestion"])
            await communicator.disconnect()

        async_to_sync(run)()


class FrontendStaticFileTests(TestCase):
    def test_frontend_file_serves_compiled_asset_inside_public_root(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            public_root = project_root / "dist" / "public" / "assets"
            public_root.mkdir(parents=True)
            asset = public_root / "app.js"
            asset.write_text("console.log('asset')", encoding="utf-8")
            with patch("config.urls.settings.BASE_DIR", project_root / "backend"):
                response = frontend_file(self.client.get("/").wsgi_request, "assets/app.js")
                self.assertEqual(response["Content-Disposition"], 'inline; filename="app.js"')
                response.close()  # libère le fichier (indispensable sous Windows)
