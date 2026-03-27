from django.db import models


class Agent(models.Model):
    VOICE = "voice"
    AUTOMATION = "automation"
    OTHER = "other"

    KIND_CHOICES = [
        (VOICE, "Voice"),
        (AUTOMATION, "Automation"),
        (OTHER, "Other"),
    ]

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, default=VOICE)
    status = models.CharField(max_length=32, default="idle")  # idle, listening, error
    active = models.BooleanField(default=True)
    wake_word = models.CharField(max_length=50, blank=True)
    mode = models.CharField(max_length=32, blank=True, help_text="Optional profile/mode, e.g. 'car'")
    gateway_binding = models.CharField(max_length=200, blank=True, help_text="Optional OpenClaw node/session id")
    last_heartbeat = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class NodeStatus(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True)
    online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class Mission(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=[
            ("planned", "Planned"),
            ("running", "Running"),
            ("paused", "Paused"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="planned",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.CharField(max_length=100, default="Pock")

    def __str__(self):
        return self.name


class Event(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(
        max_length=16,
        choices=[
            ("info", "Info"),
            ("warn", "Warning"),
            ("error", "Error"),
        ],
        default="info",
    )
    source = models.CharField(max_length=100, blank=True)
    message = models.TextField()

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.level}] {self.message[:50]}"


class IncomeProfile(models.Model):
    """
    Singleton-style freelance income target for the dashboard strip (use pk=1).

    Args:
        None (model fields only).

    Returns:
        IncomeProfile: Row storing annual/monthly targets in minor units (cents).

    Example:
        profile, _ = IncomeProfile.objects.get_or_create(pk=1, defaults={"annual_target_cents": 8500000})
    """

    annual_target_cents = models.BigIntegerField(default=8_500_000)
    monthly_target_cents = models.BigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")

    class Meta:
        verbose_name = "Income profile"
        verbose_name_plural = "Income profiles"

    def __str__(self) -> str:
        return f"Income target ({self.currency})"


class PipelineItem(models.Model):
    """
    One row in the freelance pipeline (lead through paid).

    Args:
        None (model fields only).

    Returns:
        PipelineItem: Sortable pipeline entry with optional expected value.

    Example:
        PipelineItem.objects.create(name="ACME firmware", stage=PipelineItem.STAGE_LEAD, sort_order=0)
    """

    STAGE_LEAD = "lead"
    STAGE_PROPOSAL = "proposal"
    STAGE_ACTIVE = "active"
    STAGE_PAID = "paid"

    STAGE_CHOICES = [
        (STAGE_LEAD, "Lead"),
        (STAGE_PROPOSAL, "Proposal"),
        (STAGE_ACTIVE, "Active"),
        (STAGE_PAID, "Paid"),
    ]

    name = models.CharField(max_length=200)
    stage = models.CharField(max_length=32, choices=STAGE_CHOICES, default=STAGE_LEAD)
    expected_value_cents = models.BigIntegerField(null=True, blank=True)
    next_action = models.CharField(max_length=500, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.stage})"


class DailyBuildBlock(models.Model):
    """
    Single daily build/education block (one row per calendar date).

    Args:
        None (model fields only).

    Returns:
        DailyBuildBlock: Dated task with completion flag.

    Example:
        DailyBuildBlock.objects.update_or_create(
            date=timezone.localdate(),
            defaults={"title": "ESP32 MQTT subscriber", "done": False},
        )
    """

    date = models.DateField(unique=True)
    title = models.CharField(max_length=300)
    done = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.date}: {self.title}"


class IoTLabEntry(models.Model):
    """
    Hardware / IoT lab note (device name, location, free-form notes).

    Args:
        None (model fields only).

    Returns:
        IoTLabEntry: Row with auto-updated last_touched on save.

    Example:
        IoTLabEntry.objects.create(name="Garage ESP32", location="garage", notes="DHT22 on GPIO4")
    """

    name = models.CharField(max_length=200)
    location = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    last_touched = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "IoT lab entry"
        verbose_name_plural = "IoT lab entries"

    def __str__(self) -> str:
        return self.name
