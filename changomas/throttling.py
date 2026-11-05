"""Small database-backed fixed windows shared by all web processes."""
import hashlib
import hmac
import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone


def allow_attempt(scope, identity, limit, seconds):
    from .personal_models import RateWindow
    window = int(time.time()) // seconds
    digest = hmac.new(settings.SECRET_KEY.encode(), str(identity).encode(), hashlib.sha256).hexdigest()
    key = f'{scope}:{digest}:{window}'
    now = timezone.now()
    with transaction.atomic():
        row, _ = RateWindow.objects.select_for_update().get_or_create(
            key=key, defaults={'expires_at': now + timedelta(seconds=seconds * 2)})
        if row.attempts >= limit:
            return False
        row.attempts += 1
        row.save(update_fields=['attempts'])
    RateWindow.objects.filter(expires_at__lt=now).delete()
    return True


def allow_auth(request, scope, limit=20, seconds=900):
    address = request.META.get('REMOTE_ADDR', '')
    email = request.POST.get('email', request.POST.get('username', '')).strip().lower()[:254]
    return allow_attempt(scope + '-ip', address, limit, seconds) and allow_attempt(
        scope + '-email', email, limit, seconds)
