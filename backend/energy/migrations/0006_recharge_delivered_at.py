from django.db import migrations, models
from django.db.models import F


def mark_existing_recharges_delivered(apps, schema_editor):
    # Les recharges déjà appliquées avant cette migration sont déjà reflétées dans
    # le solde des compteurs : elles ne doivent pas être créditées une seconde fois.
    Recharge = apps.get_model("energy", "Recharge")
    Recharge.objects.filter(status="APPLIED", delivered_at__isnull=True).update(delivered_at=F("synced_at"))


class Migration(migrations.Migration):

    dependencies = [
        ("energy", "0005_meter_subscriber_address_meter_subscriber_email_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="recharge",
            name="delivered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="relaycommand",
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.RunPython(mark_existing_recharges_delivered, migrations.RunPython.noop),
    ]
