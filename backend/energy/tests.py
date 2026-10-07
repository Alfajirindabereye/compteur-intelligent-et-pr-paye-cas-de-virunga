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
        # Le crédit de référence et les compteurs de limitation vivent en cache : état neuf par test.
        from django.core.cache import cache
        cache.clear()

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

    def test_recharge_survives_next_telemetry_and_is_delivered_once(self):
        # Le compteur rapporte son solde local (18.42) : il ignore encore la recharge serveur.
        from .services import apply_recharge
        recharge = apply_recharge(self.meter, "SAISIE_MANUELLE", 10, timezone.now())
        first = self.ingest(make_payload(balance_kwh=18.42))
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.data["credits"], [{"id": recharge.id, "energy_kwh": 10.0}])
        self.assertAlmostEqual(first.data["balance_kwh"], 28.42, places=2)
        # Réponse perdue : le compteur renvoie son solde inchangé, le crédit lui est proposé à nouveau.
        lost = self.ingest(make_payload(balance_kwh=18.41))
        self.assertEqual(lost.data["credits"], [{"id": recharge.id, "energy_kwh": 10.0}])
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 28.41, places=2)
        # Le compteur a intégré le crédit et l'accuse : pas de second versement.
        acked = self.ingest(make_payload(balance_kwh=28.40, credit_acks=[recharge.id]))
        self.assertEqual(acked.data["credits"], [])
        self.assertEqual(acked.data["credit_kwh"], 0.0)
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 28.40, places=2)
        recharge.refresh_from_db()
        self.assertIsNotNone(recharge.delivered_at)
        # Un accusé rejoué ou visant la recharge d'un autre compteur est sans effet.
        again = self.ingest(make_payload(balance_kwh=28.39, credit_acks=[recharge.id, 999999]))
        self.assertEqual(again.status_code, 202)
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 28.39, places=2)

    def test_degressive_credit_alerts_fire_once_per_threshold_and_cycle(self):
        from .services import apply_recharge

        def kinds():
            return sorted(Alert.objects.filter(meter=self.meter, kind__startswith="CREDIT_SEUIL_").values_list("kind", flat=True))

        self.ingest(make_payload(balance_kwh=18.42))          # plein du cycle : 100 %
        self.assertEqual(kinds(), [])
        self.ingest(make_payload(balance_kwh=3.0))            # 16,3 % : encore au-dessus de 15 %
        self.assertEqual(kinds(), [])
        self.ingest(make_payload(balance_kwh=2.5))            # 13,6 % -> seuil 15
        self.assertEqual(kinds(), ["CREDIT_SEUIL_15"])
        self.ingest(make_payload(balance_kwh=2.4))            # toujours dans la tranche : pas de doublon
        self.assertEqual(kinds(), ["CREDIT_SEUIL_15"])
        self.ingest(make_payload(balance_kwh=1.7))            # 9,2 % -> seuil 10
        self.ingest(make_payload(balance_kwh=0.9))            # 4,9 % -> seuil 5
        self.ingest(make_payload(balance_kwh=0.5))            # 2,7 % -> seuil 3
        self.ingest(make_payload(balance_kwh=0.1))            # 0,5 % -> seuil 1
        self.ingest(make_payload(balance_kwh=0.05))
        self.assertEqual(kinds(), sorted(f"CREDIT_SEUIL_{t}" for t in (15, 10, 5, 3, 1)))
        severities = dict(Alert.objects.filter(meter=self.meter, kind__startswith="CREDIT_SEUIL_").values_list("kind", "severity"))
        self.assertEqual(severities["CREDIT_SEUIL_15"], "WARNING")
        self.assertEqual(severities["CREDIT_SEUIL_3"], "CRITICAL")

        # Nouvelle recharge = nouveau cycle : la référence repart du nouveau plein, les seuils se réarment.
        recharge = apply_recharge(self.meter, "SAISIE_MANUELLE", 10, timezone.now())
        self.ingest(make_payload(balance_kwh=10.05, credit_acks=[recharge.id]))
        self.assertEqual(len(kinds()), 5)
        self.ingest(make_payload(balance_kwh=1.2))            # 11,9 % du nouveau plein -> seuil 15 à nouveau
        self.assertEqual(kinds().count("CREDIT_SEUIL_15"), 2)

        self.client.force_authenticate(self.user)
        dashboard = self.client.get("/api/dashboard/").data
        self.assertEqual(dashboard["credit"]["threshold"], 15)
        self.assertEqual(dashboard["credit"]["thresholds"], [15, 10, 5, 3, 1])
        self.assertAlmostEqual(dashboard["credit"]["percent"], 11.9, places=1)

    def test_credit_alert_is_pushed_by_email_sms_and_whatsapp(self):
        from django.core import mail
        from django.test import override_settings

        from energy import notifications

        self.meter.subscriber_email = "amani.kambale@example.com"
        self.meter.subscriber_phone = "0993 456 789"
        self.meter.save()
        twilio = {"TWILIO_ACCOUNT_SID": "ACtest", "TWILIO_AUTH_TOKEN": "secret", "TWILIO_SMS_FROM": "+15005550006", "TWILIO_WHATSAPP_FROM": "+14155238886",
                  "WHATSAPP_CLOUD_TOKEN": "", "WHATSAPP_PHONE_NUMBER_ID": ""}
        with override_settings(EMAIL_HOST_USER="alertes@gmail.com", EMAIL_HOST_PASSWORD="app-password"), \
                patch.dict(os.environ, twilio, clear=False), \
                patch.object(notifications, "_post", return_value=(201, {"sid": "SM1"})) as post:
            self.ingest(make_payload(balance_kwh=18.42))
            self.assertEqual(post.call_count, 0)              # au-dessus de 15 % : aucun envoi
            self.ingest(make_payload(balance_kwh=2.5))        # franchit 15 %
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].to, ["amani.kambale@example.com"])
            self.assertIn("seuil 15 %", mail.outbox[0].body)
            sent = [dict(item.split("=", 1) for item in call.args[2].decode().split("&")) for call in post.call_args_list]
            self.assertEqual(sorted(item["To"] for item in sent), ["%2B243993456789", "whatsapp%3A%2B243993456789"])
            self.ingest(make_payload(balance_kwh=2.4))        # même tranche : pas de nouvel envoi
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(post.call_count, 2)

            # Meta Cloud API prioritaire quand elle est configurée
            with patch.dict(os.environ, {"WHATSAPP_CLOUD_TOKEN": "meta-token", "WHATSAPP_PHONE_NUMBER_ID": "1234"}, clear=False):
                self.ingest(make_payload(balance_kwh=1.7))    # franchit 10 %
            meta_calls = [call for call in post.call_args_list if "graph.facebook.com" in call.args[0]]
            self.assertEqual(len(meta_calls), 1)
            self.assertEqual(json.loads(meta_calls[0].args[2])["to"], "243993456789")

    def test_unconfigured_channels_are_reported_never_faked(self):
        from energy import notifications

        self.meter.subscriber_phone = "0993456789"
        self.meter.save()
        empty = {name: "" for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_SMS_FROM", "TWILIO_WHATSAPP_FROM", "WHATSAPP_CLOUD_TOKEN", "WHATSAPP_PHONE_NUMBER_ID")}
        self.client.force_authenticate(self.user)
        with patch.dict(os.environ, empty, clear=False), patch.object(notifications, "_post") as post:
            response = self.client.post("/api/notifications/test/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], {"email": "not_configured", "sms": "not_configured", "whatsapp": "not_configured"})
        post.assert_not_called()
        # Un prestataire qui refuse l'envoi est rapporté comme une erreur, pas comme un succès.
        with patch.dict(os.environ, {**empty, "TWILIO_ACCOUNT_SID": "ACtest", "TWILIO_AUTH_TOKEN": "secret", "TWILIO_SMS_FROM": "+15005550006"}, clear=False), \
                patch.object(notifications, "_post", return_value=(401, {"message": "Authenticate"})):
            response = self.client.post("/api/notifications/test/", {}, format="json")
        self.assertTrue(response.data["results"]["sms"].startswith("error: Twilio HTTP 401"))

    def test_profile_update_and_alert_acknowledgement(self):
        self.client.force_authenticate(self.user)
        saved = self.client.post("/api/profile/", {"email": "amani@example.com", "phone": "+243 993 456 789"}, format="json")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data["email"], "amani@example.com")
        self.assertIn(saved.data["channels"]["sms"], ("ready", "not_configured"))
        self.assertEqual(self.client.post("/api/profile/", {"phone": "12"}, format="json").status_code, 400)
        self.meter.refresh_from_db()
        self.assertEqual(self.meter.subscriber_phone, "+243 993 456 789")

        self.ingest(make_payload(voltage=260.0, power=480.0))
        alert = Alert.objects.get(meter=self.meter, kind="SURTENSION")
        listed = self.client.get("/api/dashboard/").data["alerts"]
        self.assertIn(alert.id, [item["id"] for item in listed])
        self.assertEqual(self.client.post(f"/api/alerts/{alert.id}/ack/", {}, format="json").status_code, 200)
        self.assertNotIn(alert.id, [item["id"] for item in self.client.get("/api/dashboard/").data["alerts"]])
        # Une alerte acquittée ne renaît pas à la télémétrie suivante.
        self.ingest(make_payload(voltage=261.0, power=480.0))
        self.assertEqual(Alert.objects.filter(meter=self.meter, kind="SURTENSION").count(), 1)
        # L'alerte d'un autre compteur est introuvable pour cet abonné.
        other = Alert.objects.create(meter=Meter.objects.get(pk="VSF-DEMO-ALF-001"), kind="SURTENSION", severity="CRITICAL", message="x")
        self.assertEqual(self.client.post(f"/api/alerts/{other.id}/ack/", {}, format="json").status_code, 404)

    def test_admin_login_issues_token_only_for_staff_accounts(self):
        import jwt as pyjwt

        from .authentication import jwt_secret

        User.objects.create_user(username="chef", password="mot-de-passe-solide", is_staff=True)
        User.objects.create_user(username="simple", password="mot-de-passe-solide")
        client = APIClient()
        self.assertEqual(client.post("/api/auth/admin/login/", {"username": "chef", "password": "faux"}, format="json").status_code, 401)
        self.assertEqual(client.post("/api/auth/admin/login/", {"username": "simple", "password": "mot-de-passe-solide"}, format="json").status_code, 401)
        login = client.post("/api/auth/admin/login/", {"username": "chef", "password": "mot-de-passe-solide"}, format="json")
        self.assertEqual(login.status_code, 200)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access_token']}")
        self.assertEqual(client.get("/api/admin/overview/").status_code, 200)
        issued = client.post("/api/recharges/manual/issue/", {"meter_id": "VSF-000001", "energy_kwh": 5}, format="json")
        self.assertEqual(issued.status_code, 201)
        # Un jeton portant le rôle administrateur pour un compte qui ne l'est pas reste sans pouvoir.
        forged = pyjwt.encode({"sub": "simple", "domain_role": "administrateur", "exp": timezone.now() + timezone.timedelta(hours=1)}, jwt_secret(), algorithm="HS256")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {forged}")
        self.assertEqual(client.get("/api/admin/overview/").status_code, 403)
        # Le jeton d'un abonné n'ouvre pas la supervision.
        subscriber = self.client.post("/api/auth/subscriber/login/", {"first_name": "Amani", "last_name": "Kambale", "meter_code": "12345678901234567890"}, format="json")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {subscriber.data['access_token']}")
        self.assertEqual(client.get("/api/admin/overview/").status_code, 403)

    def test_recharge_restores_relay_of_cut_meter_through_telemetry(self):
        from .services import apply_recharge
        self.ingest(make_payload(balance_kwh=0.0, relay_status=True))
        apply_recharge(self.meter, "SAISIE_MANUELLE", 5, timezone.now())
        # Le compteur, toujours coupé et à solde local nul, reçoit le crédit et l'ordre de rétablissement.
        response = self.ingest(make_payload(balance_kwh=0.0, relay_status=False, power=0.0, current=0.0))
        self.assertAlmostEqual(response.data["credit_kwh"], 5.0, places=3)
        self.assertEqual(response.data["relay_command"]["desired_state"], "ON")

    def test_subscriber_isolation_is_sent_to_meter_and_held(self):
        self.client.force_authenticate(self.user)
        command = self.client.post("/api/relay/commands/", {"desired_state": "OFF"}, format="json")
        # Le compteur, encore alimenté, reçoit l'ordre de l'abonné dans la réponse de télémétrie.
        response = self.ingest(make_payload(relay_status=True))
        self.assertEqual(response.data["relay_command"], {"command_id": str(command.data["id"]), "desired_state": "OFF", "reason": "commande_abonne"})
        # Une fois exécuté, l'isolement tient malgré un solde positif.
        response = self.ingest(make_payload(relay_status=False))
        self.assertIsNone(response.data["relay_command"])
        self.assertEqual(RelayCommand.objects.get(id=command.data["id"]).status, RelayCommand.APPLIED)
        self.meter.refresh_from_db()
        self.assertEqual(self.meter.relay_status, "OFF")
        # Le rétablissement demandé par l'abonné est transmis à son tour.
        self.client.post("/api/relay/commands/", {"desired_state": "ON"}, format="json")
        response = self.ingest(make_payload(relay_status=False))
        self.assertEqual(response.data["relay_command"]["desired_state"], "ON")

    def test_relay_restore_refused_without_balance(self):
        self.ingest(make_payload(balance_kwh=0.0, relay_status=True))
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/relay/commands/", {"desired_state": "ON"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(RelayCommand.objects.filter(meter=self.meter).exists())

    def test_budget_update_raises_alert_instead_of_crashing(self):
        from datetime import timedelta
        from decimal import Decimal

        from .models import Telemetry

        now = timezone.now()
        Telemetry.objects.bulk_create([
            Telemetry(meter=self.meter, message_id=str(uuid.uuid4()), applied_at=now - timedelta(hours=hours_ago),
                      voltage_v=Decimal("220"), current_a=Decimal("2"), power_w=Decimal("440"),
                      energy_kwh=Decimal(str(energy)), balance_kwh=Decimal("18.42"), relay_status="ON", signal_gsm=70)
            for hours_ago, energy in ((3, 10.0), (1, 16.0))
        ])
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/budget/", {"limit_kwh": 5}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["limit_kwh"], 5.0)
        self.assertTrue(Alert.objects.filter(meter=self.meter, kind="DEPASSEMENT_BUDGET").exists())
        self.assertEqual(self.client.get("/api/budget/").data["limit_kwh"], 5.0)
        self.assertEqual(self.client.post("/api/budget/", {"limit_kwh": "abc"}, format="json").status_code, 400)

    def test_refresh_token_cannot_be_used_as_access_token(self):
        login = self.client.post("/api/auth/subscriber/login/", {"first_name": "Amani", "last_name": "Kambale", "meter_code": "12345678901234567890"}, format="json")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['refresh_token']}")
        self.assertIn(client.get("/api/dashboard/").status_code, (401, 403))

    def test_manual_token_response_reports_new_balance(self):
        self.client.force_authenticate(self.admin)
        token = self.client.post("/api/recharges/manual/issue/", {"meter_id": "VSF-000001", "energy_kwh": 10}, format="json").data["token"]
        self.client.force_authenticate(self.user)
        applied = self.client.post("/api/recharges/manual/apply/", {"token": token}, format="json")
        self.assertAlmostEqual(applied.data["balance_kwh"], 28.42, places=2)
        self.assertAlmostEqual(applied.data["energy_kwh"], 10.0, places=3)

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
            body = {"webhook_id": "evt-c1", "event": "charge.completed", "data": {"id": 1, "status": "successful", "tx_ref": "ref-abc", "amount": 10, "currency": "USD"}}
            response = APIClient().post("/api/payments/flutterwave/webhook/", body, format="json", HTTP_VERIF_HASH="hash-test")
        self.assertEqual(response.status_code, 200)
        recharge = Recharge.objects.get(provider_reference="ref-abc")
        self.assertEqual(recharge.status, Recharge.STATUS_APPLIED)
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 28.42, places=2)

    def test_flutterwave_webhook_ignores_underpaid_or_failed_charge(self):
        Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_PENDING, applied_at=None, provider_reference="ref-low")
        with patch.dict(os.environ, {"FLW_SECRET_HASH": "hash-test"}):
            client = APIClient()
            # Montant payé (1 USD) inférieur au prix des 10 kWh demandés
            underpaid = {"webhook_id": "evt-low", "event": "charge.completed", "data": {"id": 2, "status": "successful", "tx_ref": "ref-low", "amount": 1, "currency": "USD"}}
            self.assertEqual(client.post("/api/payments/flutterwave/webhook/", underpaid, format="json", HTTP_VERIF_HASH="hash-test").status_code, 200)
            # Paiement échoué, même si le type d'événement évoque un succès
            failed = {"webhook_id": "evt-ko", "event": "charge.success", "data": {"id": 3, "status": "failed", "tx_ref": "ref-low", "amount": 10, "currency": "USD"}}
            self.assertEqual(client.post("/api/payments/flutterwave/webhook/", failed, format="json", HTTP_VERIF_HASH="hash-test").status_code, 200)
        self.assertEqual(Recharge.objects.get(provider_reference="ref-low").status, Recharge.STATUS_PENDING)
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 18.42, places=2)

    def test_flutterwave_redirect_never_credits_on_url_parameters_alone(self):
        Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_PENDING, applied_at=None, provider_reference="ref-verify-1")
        # « status=successful » est écrit par le navigateur : sans vérification serveur à serveur, aucun crédit.
        for url in (
            "/api/payments/flutterwave/verify/?tx_ref=ref-verify-1&status=successful",
            "/api/payments/flutterwave/verify/?tx_ref=ref-verify-1&status=successful&transaction_id=7",
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Aucun crédit")
        with patch.dict(os.environ, {"FLUTTERWAVE_SECRET_KEY": "sk-test"}, clear=False):
            # Clé présente mais pas d'identifiant de transaction à vérifier : toujours aucun crédit.
            response = self.client.get("/api/payments/flutterwave/verify/?tx_ref=ref-verify-1&status=successful")
            self.assertContains(response, "Aucun crédit")
        self.assertEqual(Recharge.objects.get(provider_reference="ref-verify-1").status, Recharge.STATUS_PENDING)
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 18.42, places=2)

    def test_flutterwave_redirect_verify_uses_api_when_secret_provided(self):
        Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_PENDING, applied_at=None, provider_reference="ref-verify-2")
        from energy import views as views_mod
        with patch.dict(os.environ, {"FLUTTERWAVE_SECRET_KEY": "sk-test"}, clear=False):
            with patch.object(views_mod, "_http_get_json", return_value=(200, {"status": "success", "data": {"status": "successful", "tx_ref": "ref-verify-2", "amount": "10.00", "currency": "USD"}})):
                # Statut de redirection "failed", mais l'API Flutterwave confirme "successful" → complète.
                response = self.client.get("/api/payments/flutterwave/verify/?tx_ref=ref-verify-2&transaction_id=7&status=failed")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "confirmé")
        recharge = Recharge.objects.get(provider_reference="ref-verify-2")
        self.assertEqual(recharge.status, Recharge.STATUS_APPLIED)

    def test_flutterwave_redirect_rejects_other_transaction_or_lower_amount(self):
        Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_PENDING, applied_at=None, provider_reference="ref-verify-3")
        from energy import views as views_mod
        confirmations = [
            {"status": "successful", "tx_ref": "une-autre-reference", "amount": "10.00", "currency": "USD"},
            {"status": "successful", "tx_ref": "ref-verify-3", "amount": "0.50", "currency": "USD"},
            {"status": "successful", "tx_ref": "ref-verify-3", "amount": "10.00", "currency": "NGN"},
        ]
        with patch.dict(os.environ, {"FLUTTERWAVE_SECRET_KEY": "sk-test"}, clear=False):
            for data in confirmations:
                with patch.object(views_mod, "_http_get_json", return_value=(200, {"status": "success", "data": data})):
                    response = self.client.get("/api/payments/flutterwave/verify/?tx_ref=ref-verify-3&transaction_id=7&status=successful")
                self.assertContains(response, "Aucun crédit")
        self.assertEqual(Recharge.objects.get(provider_reference="ref-verify-3").status, Recharge.STATUS_PENDING)

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
            "amount": "25000",
            "currency": "CDF",
            "country": "COD",
            "payer": {"type": "MMO", "accountDetails": {"provider": "ORANGE_COD", "phoneNumber": "243993456789"}},
            "customerMessage": "Paiement de 25000 FC reçu",
            "providerTransactionId": "tx-1",
        }
        from energy import views as views_mod
        confirmed = (200, {"status": "FOUND", "data": {"depositId": "deposit-123", "status": "COMPLETED", "amount": "25000", "currency": "CDF"}})
        client = APIClient()
        with patch.dict(os.environ, {"PAWAPAY_SANDBOX_TOKEN": "tok"}, clear=False), patch.object(views_mod, "_http_get_json", return_value=confirmed):
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

    def test_pawapay_forged_callback_does_not_credit(self):
        Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_PENDING, applied_at=None, provider_reference="deposit-forged")
        body = {"depositId": "deposit-forged", "status": "COMPLETED", "amount": "25000", "currency": "CDF"}
        from energy import views as views_mod
        client = APIClient()
        # Sans token : impossible de confirmer chez PawaPay, donc aucun crédit sur la seule foi du callback.
        with patch.dict(os.environ, {"PAWAPAY_SANDBOX_TOKEN": ""}, clear=False):
            self.assertEqual(client.post("/api/payments/pawapay/callback/", body, format="json").status_code, 200)
        # Avec token : PawaPay dit que le dépôt n'est pas finalisé, ou d'un montant inférieur.
        for data in ({"depositId": "deposit-forged", "status": "PROCESSING"},
                     {"depositId": "deposit-forged", "status": "COMPLETED", "amount": "100", "currency": "CDF"}):
            with patch.dict(os.environ, {"PAWAPAY_SANDBOX_TOKEN": "tok"}, clear=False), patch.object(views_mod, "_http_get_json", return_value=(200, {"status": "FOUND", "data": data})):
                self.assertEqual(client.post("/api/payments/pawapay/callback/", body, format="json").status_code, 200)
        self.assertEqual(Recharge.objects.get(provider_reference="deposit-forged").status, Recharge.STATUS_PENDING)
        self.meter.refresh_from_db()
        self.assertAlmostEqual(float(self.meter.balance_kwh), 18.42, places=2)

    def test_pawapay_status_reports_applied_after_callback_and_failure(self):
        from energy import views as views_mod
        self.client.force_authenticate(self.user)
        # Recharge déjà créditée (par le callback) : le polling doit s'arrêter sur « applied ».
        Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_APPLIED, applied_at=timezone.now(), provider_reference="deposit-done")
        done = self.client.get("/api/payments/pawapay/status/deposit-done/")
        self.assertEqual(done.status_code, 200)
        self.assertTrue(done.data["applied"])
        # Dépôt refusé par le réseau : recharge marquée FAILED et signalée au client.
        Recharge.objects.create(meter=self.meter, source="APP_PAIEMENT", energy_kwh=10, status=Recharge.STATUS_PENDING, applied_at=None, provider_reference="deposit-ko")
        with patch.dict(os.environ, {"PAWAPAY_SANDBOX_TOKEN": "tok"}, clear=False), patch.object(views_mod, "_http_get_json", return_value=(200, {"status": "FOUND", "data": {"depositId": "deposit-ko", "status": "FAILED"}})):
            failed = self.client.get("/api/payments/pawapay/status/deposit-ko/")
        self.assertTrue(failed.data["failed"])
        self.assertEqual(Recharge.objects.get(provider_reference="deposit-ko").status, Recharge.STATUS_FAILED)

    def test_pawapay_initiate_uses_uuid_deposit_id_and_fails_rejected_deposit(self):
        from energy import views as views_mod
        self.client.force_authenticate(self.user)
        request_body = {"provider": "pawapay", "amount_cdf": 5000, "phone_number": "0993456789", "network": "ORANGE_COD"}
        with patch.dict(os.environ, {"PAWAPAY_SANDBOX_TOKEN": "tok"}, clear=False):
            with patch.object(views_mod, "_http_post_json", return_value=(200, {"status": "ACCEPTED"})) as post:
                accepted = self.client.post("/api/payments/initiate/", request_body, format="json")
            self.assertEqual(accepted.status_code, 202)
            sent = post.call_args.args[2]
            self.assertEqual(str(uuid.UUID(sent["depositId"])), sent["depositId"])  # exigence PawaPay
            self.assertEqual(sent["payer"]["accountDetails"]["phoneNumber"], "243993456789")
            self.assertEqual(Recharge.objects.get(provider_reference=sent["depositId"]).status, Recharge.STATUS_PENDING)
            with patch.object(views_mod, "_http_post_json", return_value=(200, {"status": "REJECTED"})) as post:
                rejected = self.client.post("/api/payments/initiate/", request_body, format="json")
            self.assertEqual(rejected.status_code, 502)
            # Un dépôt refusé ne laisse pas de recharge en attente indéfiniment
            self.assertEqual(Recharge.objects.get(provider_reference=post.call_args.args[2]["depositId"]).status, Recharge.STATUS_FAILED)

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
