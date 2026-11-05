"""Periodic refresh of products followed by active users."""

import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q, F
from django.conf import settings
from django.utils import timezone

from changomas.alert_models import JobLease
from changomas.models import Product, SourceRun, Supermarket
from changomas.pricing import record_observation
from changomas.scraper import STORE_CONFIGS, VtexClient, parse_products
from changomas.models import GTIN_RE
from changomas.personal_models import Subscription
from changomas.notifications import evaluate_run

logger = logging.getLogger(__name__)


def _acquire_lease(name='followed-products', duration=timedelta(hours=4)):
    now = timezone.now()
    token = uuid.uuid4().hex
    with transaction.atomic():
        lease, _ = JobLease.objects.select_for_update().get_or_create(
            name=name, defaults={'token': token, 'expires_at': now},
        )
        if lease.expires_at and lease.expires_at > now:
            return None
        lease.token = token
        lease.expires_at = now + duration
        lease.save(update_fields=['token', 'expires_at'])
    return token


def release_lease(name, token):
    JobLease.objects.filter(name=name, token=token).delete()


def refresh_followed_products(*, delay=0.3, max_products=None):
    """Fetch current VTEX offers for followed product IDs and record changes."""
    token = _acquire_lease()
    if token is None:
        return {'status': 'already_running', 'products': 0, 'observations': 0}
    stats = {'status': 'success', 'products': 0, 'observations': 0, 'errors': 0}
    started = timezone.now()
    grouped = {}
    limit = max_products if max_products is not None else getattr(settings, 'SUPERMARKET_MAX_REFRESH_PRODUCTS', 3000)
    remaining = max(1, int(limit))
    per_store = max(1, remaining // len(STORE_CONFIGS))
    for store_slug in STORE_CONFIGS:
        subscribers = Subscription.objects.filter(is_active=True, user__is_active=True).filter(
            Q(stores__isnull=True) | Q(stores__pk=store_slug))
        product_filter = Q(pk__in=subscribers.values('product_id')) | Q(
            catalog_item_id__in=subscribers.exclude(product__catalog_item_id=None).values('product__catalog_item_id')) | Q(
            ean__in=subscribers.exclude(product__ean='').values('product__ean'))
        products = Product.objects.filter(product_filter, supermarket_id=store_slug, supermarket__is_active=True).order_by(
            F('last_price_checked_at').asc(nulls_first=True), 'pk')[:min(remaining, per_store)]
        for product in products:
            grouped.setdefault(product.supermarket_id, {}).setdefault(product.vtex_product_id, []).append(product)
            remaining -= 1
        if remaining <= 0:
            logger.warning('Se alcanzó el límite de refresco: %s publicaciones; el resto espera la próxima corrida.', limit)
            break

    try:
        for store_slug, product_ids in grouped.items():
            lease_name = f'store:{store_slug}'
            store_token = _acquire_lease(lease_name, timedelta(hours=6))
            if store_token is None:
                logger.info('Se omite refresco de %s: ya hay una corrida de catálogo activa.', store_slug)
                continue
            try:
                store = Supermarket.objects.get(pk=store_slug, is_active=True)
                run = SourceRun.objects.create(
                    supermarket=store, kind='followed', status='running', started_at=started,
                )
                client = VtexClient(store=store_slug, delay=delay)
                failed = False
                run_products = 0
                run_errors = 0
                for vtex_id, tracked in product_ids.items():
                    try:
                        raw_items = client._get_json(client.config.search_url, params={'fq': f'productId:{vtex_id}'})
                        if not raw_items:
                            raise ValueError('VTEX no devolvió producto')
                        parsed = []
                        for raw in raw_items:
                            parsed.extend(parse_products(raw, store=store_slug))
                        by_sku = {item['vtex_sku_id']: item for item in parsed}
                        for product in tracked:
                            data = by_sku.get(product.vtex_sku_id or '')
                            if data is None and product.vtex_sku_id is None:
                                data = next((x for x in parsed if x['vtex_product_id'] == vtex_id), None)
                            if data is None:
                                # An absent offer is not evidence to synthesize a price or stock update.
                                continue
                            data['is_comparable'] = bool(GTIN_RE.fullmatch(data.get('ean') or ''))
                            for field in (
                                'vtex_product_id', 'ean', 'product_reference', 'measurement_unit',
                                'unit_multiplier', 'name', 'brand', 'category', 'image_url', 'link',
                                'is_available', 'is_comparable',
                            ):
                                if getattr(product, field) != data[field]:
                                    setattr(product, field, data[field])
                            product.save()
                            observation = record_observation(product, data, run=run)
                            stats['products'] += 1
                            run_products += 1
                            if observation and observation.source_run_id == run.pk:
                                stats['observations'] += 1
                    except Exception:
                        failed = True
                        run_errors += 1
                        stats['errors'] += 1
                        logger.exception('Error refrescando VTEX %s/%s', store_slug, vtex_id)
                run.status = 'partial' if failed else 'success'
                run.finished_at = timezone.now()
                run.product_count = run_products
                run.error = f'{run_errors} productos no se pudieron refrescar.' if failed else ''
                run.save(update_fields=['status', 'finished_at', 'product_count', 'error'])
                if not failed:
                    evaluate_run(run)
                if failed:
                    stats['status'] = 'partial'
            finally:
                release_lease(lease_name, store_token)
        return stats
    finally:
        release_lease('followed-products', token)
