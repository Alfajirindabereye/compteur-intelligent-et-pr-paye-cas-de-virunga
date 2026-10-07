"""Simulateur logiciel de compteur Virunga Smart Energy.

SIMULATEUR — données de démonstration identifiables (le compteur créé est
marqué ``is_demo=True`` et l'interface affiche le mode DEMO).

Ce simulateur utilise le PIPELINE RÉEL : il envoie une télémétrie conforme au
contrat du prompt via HTTPS POST signé (HMAC-SHA256) vers ``/api/iot/telemetry``
toutes les 5 secondes, exactement comme le ferait un compteur ESP32 + GSM.
"""
import json
import math
import os
import random
import time
import urllib.request
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from energy.models import Meter, Recharge, Sector
from energy.services import compute_signature

FIRMWARE_VERSION = "1.0.0"


def seed_demo_history(meter: Meter, hours: int = 168) -> int:
    """Pré-remplit un historique de consommation DEMO (7 jours par défaut).

    Données produites par le simulateur officiel, identifiables via
    ``meter.is_demo`` (l'interface affiche le mode DEMO). Le flux temps réel,
    lui, passe par le pipeline réel (HTTPS POST signé). Le profil de charge
    varie jour/nuit et marque un pic en fin de semaine (vendredi soir et
    week-end), ce qui alimente les camemberts journalier et hebdomadaire.
    """
    from decimal import Decimal
    from energy.models import Telemetry

    now = timezone.now()
    if meter.telemetry.filter(applied_at__gte=now - timedelta(hours=2)).exists():
        return 0  # historique récent déjà présent : ne pas dupliquer

    # Première passe : calculer la consommation simulée heure par heure.
    deltas = []
    for index in range(hours):
        applied_at = now - timedelta(hours=hours - index)
        hour = applied_at.hour
        # Profil de charge réaliste : creux la nuit, pointe le soir.
        cycle = math.sin((hour - 6) / 24 * 2 * math.pi)
        # Fin de semaine plus chargée (vendredi soir et week-end).
        weekend_boost = 1.22 if applied_at.weekday() >= 4 and hour >= 16 else 1.0
        power = max(60.0, 480.0 * (0.55 + 0.45 * cycle) * weekend_boost + random.uniform(-25, 25))
        deltas.append(power / 1000.0)  # 1 heure en kWh

    # L'historique rejoué doit RATTRAPER l'état réel du compteur : l'énergie
    # cumulée démarre 7 jours en arrière et finit à la valeur actuelle, et la
    # balance démarre d'autant plus haut pour finir à la valeur actuelle.
    # Sans cela, le jour courant mélange deux séries (seed + temps réel) et le
    # camembert hebdomadaire afficherait une valeur aberrante.
    total_energy = sum(deltas)
    energy_cumulated = max(float(meter.energy_kwh) - total_energy, 0.0)
    balance = float(meter.balance_kwh) + total_energy

    rows = []
    for index in range(hours):
        applied_at = now - timedelta(hours=hours - index)
        energy_delta = deltas[index]
        energy_cumulated += energy_delta
        balance = max(balance - energy_delta, 0.0)
        voltage = round(220.4 + random.uniform(-3.5, 3.5), 2)
        current = round((energy_delta * 1000.0) / max(voltage, 1), 3)
        rows.append(Telemetry(
            meter=meter,
            message_id=str(uuid.uuid4()),
            applied_at=applied_at,
            voltage_v=Decimal(str(voltage)),
            current_a=Decimal(str(current)),
            power_w=Decimal(str(round(energy_delta * 1000.0, 1))),
            energy_kwh=Decimal(str(round(energy_cumulated, 4))),
            balance_kwh=Decimal(str(round(balance, 3))),
            relay_status="ON" if balance > 0 else "OFF",
            signal_gsm=random.randint(55, 90),
        ))
    Telemetry.objects.bulk_create(rows)

    # Le temps réel reprend exactement là où l'historique se termine.
    meter.energy_kwh = Decimal(str(round(energy_cumulated, 3)))
    meter.balance_kwh = Decimal(str(round(balance, 3)))
    meter.save(update_fields=["energy_kwh", "balance_kwh"])
    return len(rows)


def build_payload(meter_id: str, state: dict) -> dict:
    """Construit un payload conforme au contrat de télémétrie du prompt."""
    payload = {
        "message_id": str(uuid.uuid4()),
        "meter_id": meter_id,
        "device_timestamp": timezone.now().isoformat(),
        "voltage": round(state["voltage"], 2),
        "current": round(state["current"], 3),
        "power": round(state["power"], 1),
        "energy_consumed": round(state["energy_kwh"], 4),
        "balance_kwh": round(state["balance_kwh"], 3),
        "relay_status": state["relay_status"],
        "signal_strength": state["signal_strength"],
        "device_status": "ONLINE",
        "firmware_version": FIRMWARE_VERSION,
    }
    # Accusé de réception des crédits déjà intégrés au solde local.
    if state.get("applied_credits"):
        payload["credit_acks"] = sorted(state["applied_credits"])
    return payload


