"""Price-alert condition evaluation and durable email delivery."""

import hashlib
import json
import logging
import re
import smtplib
from datetime import date
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from changomas.alert_models import EmailDelivery, PriceAlertEvent

logger = logging.getLogger(__name__)
PUBLIC_URL = 'https://vincentalejo.myddns.me/supermarket-tracker/'


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _norm(text):
    return re.sub(r'\s+', ' ', (text or '').casefold()).strip()


def _eligible(user):
    if not getattr(user, 'is_active', False):
        return False
    try:
        pref = user.notification_preference
    except ObjectDoesNotExist:
        return False
    return bool(pref.email_enabled and pref.email_verified_at and pref.verified_email.casefold() == user.email.casefold() and not pref.unsubscribed_at and user.email)


def _delivery_snapshot(user, events):
    products = [event.payload for event in events]
    return {
        'recipient': user.email,
        'events': products,
        'public_url': getattr(settings, 'SUPERMARKET_PUBLIC_URL', PUBLIC_URL).rstrip('/') + '/',
        'unsubscribe_url': _unsubscribe_url(user),
    }


def _unsubscribe_url(user):
    token = signing.dumps({'uid': user.pk, 'email': user.email}, salt='changomas.email-unsubscribe.v1')
    base = getattr(settings, 'SUPERMARKET_PUBLIC_URL', PUBLIC_URL).rstrip('/')
    return f'{base}/baja-email/{token}/'


@transaction.atomic
def enqueue_observation_alerts(observation, *, batch=None):
    """Evaluate subscriptions for an appended observation and enqueue one batch/user."""
    from changomas.personal_models import Subscription
    from changomas.pricing import line_total, promotion_details

    observed_product = observation.product
    same_identity = Q(product_id=observed_product.pk)
    if observed_product.catalog_item_id:
        same_identity |= Q(product__catalog_item_id=observed_product.catalog_item_id)
    elif observed_product.ean:
        same_identity |= Q(product__ean=observed_product.ean)

    created_by_user = {}
    with transaction.atomic():
        subscriptions = Subscription.objects.select_for_update().filter(
            same_identity, is_active=True,
        ).select_related('user', 'product', 'product__supermarket')
        allowed = Subscription.objects.filter(Q(stores__isnull=True) | Q(stores__pk=observation.product.supermarket_id)).values('pk')
        subscriptions = subscriptions.filter(pk__in=allowed)
        price = observation.price
        rule = promotion_details(observation)
        today = timezone.localdate(observation.observed_at)
        promotion_allowed = not bool(rule.get('restricted'))
        try:
            if rule.get('starts_on'):
                promotion_allowed &= date.fromisoformat(rule['starts_on']) <= today
            if rule.get('ends_on'):
                promotion_allowed &= today <= date.fromisoformat(rule['ends_on'])
        except (ValueError, TypeError):
            promotion_allowed = False
        discount_price = observation.promo_price if observation.promo_price is not None and observation.promo_price < price else price
        try:
            if not rule.get('restricted') and rule.get('kind') == 'nxm':
                take = int(rule.get('take', 0))
                if take > 1:
                    discount_price = min(discount_price, line_total(observation, take) / Decimal(take))
            elif not rule.get('restricted') and rule.get('kind') == 'second_unit':
                discount_price = min(discount_price, line_total(observation, 2) / Decimal(2))
        except (ValueError, TypeError, ArithmeticError):
            pass
        has_discount = (bool(rule.get('kind')) and observation.promo_price is not None and observation.promo_price < price) or (
            observation.list_price is not None and observation.list_price > price
        )
        for sub in subscriptions:
            all_state = dict(sub.last_condition or {})
            listing_key = str(observation.product_id)
            state = dict(all_state.get(listing_key) or {})
            target = sub.target_price
            target_rule = str(target) if target is not None else None
            was_below = bool(state.get('target_below', False)) and state.get('target_rule') == target_rule
            below = target is not None and price <= target
            if target is not None and below and not was_below:
                payload = _payload(sub, observation, 'target', price)
                key = _digest(['target', str(target), observation.product_id, observation.pk])
                event, created = PriceAlertEvent.objects.get_or_create(
                    subscription=sub, key=key,
                    defaults={'observation': observation, 'payload': payload},
                )
                if created and _eligible(sub.user):
                    created_by_user.setdefault(sub.user_id, (sub.user, []))[1].append(event)

            promo_signature = None
            if sub.promo_alert and promotion_allowed and has_discount:
                promo_signature = _digest([
                    str(discount_price), str(observation.list_price), _norm(observation.promo_text), rule,
                ])
                if promo_signature != state.get('promo_signature'):
                    payload = _payload(sub, observation, 'promotion', discount_price)
                    key = _digest(['promotion', promo_signature, observation.product_id, observation.pk])
                    event, created = PriceAlertEvent.objects.get_or_create(
                        subscription=sub, key=key,
                        defaults={'observation': observation, 'payload': payload},
                    )
                    if created and _eligible(sub.user):
                        created_by_user.setdefault(sub.user_id, (sub.user, []))[1].append(event)

            state.update({
                'target_below': below, 'target_rule': target_rule,
                'last_price': str(price), 'promo_signature': promo_signature,
            })
            all_state[listing_key] = state
            sub.last_condition = all_state
            sub.save(update_fields=['last_condition'])

    if batch is not None:
        for user_id, (user, events) in created_by_user.items():
            batch.setdefault(user_id, (user, []))[1].extend(events)
        return
    _create_deliveries(created_by_user, observation.pk)


