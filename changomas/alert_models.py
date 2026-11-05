"""Persistent price-alert events and the transactional email outbox."""

from django.conf import settings
from django.db import models


class PriceAlertEvent(models.Model):
    subscription = models.ForeignKey(
        'changomas.Subscription', on_delete=models.CASCADE, related_name='alert_events',
    )
    key = models.CharField(max_length=64)
    observation = models.ForeignKey(
        'changomas.PriceObservation', on_delete=models.CASCADE, related_name='alert_events',
    )
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['subscription', 'key'], name='unique_alert_event_key')]
        ordering = ['created_at', 'pk']


class EmailDelivery(models.Model):
    class State(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENDING = 'sending', 'Sending'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'
        UNCERTAIN = 'uncertain', 'Uncertain'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='price_email_deliveries')
    events = models.ManyToManyField(PriceAlertEvent, related_name='deliveries')
    batch_key = models.CharField(max_length=64, unique=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING, db_index=True)
    body_snapshot = models.JSONField(default=dict)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']


class JobLease(models.Model):
    """Database lease prevents overlapping copies of the followed refresh job."""
    name = models.CharField(max_length=80, primary_key=True)
    token = models.CharField(max_length=32)
    expires_at = models.DateTimeField(db_index=True)
