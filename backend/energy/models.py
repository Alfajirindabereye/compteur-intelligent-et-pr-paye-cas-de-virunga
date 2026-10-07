from django.db import models


class Sector(models.Model):
    name = models.CharField(max_length=128, unique=True)
    territory = models.CharField(max_length=128)

    def __str__(self) -> str:
        return self.name


class Meter(models.Model):
    meter_id = models.CharField(max_length=64, primary_key=True)
    sector = models.ForeignKey(Sector, on_delete=models.PROTECT, related_name="meters")
    owner_open_id = models.CharField(max_length=128, blank=True)
    subscriber_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    subscriber_first_name = models.CharField(max_length=80, blank=True)
    subscriber_last_name = models.CharField(max_length=80, blank=True)
    subscriber_email = models.EmailField(blank=True, default="")
    subscriber_phone = models.CharField(max_length=24, blank=True, default="")
    subscriber_address = models.CharField(max_length=255, blank=True, default="")
    voltage_v = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    current_a = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    power_w = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    energy_kwh = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    balance_kwh = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    relay_status = models.CharField(max_length=16, default="ON")
    signal_gsm = models.IntegerField(default=0)
    device_status = models.CharField(max_length=16, default="OFFLINE")
    firmware_version = models.CharField(max_length=32, blank=True, default="")
    is_demo = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class Telemetry(models.Model):
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name="telemetry")
    message_id = models.CharField(max_length=128, unique=True)
    applied_at = models.DateTimeField()
    synced_at = models.DateTimeField(auto_now_add=True)
    voltage_v = models.DecimalField(max_digits=10, decimal_places=3)
    current_a = models.DecimalField(max_digits=10, decimal_places=3)
    power_w = models.DecimalField(max_digits=12, decimal_places=3)
    energy_kwh = models.DecimalField(max_digits=14, decimal_places=3)
    balance_kwh = models.DecimalField(max_digits=14, decimal_places=3)
    relay_status = models.CharField(max_length=16)
    signal_gsm = models.IntegerField()


class BudgetSetting(models.Model):
    meter = models.OneToOneField(Meter, on_delete=models.CASCADE, related_name="budget")
    limit_kwh = models.DecimalField(max_digits=14, decimal_places=3)
    warning_percentage = models.PositiveSmallIntegerField(default=80)


class Recharge(models.Model):
    SOURCE_CHOICES = [("APP_PAIEMENT", "APP_PAIEMENT"), ("SAISIE_MANUELLE", "SAISIE_MANUELLE")]
    STATUS_PENDING = "PENDING"
    STATUS_APPLIED = "APPLIED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [(STATUS_PENDING, STATUS_PENDING), (STATUS_APPLIED, STATUS_APPLIED), (STATUS_FAILED, STATUS_FAILED)]
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name="recharges")
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES)
    energy_kwh = models.DecimalField(max_digits=14, decimal_places=3)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_APPLIED)
    applied_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(auto_now_add=True)
    provider_reference = models.CharField(max_length=128, blank=True)


class ManualToken(models.Model):
    token = models.CharField(max_length=256, unique=True)
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name="manual_tokens")
    sequence = models.PositiveBigIntegerField()
    energy_kwh = models.DecimalField(max_digits=14, decimal_places=3)
    issued_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["meter", "sequence"], name="uniq_manual_token_meter_sequence"),
        ]


class PaymentEvent(models.Model):
    event_id = models.CharField(max_length=255, primary_key=True)
    provider = models.CharField(max_length=32)
    status = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)


class Alert(models.Model):
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name="alerts")
    kind = models.CharField(max_length=64)
    severity = models.CharField(max_length=16)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class RelayCommand(models.Model):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    SUPERSEDED = "SUPERSEDED"
    STATUS_CHOICES = [(PENDING, PENDING), (APPLIED, APPLIED), (SUPERSEDED, SUPERSEDED)]
    ON = "ON"
    OFF = "OFF"
    STATE_CHOICES = [(ON, ON), (OFF, OFF)]

    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name="relay_commands")
    requested_state = models.CharField(max_length=3, choices=STATE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)
    requested_by = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class NewsArticle(models.Model):
    title = models.CharField(max_length=180)
    summary = models.CharField(max_length=600)
    body = models.TextField(blank=True)
    category = models.CharField(max_length=80)
    territory = models.CharField(max_length=80)
    image_url = models.URLField(blank=True)
    source_url = models.URLField(blank=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
