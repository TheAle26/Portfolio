"""Quantity-aware prices and timestamped observations shared by every surface."""
import hashlib
import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

CENT = Decimal('0.01')
FRESH_HOURS = 36


def normalize_gtin(value):
    value = str(value or '').strip()
    if not value.isascii() or not re.fullmatch(r'(\d{8}|\d{12}|\d{13}|\d{14})', value):
        return None
    digits = [int(d) for d in value]
    check = (10 - sum(d * (3 if i % 2 == 0 else 1)
                      for i, d in enumerate(reversed(digits[:-1]))) % 10) % 10
    return value.zfill(14) if digits[-1] == check else None


def promotion_details(record):
    rule = getattr(record, 'promotion', None) or {}
    if not rule:
        # Legacy text may be interpreted only by the same conservative parser.
        from .scraper import parse_promotion_rule
        rule = parse_promotion_rule(getattr(record, 'promo_text', '') or '')
    return rule


def promotion_label(record):
    from django.utils.translation import gettext as _
    rule = promotion_details(record)
    if rule.get('kind') == 'nxm':
        label = _('Llevá %(take)s, pagá %(pay)s') % rule
    elif rule.get('kind') == 'second_unit':
        label = _('%(percent)s%% de descuento en la segunda unidad') % rule
    else:
        return getattr(record, 'promo_text', '') or ''
    if rule.get('restricted'):
        label += ' · ' + _('Sujeto a condiciones del supermercado')
    elif 'online' in getattr(record, 'promo_text', '').casefold():
        label += ' · ' + _('Exclusivo online')
    if rule.get('ends_on'):
        label += ' · ' + _('Hasta %(date)s') % {'date': date.fromisoformat(rule['ends_on']).strftime('%d/%m')}
    return label


def line_total(record, quantity=1):
    quantity = max(1, min(int(quantity), 99))
    base = Decimal(record.price)
    rule = promotion_details(record)
    today = timezone.localdate()
    try:
        applicable = not rule.get('restricted')
        if rule.get('starts_on'):
            applicable &= date.fromisoformat(rule['starts_on']) <= today
        if rule.get('ends_on'):
            applicable &= today <= date.fromisoformat(rule['ends_on'])
        if applicable and rule.get('kind') == 'nxm':
            take, pay = int(rule['take']), int(rule['pay'])
            if 1 <= pay < take <= 99:
                quantity = (quantity // take) * pay + quantity % take
        elif applicable and rule.get('kind') == 'second_unit':
            percent = Decimal(str(rule['percent']))
            if 0 < percent <= 100:
                return (base * (quantity - (quantity // 2) * percent / 100)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (ValueError, KeyError, TypeError, ArithmeticError):
        pass
    return (base * quantity).quantize(CENT, rounding=ROUND_HALF_UP)


def legacy_cutoff_date():
    cutoff = timezone.localtime(timezone.now() - timedelta(hours=FRESH_HOURS))
    return cutoff.date() + timedelta(days=int(cutoff.time() != time.min))


def is_fresh(product, record=None):
    checked = product.last_price_checked_at
    if checked is not None:
        return checked >= timezone.now() - timedelta(hours=FRESH_HOURS)
    # Existing daily rows remain usable during the additive migration.
    if record is not None:
        return timezone.make_aware(datetime.combine(record.date, time.min), timezone.get_current_timezone()) >= timezone.now() - timedelta(hours=FRESH_HOURS)
    return False


@transaction.atomic
def record_observation(product, parsed, run=None, observed_at=None):
    from .models import CatalogItem, PriceObservation, PriceRecord, Product
    observed_at = observed_at or timezone.now()
    fields = {key: parsed.get(key) for key in ('price', 'list_price', 'promo_price', 'promo_text')}
    fields['promo_text'] = fields['promo_text'] or ''
    fields['promotion'] = parsed.get('promotion') or {}
    fingerprint = hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()
    # Serialize writers for this listing, including targeted/catalog overlap.
    Product.objects.select_for_update().get(pk=product.pk)
    latest = PriceObservation.objects.filter(product=product).order_by('-observed_at', '-pk').first()
    if latest is None or latest.fingerprint != fingerprint:
        latest = PriceObservation.objects.create(product=product, observed_at=observed_at,
                                                 source_run=run, fingerprint=fingerprint, **fields)
    PriceRecord.objects.update_or_create(product=product, date=timezone.localdate(observed_at),
                                         defaults={**fields, 'observed_at': observed_at})
    from .search import normalize
    updates = {'last_price_checked_at': observed_at, 'search_text': normalize(product.name + ' ' + product.brand), 'is_available': bool(parsed.get('is_available', product.is_available))}
    gtin = normalize_gtin(product.ean)
    if gtin:
        item, _ = CatalogItem.objects.get_or_create(gtin=gtin, defaults={'name': product.name, 'brand': product.brand})
        updates['catalog_item'] = item
    else:
        updates['catalog_item'] = None
    Product.objects.filter(pk=product.pk).update(**updates)
    for key, value in updates.items():
        setattr(product, key, value)
    return latest