def _create_deliveries(created_by_user, batch_ref):
    for user, events in created_by_user.values():
        # Events are sorted for stable idempotency.
        ids = sorted(event.pk for event in events)
        batch_key = _digest([user.pk, batch_ref, ids])
        delivery, created = EmailDelivery.objects.get_or_create(
            batch_key=batch_key,
            defaults={'user': user, 'body_snapshot': _delivery_snapshot(user, events)},
        )
        if created:
            delivery.events.set(events)


@transaction.atomic
def evaluate_run(run):
    """Evaluate the latest verified observation for every listing checked by this run."""
    from changomas.models import PriceObservation, Product

    from changomas.personal_models import Subscription
    from django.db.models import Prefetch
    subscribed = Subscription.objects.filter(is_active=True)
    identity_filter = Q(pk__in=subscribed.values('product_id')) | Q(catalog_item_id__in=subscribed.exclude(product__catalog_item_id=None).values('product__catalog_item_id')) | Q(ean__in=subscribed.exclude(product__ean='').values('product__ean'))
    checked = Product.objects.filter(identity_filter,
        supermarket_id=run.supermarket_id,
        last_price_checked_at__gte=run.started_at,
        is_available=True,
    ).prefetch_related(Prefetch('observations', queryset=PriceObservation.objects.select_related('product__supermarket').order_by('-observed_at', '-pk')[:1], to_attr='latest_observations'))
    by_user = {}
    for product in checked.iterator(chunk_size=200):
        observation = product.latest_observations[0] if product.latest_observations else None
        if observation is None:
            continue
        enqueue_observation_alerts(observation, batch=by_user)
    if by_user:
        _create_deliveries(by_user, f'run-{run.pk}')


def _payload(subscription, observation, kind, effective_price):
    product = observation.product
    from .pricing import promotion_label
    return {
        'subscription_id': subscription.pk,
        'kind': kind,
        'product': product.name,
        'store': product.supermarket.name,
        'price': str(observation.price),
        'effective_price': str(effective_price),
        'target_price': str(subscription.target_price) if subscription.target_price is not None else None,
        'promo_text': promotion_label(observation) or (
            'Descuento sobre precio de lista'
            if observation.list_price is not None and observation.list_price > observation.price
            else 'Precio promocional'
        ),
        'url': f"{getattr(settings, 'SUPERMARKET_PUBLIC_URL', PUBLIC_URL).rstrip('/')}/{product.supermarket.slug}/producto/{product.reference_code}/",
    }


