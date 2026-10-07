from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("energy", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="meter",
            name="subscriber_code",
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="meter",
            name="subscriber_first_name",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="meter",
            name="subscriber_last_name",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.CreateModel(
            name="NewsArticle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180)),
                ("summary", models.CharField(max_length=600)),
                ("body", models.TextField(blank=True)),
                ("category", models.CharField(max_length=80)),
                ("territory", models.CharField(max_length=80)),
                ("image_url", models.URLField(blank=True)),
                ("source_url", models.URLField(blank=True)),
                ("is_published", models.BooleanField(default=False)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-published_at", "-created_at"]},
        ),
        migrations.CreateModel(
            name="RelayCommand",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("requested_state", models.CharField(choices=[("ON", "ON"), ("OFF", "OFF")], max_length=3)),
                ("status", models.CharField(choices=[("PENDING", "PENDING"), ("APPLIED", "APPLIED"), ("SUPERSEDED", "SUPERSEDED")], default="PENDING", max_length=16)),
                ("requested_by", models.CharField(max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("meter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="relay_commands", to="energy.meter")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