class Command(BaseCommand):
    help = "Simulateur de compteur : envoie une télémétrie signée toutes les 5 secondes via le pipeline réel."

    def add_arguments(self, parser):
        parser.add_argument("--meter", default="VSE-000001", help="Identifiant du compteur simulé.")
        parser.add_argument("--interval", type=float, default=5.0, help="Intervalle entre deux envois (secondes).")
        parser.add_argument("--count", type=int, default=0, help="Nombre d'envois (0 = illimité).")
        parser.add_argument("--base-url", default=os.getenv("VSE_BASE_URL", "http://127.0.0.1:8000"), help="URL du backend Django.")
        parser.add_argument("--initial-balance", type=float, default=18.42, help="Solde initial du compteur simulé (kWh).")
        parser.add_argument("--no-seed-history", action="store_true", help="Ne pas pré-remplir l'historique de démonstration (7 jours).")

    def handle(self, *args, **options):
        meter_id = options["meter"]
        interval = options["interval"]
        count = options["count"]
        base_url = options["base_url"].rstrip("/")
        endpoint = f"{base_url}/api/iot/telemetry"
        initial_balance = options["initial_balance"]

        if not os.getenv("VIRUNGA_IOT_HMAC_SECRET"):
            self.stderr.write(self.style.ERROR("VIRUNGA_IOT_HMAC_SECRET n'est pas défini : le backend rejettera les payloads."))
            return

        # Le compteur simulé est créé (ou réactivé) avec is_demo=True, identifiable.
        sector, _ = Sector.objects.get_or_create(name="Goma — Démonstration", defaults={"territory": "Goma"})
        existing = Meter.objects.filter(pk=meter_id).first()
        meter, created = Meter.objects.update_or_create(
            meter_id=meter_id,
            defaults={
                "sector": sector,
                "device_status": "ONLINE",
                "is_demo": True,
                "firmware_version": FIRMWARE_VERSION,
                "subscriber_first_name": "Ndabereye",
                "subscriber_last_name": "ALFAJIRI",
                "balance_kwh": float(existing.balance_kwh) if existing and existing.balance_kwh > 0 else initial_balance,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"[SIMULATEUR DEMO] Compteur {meter_id} {'créé' if created else 'existant'} (is_demo=True) — envoi vers {endpoint} toutes les {interval}s"))

        if not options["no_seed_history"]:
            seeded = seed_demo_history(meter)
            if seeded:
                self.stdout.write(self.style.SUCCESS(f"[SIMULATEUR DEMO] Historique de démonstration généré : {seeded} points horaires (7 jours) pour le graphique et les camemberts."))
            else:
                self.stdout.write(self.style.WARNING("[SIMULATEUR DEMO] Historique déjà présent (2 h récentes) : aucune duplication."))

        # Le compteur simulé redémarre dans l'état connu du backend. Les recharges pas encore
        # transmises sont exclues du solde local : elles arriveront par `credit_kwh` à la
        # première télémétrie (sinon elles seraient comptées deux fois).
        meter.refresh_from_db()
        undelivered = sum(
            float(recharge.energy_kwh)
            for recharge in meter.recharges.filter(status=Recharge.STATUS_APPLIED, delivered_at__isnull=True)
        )
        state = {
            "voltage": 220.4,
            "current": 2.31,
            "power": 508.2,
            "energy_kwh": float(meter.energy_kwh),
            "balance_kwh": max(float(meter.balance_kwh) - undelivered, 0.0),
            "relay_status": meter.relay_status == "ON",
            "signal_strength": 76,
            # Crédits intégrés au solde local et pas encore confirmés par le backend.
            "applied_credits": set(),
        }
        sent = 0
        try:
            while count == 0 or sent < count:
                sent += 1
                # Variation réaliste de la charge (profil sinusoïdal + bruit)
                t = time.time()
                power = 350 + 280 * (0.5 + 0.5 * math.sin(t / 30.0)) + random.uniform(-25, 25)
                voltage = 220.4 + random.uniform(-4, 4)
                # Relais ouvert : la tension reste présente en amont, mais aucune charge n'est alimentée.
                if not state["relay_status"]:
                    power = 0.0
                current = power / max(voltage, 1)
                state["power"] = max(power, 0)
                state["voltage"] = max(voltage, 0)
                state["current"] = max(current, 0)
                # W -> kWh : diviser par 1000 (sinon la consommation explose)
                consumed = state["power"] * (interval / 3600.0) / 1000.0
                state["energy_kwh"] += consumed
                # Consommation débitée du solde ; coupure locale immédiate si épuisé.
                # Le rétablissement, lui, vient du backend (relay_command) après une recharge.
                state["balance_kwh"] = max(state["balance_kwh"] - consumed, 0)
                if state["balance_kwh"] <= 0:
                    state["relay_status"] = False
                state["signal_strength"] = max(20, min(95, state["signal_strength"] + random.randint(-3, 3)))

                payload = build_payload(meter_id, state)
                signature = compute_signature(payload)
                request = urllib.request.Request(
                    endpoint,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-Virunga-Signature": signature},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=10) as response:
                        body = json.loads(response.read().decode("utf-8"))
                        http_status = response.status
                    status_line = f"[{sent}] HTTP {http_status} accepted={body.get('accepted')}"
                    # Le compteur applique ce que le backend lui renvoie : crédit des recharges
                    # et ordre de relais (règle de solde ou commande de l'abonné).
                    # Un crédit est appliqué une seule fois (par identifiant), puis accusé dans la
                    # télémétrie suivante ; le backend le renvoie tant qu'il n'a pas reçu l'accusé.
                    listed = set()
                    for credit in body.get("credits") or []:
                        listed.add(credit["id"])
                        if credit["id"] not in state["applied_credits"]:
                            state["applied_credits"].add(credit["id"])
                            state["balance_kwh"] += float(credit["energy_kwh"])
                            status_line += f" credit=+{credit['energy_kwh']} kWh (recharge {credit['id']})"
                    state["applied_credits"] &= listed  # les autres sont confirmés
                    if body.get("relay_command"):
                        state["relay_status"] = body["relay_command"].get("desired_state") == "ON"
                        status_line += f" relay_command={body['relay_command']}"
                    self.stdout.write(self.style.SUCCESS(status_line))
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"Erreur d'envoi : {exc}"))
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nSimulateur arrêté."))
