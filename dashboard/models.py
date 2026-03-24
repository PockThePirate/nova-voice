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
