import uuid
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import NewsArticle, Recharge, Telemetry


class TelemetryPayloadSerializer(serializers.Serializer):
    """Contrat de données imposé par le prompt d'ingénierie (validation stricte)."""

    message_id = serializers.UUIDField()
    meter_id = serializers.CharField(max_length=64)
    device_timestamp = serializers.DateTimeField()
    voltage = serializers.FloatField(min_value=0, max_value=300)
    current = serializers.FloatField(min_value=0, max_value=100)
    power = serializers.FloatField(min_value=0, max_value=30000)
    energy_consumed = serializers.FloatField(min_value=0, max_value=1000000)
    balance_kwh = serializers.FloatField(min_value=0, max_value=1000000)
    relay_status = serializers.BooleanField()
    signal_strength = serializers.IntegerField(min_value=0, max_value=100)
    device_status = serializers.ChoiceField(choices=["ONLINE", "OFFLINE"])
    firmware_version = serializers.CharField(max_length=32)

    def validate(self, attrs):
        # Cohérence physique : P <= V x I (tolérance 15 % pour facteur de puissance)
        if attrs["power"] > attrs["voltage"] * max(attrs["current"], 1) * 1.15:
            raise serializers.ValidationError("La puissance dépasse la cohérence tension-courant.")
        # Cohérence temporelle : pas de message trop ancien ni daté dans le futur
        now = timezone.now()
        if attrs["device_timestamp"] < now - timedelta(minutes=10):
            raise serializers.ValidationError("Message trop ancien (plus de 10 minutes).")
        if attrs["device_timestamp"] > now + timedelta(minutes=5):
            raise serializers.ValidationError("Message daté dans le futur.")
        if attrs["relay_status"] is False and attrs["balance_kwh"] > 0 and attrs["device_status"] == "ONLINE":
            # Un relais coupé avec un solde positif est plausible (isolement manuel) : on ne rejette pas,
            # mais on garde la trace dans le journal de rejet côté vue.
            pass
        return attrs


class TelemetrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Telemetry
        fields = "__all__"


class SubscriberLoginSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=80, trim_whitespace=True)
    last_name = serializers.CharField(max_length=80, trim_whitespace=True)
    meter_code = serializers.RegexField(r"^\d{20}$", error_messages={"invalid": "Le code compteur doit contenir exactement 20 chiffres."})
    # Coordonnées de contact recueillies à la première connexion (optionnelles, enrichissent le profil).
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=24, required=False, allow_blank=True, default="", trim_whitespace=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default="", trim_whitespace=True)

    def validate(self, attrs):
        if len(attrs["first_name"].strip()) < 2 or len(attrs["last_name"].strip()) < 2:
            raise serializers.ValidationError("Le nom et le prénom doivent contenir au moins deux caractères.")
        return attrs


class TokenRefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")


class ManualTokenIssueSerializer(serializers.Serializer):
    meter_id = serializers.CharField(max_length=64)
    energy_kwh = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))


class ManualTokenApplySerializer(serializers.Serializer):
    token = serializers.CharField(max_length=256)


class PaymentInitiateSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=["pawapay", "flutterwave"])
    amount_cdf = serializers.DecimalField(max_digits=14, decimal_places=0, min_value=Decimal("100"))
    # Pour PawaPay (mobile money) : numéro de téléphone de l'abonné + réseau choisi (Airtel/Orange/Vodacom).
    phone_number = serializers.CharField(max_length=24, required=False, allow_blank=True)
    network = serializers.ChoiceField(
        choices=[
            ("AIRTEL_COD", "Airtel"),
            ("ORANGE_COD", "Orange"),
            ("VODACOM_MPESA_COD", "Vodacom"),
        ],
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("provider") == "pawapay":
            phone = (attrs.get("phone_number") or "").strip()
            if not phone:
                raise serializers.ValidationError({"phone_number": "Numéro mobile money requis pour un paiement PawaPay."})
        return attrs


class RelayCommandRequestSerializer(serializers.Serializer):
    desired_state = serializers.ChoiceField(choices=["ON", "OFF"])


class NewsArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsArticle
        fields = ["id", "title", "summary", "body", "category", "territory", "image_url", "source_url", "is_published", "published_at", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