def dispatch_email_deliveries(*, send=False, limit=100, now=None):
    """Send due outbox rows. Dry-run returns a count and never calls SMTP."""
    now = now or timezone.now()
    EmailDelivery.objects.filter(
        state=EmailDelivery.State.SENDING,
        claimed_at__lt=now - timedelta(minutes=15),
    ).update(
        state=EmailDelivery.State.UNCERTAIN,
        error='El worker se interrumpió durante el envío; resultado SMTP incierto.',
    )
    due = EmailDelivery.objects.filter(
        Q(state=EmailDelivery.State.PENDING) |
        Q(state=EmailDelivery.State.FAILED, next_attempt_at__lte=now),
    ).order_by('created_at', 'pk')[:limit]
    if not send or not getattr(settings, 'SUPERMARKET_EMAILS_ENABLED', False):
        return {'ready': due.count(), 'sent': 0, 'dry_run': True}

    sent = 0
    for candidate in due:
        with transaction.atomic():
            qs = EmailDelivery.objects.select_for_update()
            if transaction.get_connection().features.has_select_for_update_skip_locked:
                qs = qs.select_for_update(skip_locked=True)
            delivery = qs.filter(pk=candidate.pk).first()
            if delivery is None or delivery.state not in (EmailDelivery.State.PENDING, EmailDelivery.State.FAILED):
                continue
            delivery.state = EmailDelivery.State.SENDING
            delivery.attempts += 1
            delivery.claimed_at = now
            delivery.save(update_fields=['state', 'attempts', 'claimed_at'])
        user = get_user_model().objects.filter(pk=delivery.user_id).first()
        if user is None or not _eligible(user):
            delivery.state = EmailDelivery.State.FAILED
            delivery.error = 'El usuario ya no cumple las preferencias de envío.'
            delivery.next_attempt_at = None
            delivery.save(update_fields=['state', 'error', 'next_attempt_at'])
            continue
        snapshot = delivery.body_snapshot
        active_ids = set(user.subscriptions.filter(is_active=True).values_list('pk', flat=True))
        events = [event for event in snapshot.get('events', []) if event.get('subscription_id') in active_ids]
        if not events:
            delivery.state = EmailDelivery.State.FAILED
            delivery.error = 'No quedan seguimientos activos en este envío.'
            delivery.next_attempt_at = None
            delivery.save(update_fields=['state', 'error', 'next_attempt_at'])
            continue
        context = {
            'events': events,
            'public_url': snapshot.get('public_url', PUBLIC_URL),
            'unsubscribe_url': _unsubscribe_url(user),
        }
        text_body = render_to_string('changomas/emails/price_alert.txt', context)
        html_body = render_to_string('changomas/emails/price_alert.html', context)
        message = EmailMultiAlternatives(
            subject='Cambios en tus productos seguidos', body=text_body,
            to=[user.email], from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        )
        message.attach_alternative(html_body, 'text/html')
        try:
            accepted = message.send(fail_silently=False)
            if accepted != 1:
                delivery.state = EmailDelivery.State.FAILED
                delivery.error = 'El backend SMTP no aceptó el mensaje.'
                delivery.next_attempt_at = (
                    now + timedelta(minutes=min(60, 2 ** min(delivery.attempts, 5)))
                    if delivery.attempts < 5 else None
                )
                delivery.save(update_fields=['state', 'error', 'next_attempt_at'])
                continue
        except smtplib.SMTPResponseException as exc:
            delivery.error = str(exc)[:2000]
            if 400 <= exc.smtp_code < 500:
                delivery.state = EmailDelivery.State.FAILED
                delivery.next_attempt_at = (
                    now + timedelta(minutes=min(60, 2 ** min(delivery.attempts, 5)))
                    if delivery.attempts < 5 else None
                )
            else:
                delivery.state = EmailDelivery.State.UNCERTAIN
                delivery.next_attempt_at = None
            delivery.save(update_fields=['state', 'error', 'next_attempt_at'])
            continue
        except (smtplib.SMTPServerDisconnected, TimeoutError, OSError) as exc:
            # Connection loss can happen after SMTP accepted the message. Never auto-retry ambiguously.
            delivery.state = EmailDelivery.State.UNCERTAIN
            delivery.error = str(exc)[:2000]
            delivery.next_attempt_at = None
            delivery.save(update_fields=['state', 'error', 'next_attempt_at'])
            continue
        except Exception as exc:
            delivery.state = EmailDelivery.State.UNCERTAIN
            delivery.error = str(exc)[:2000]
            delivery.next_attempt_at = None
            delivery.save(update_fields=['state', 'error', 'next_attempt_at'])
            logger.exception('Fallo SMTP no recuperable para envío %s', delivery.pk)
            continue
        delivery.state = EmailDelivery.State.SENT
        delivery.sent_at = timezone.now()
        delivery.error = ''
        delivery.next_attempt_at = None
        delivery.save(update_fields=['state', 'sent_at', 'error', 'next_attempt_at'])
        sent += 1
    return {'ready': due.count(), 'sent': sent, 'dry_run': False}
