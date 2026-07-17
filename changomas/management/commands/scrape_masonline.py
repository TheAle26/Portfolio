"""
Comando diario que recorre todo el catálogo de MasOnline (ChangoMás),
guarda el precio del día de cada producto y purga el historial
de más de 30 días.

Uso:
    python manage.py scrape_masonline
    python manage.py scrape_masonline --max-categories 3 --delay 0.1  (prueba rápida)
"""
import logging

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from changomas.models import GTIN_RE, PriceRecord, Product, Supermarket
from changomas.scraper import (
    STORE_CONFIGS,
    MasOnlineClient,
    ScrapeError,
    VtexClient,
    parse_products,
)
from changomas.views import categories_cache_key

logger = logging.getLogger(__name__)

RETENTION_DAYS = 30


class Command(BaseCommand):
    help = 'Scrapea un catálogo VTEX y guarda sus precios del día.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--store',
            choices=tuple(STORE_CONFIGS),
            default='changomas',
            help='Supermercado a relevar (default: changomas).',
        )
        parser.add_argument('--delay', type=float, default=0.3,
                            help='Pausa en segundos entre requests a la API (default 0.3).')
        parser.add_argument('--max-categories', type=int, default=None,
                            help='Limita la cantidad de categorías (solo para pruebas).')
        parser.add_argument('--keep-days', type=int, default=RETENTION_DAYS,
                            help=f'Días de historial a conservar (default {RETENTION_DAYS}).')

    def handle(self, *args, **options):
        run_started = timezone.now()
        today = timezone.localdate()
        store_slug = options['store']
        supermarket = Supermarket.objects.get(slug=store_slug)
        client = (
            MasOnlineClient(delay=options['delay'])
            if store_slug == 'changomas'
            else VtexClient(store=store_slug, delay=options['delay'])
        )

        categories = client.get_leaf_categories()
        if not categories:
            raise CommandError('No se pudo obtener el árbol de categorías.')
        if options['max_categories']:
            categories = categories[:options['max_categories']]

        self.stdout.write(f'Categorías hoja a recorrer: {len(categories)}')

        seen_sku_ids = set()
        failed_categories = []
        stats = {'products': 0, 'created': 0, 'prices': 0, 'skipped': 0}

        for index, (category_id, category_path) in enumerate(categories, start=1):
            batch = []
            category_failed = False
            try:
                for raw in client.iter_category_products(category_id):
                    try:
                        parsed_items = parse_products(
                            raw, category_path, store=store_slug,
                        )
                    except Exception:
                        # Un producto malformado no debe tumbar la corrida nocturna
                        logger.exception('Producto malformado en %s', category_path)
                        stats['skipped'] += 1
                        continue
                    if not parsed_items:
                        stats['skipped'] += 1
                        continue
                    for parsed in parsed_items:
                        if parsed['vtex_sku_id'] in seen_sku_ids:
                            continue
                        seen_sku_ids.add(parsed['vtex_sku_id'])
                        parsed['is_comparable'] = bool(GTIN_RE.match(parsed['ean'] or ''))
                        batch.append(parsed)
            except ScrapeError as exc:
                category_failed = True
                logger.warning('Categoría incompleta %s: %s', category_path, exc)
            except Exception:
                category_failed = True
                logger.exception('Error inesperado recorriendo %s', category_path)

            if batch:
                try:
                    # Lo que sí se pudo bajar de una categoría fallida es válido
                    self._save_batch(batch, today, stats, supermarket)
                except Exception:
                    category_failed = True
                    logger.exception('Error guardando el lote de %s', category_path)

            if category_failed:
                failed_categories.append(category_path)

            if index % 50 == 0 or index == len(categories):
                self.stdout.write(
                    f'[{index}/{len(categories)}] {category_path} | '
                    f'productos: {stats["products"]} (nuevos: {stats["created"]})'
                )

        purged = self._purge_old_records(
            today, options['keep_days'], supermarket,
        )
        if options['max_categories']:
            # Corrida parcial de prueba: no vimos el catálogo completo, así que
            # no podemos afirmar que un producto ausente ya no esté a la venta.
            self.stdout.write('Corrida parcial (--max-categories): se omite el marcado de no disponibles.')
        else:
            self._mark_missing_unavailable(
                run_started, seen_sku_ids, failed_categories, supermarket,
            )
        cache.delete(categories_cache_key(store_slug))

        elapsed = (timezone.now() - run_started).total_seconds()
        style = self.style.WARNING if failed_categories else self.style.SUCCESS
        self.stdout.write(style(
            f'{supermarket.name}: listo en {elapsed / 60:.1f} min. '
            f'Productos: {stats["products"]} '
            f'(nuevos: {stats["created"]}), precios guardados: {stats["prices"]}, '
            f'sin oferta: {stats["skipped"]}, registros purgados: {purged}, '
            f'categorías con fallas: {len(failed_categories)}.'
        ))
        if failed_categories:
            raise CommandError(
                f'{supermarket.name}: {len(failed_categories)} categorías fallaron.'
            )

    @transaction.atomic
    def _save_batch(self, batch, today, stats, supermarket):
        """Guarda un lote de productos parseados y sus precios del día."""
        sku_ids = [p['vtex_sku_id'] for p in batch]
        product_ids = [p['vtex_product_id'] for p in batch]
        existing_by_sku = {
            product.vtex_sku_id: product
            for product in Product.objects.filter(
                supermarket=supermarket,
                vtex_sku_id__in=sku_ids,
            )
        }
        # Filas anteriores a la migracion multi-SKU no tienen itemId. La
        # primera variante del productId reutiliza esa fila y preserva todo su
        # historial; las variantes adicionales se crean normalmente.
        legacy_by_product = {}
        for product in Product.objects.filter(
            supermarket=supermarket,
            vtex_sku_id__isnull=True,
            vtex_product_id__in=product_ids,
        ).order_by('pk'):
            legacy_by_product.setdefault(product.vtex_product_id, []).append(product)

        matched = {}
        for parsed in batch:
            sku_id = parsed['vtex_sku_id']
            product = existing_by_sku.get(sku_id)
            if product is None:
                legacy = legacy_by_product.get(parsed['vtex_product_id'], [])
                product = None
                for index, candidate in enumerate(legacy):
                    if candidate.ean and candidate.ean == parsed['ean']:
                        product = legacy.pop(index)
                        break
                if product is None and legacy:
                    product = legacy.pop(0)
            matched[sku_id] = product

        # reference_code es una URL estable. Los existentes conservan su
        # codigo; solo resolvemos colisiones para publicaciones nuevas.
        used_codes = set(
            Product.objects.filter(supermarket=supermarket)
            .values_list('reference_code', flat=True)
        )
        for parsed in batch:
            product = matched[parsed['vtex_sku_id']]
            if product is not None:
                parsed['reference_code'] = product.reference_code
                continue
            if parsed['reference_code'] in used_codes:
                fallback = f"vtex-{parsed['vtex_sku_id']}"
                candidate = fallback
                suffix = 2
                while candidate in used_codes:
                    candidate = f'{fallback}-{suffix}'
                    suffix += 1
                parsed['reference_code'] = candidate
            used_codes.add(parsed['reference_code'])

        create_fields = ('reference_code', 'ean', 'vtex_sku_id',
                          'product_reference', 'measurement_unit', 'unit_multiplier', 'name',
                          'brand', 'category', 'image_url', 'link', 'is_available',
                          'is_comparable')
        update_fields = ('vtex_product_id', 'ean', 'vtex_sku_id',
                         'product_reference', 'measurement_unit', 'unit_multiplier', 'name',
                         'brand', 'category', 'image_url', 'link', 'is_available',
                         'is_comparable')
        to_create = []
        unchanged_ids = []
        for parsed in batch:
            product = matched[parsed['vtex_sku_id']]
            if product is None:
                to_create.append(Product(
                    supermarket=supermarket,
                    vtex_product_id=parsed['vtex_product_id'],
                    **{field: parsed[field] for field in create_fields},
                ))
                stats['created'] += 1
            else:
                changed = False
                for field in update_fields:
                    if getattr(product, field) != parsed[field]:
                        setattr(product, field, parsed[field])
                        changed = True
                if changed:
                    # save() refresca last_seen (auto_now)
                    product.save()
                else:
                    unchanged_ids.append(product.pk)

        if to_create:
            Product.objects.bulk_create(to_create)
        if unchanged_ids:
            # Un solo UPDATE para marcar como vistos a los que no cambiaron,
            # en vez de miles de save() individuales por noche en la Raspberry.
            Product.objects.filter(pk__in=unchanged_ids).update(last_seen=timezone.now())

        products_by_sku = {
            product.vtex_sku_id: product
            for product in Product.objects.filter(
                supermarket=supermarket,
                vtex_sku_id__in=sku_ids,
            )
        }
        price_rows = []
        for parsed in batch:
            product = products_by_sku.get(parsed['vtex_sku_id'])
            if product is None:
                continue
            price_rows.append(PriceRecord(
                product=product,
                date=today,
                price=parsed['price'],
                list_price=parsed['list_price'],
                promo_price=parsed['promo_price'],
                promo_text=parsed['promo_text'],
            ))
        # ignore_conflicts: si el comando se corre dos veces el mismo día,
        # se conserva el primer precio guardado.
        created_prices = PriceRecord.objects.bulk_create(price_rows, ignore_conflicts=True)
        stats['prices'] += len(created_prices)
        stats['products'] += len(batch)

    def _purge_old_records(self, today, keep_days, supermarket):
        # today - (keep_days - 1) conserva exactamente keep_days fechas
        cutoff = today - timezone.timedelta(days=keep_days - 1)
        deleted, _ = PriceRecord.objects.filter(
            product__supermarket=supermarket,
            date__lt=cutoff,
        ).delete()
        return deleted

    def _mark_missing_unavailable(
        self, run_started, seen_sku_ids, failed_categories, supermarket,
    ):
        """Los productos que no aparecieron en esta corrida dejan de estar disponibles."""
        if not seen_sku_ids:
            # Si no vimos nada, algo falló: no marcamos todo como no disponible.
            return
        if failed_categories:
            # Con categorías incompletas no podemos distinguir "desapareció del
            # catálogo" de "no lo pudimos bajar hoy": no marcamos nada.
            self.stdout.write(self.style.WARNING(
                f'{len(failed_categories)} categorías fallaron: se omite el marcado '
                f'de productos no disponibles en esta corrida.'
            ))
            return
        Product.objects.filter(
            supermarket=supermarket,
            last_seen__lt=run_started,
            is_available=True,
        ) \
            .update(is_available=False)
