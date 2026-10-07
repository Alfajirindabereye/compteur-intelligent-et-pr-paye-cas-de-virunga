from django.db import migrations


METER_ID = "VSF-DEMO-ALF-001"
METER_CODE = "16985283257989916672"


def create_demo_subscriber(apps, schema_editor):
    Sector = apps.get_model("energy", "Sector")
    Meter = apps.get_model("energy", "Meter")
    sector, _ = Sector.objects.get_or_create(name="Goma — Démonstration", defaults={"territory": "Goma"})
    Meter.objects.update_or_create(
        meter_id=METER_ID,
        defaults={
            "sector": sector,
            "subscriber_code": METER_CODE,
            "subscriber_first_name": "Ndabereye",
            "subscriber_last_name": "ALFAJIRI",
            "voltage_v": 220.4,
            "current_a": 2.31,
            "power_w": 508.2,
            "energy_kwh": 0.084,
            "balance_kwh": 18.42,
            "relay_status": "ON",
            "signal_gsm": 86,
            "device_status": "ONLINE",
        },
    )


def remove_demo_subscriber(apps, schema_editor):
    Meter = apps.get_model("energy", "Meter")
    Meter.objects.filter(meter_id=METER_ID, subscriber_code=METER_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("energy", "0002_subscribers_relay_news"),
    ]

    operations = [
        migrations.RunPython(create_demo_subscriber, remove_demo_subscriber),
    ]
