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
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from changomas.models import PriceRecord, Product
from changomas.scraper import MasOnlineClient, ScrapeError, parse_product
from changomas.views import CATEGORIES_CACHE_KEY

logger = logging.getLogger(__name__)

RETENTION_DAYS = 30


class Command(BaseCommand):
    help = 'Scrapea el catálogo completo de masonline.com.ar y guarda los precios del día.'

    def add_arguments(self, parser):
        parser.add_argument('--delay', type=float, default=0.3,
                            help='Pausa en segundos entre requests a la API (default 0.3).')
        parser.add_argument('--max-categories', type=int, default=None,
                            help='Limita la cantidad de categorías (solo para pruebas).')
        parser.add_argument('--keep-days', type=int, default=RETENTION_DAYS,
                            help=f'Días de historial a conservar (default {RETENTION_DAYS}).')

    def handle(self, *args, **options):
        run_started = timezone.now()
        today = timezone.localdate()
        client = MasOnlineClient(delay=options['delay'])

        categories = client.get_leaf_categories()
        if not categories:
            self.stderr.write(self.style.ERROR('No se pudo obtener el árbol de categorías. Abortando.'))
            return
        if options['max_categories']:
            categories = categories[:options['max_categories']]

        self.stdout.write(f'Categorías hoja a recorrer: {len(categories)}')

        seen_vtex_ids = set()
        failed_categories = []
        stats = {'products': 0, 'created': 0, 'prices': 0, 'skipped': 0}

        for index, (category_id, category_path) in enumerate(categories, start=1):
            batch = []
            category_failed = False
            try:
                for raw in client.iter_category_products(category_id):
                    try:
                        parsed = parse_product(raw, category_path)
                    except Exception:
                        # Un producto malformado no debe tumbar la corrida nocturna
                        logger.exception('Producto malformado en %s', category_path)
                        stats['skipped'] += 1
                        continue
                    if parsed is None:
                        stats['skipped'] += 1
                        continue
                    if parsed['vtex_product_id'] in seen_vtex_ids:
                        continue
                    seen_vtex_ids.add(parsed['vtex_product_id'])
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
                    self._save_batch(batch, today, stats)
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

        purged = self._purge_old_records(today, options['keep_days'])
        if options['max_categories']:
            # Corrida parcial de prueba: no vimos el catálogo completo, así que
            # no podemos afirmar que un producto ausente ya no esté a la venta.
            self.stdout.write('Corrida parcial (--max-categories): se omite el marcado de no disponibles.')
        else:
            self._mark_missing_unavailable(run_started, seen_vtex_ids, failed_categories)
        cache.delete(CATEGORIES_CACHE_KEY)

        elapsed = (timezone.now() - run_started).total_seconds()
        style = self.style.WARNING if failed_categories else self.style.SUCCESS
        self.stdout.write(style(
            f'Listo en {elapsed / 60:.1f} min. Productos: {stats["products"]} '
            f'(nuevos: {stats["created"]}), precios guardados: {stats["prices"]}, '
            f'sin oferta: {stats["skipped"]}, registros purgados: {purged}, '
            f'categorías con fallas: {len(failed_categories)}.'
        ))

    @transaction.atomic
    def _save_batch(self, batch, today, stats):
        """Guarda un lote de productos parseados y sus precios del día."""
        vtex_ids = [p['vtex_product_id'] for p in batch]
        existing = {
            product.vtex_product_id: product
            for product in Product.objects.filter(vtex_product_id__in=vtex_ids)
        }
        # Códigos de referencia ya usados por OTROS productos en DB (evita
        # chocar con la restricción unique si dos productos comparten EAN).
        used_codes = set(
            Product.objects
            .filter(reference_code__in=[p['reference_code'] for p in batch])
            .exclude(vtex_product_id__in=vtex_ids)
            .values_list('reference_code', flat=True)
        )
        # También hay que detectar colisiones DENTRO del propio lote: dos
        # productos nuevos con el mismo EAN romperían el bulk_create.
        for parsed in batch:
            if parsed['reference_code'] in used_codes:
                parsed['reference_code'] = f"vtex-{parsed['vtex_product_id']}"
            used_codes.add(parsed['reference_code'])

        product_fields = ('reference_code', 'ean', 'product_reference', 'name',
                          'brand', 'category', 'image_url', 'link', 'is_available')
        to_create = []
        unchanged_ids = []
        for parsed in batch:
            product = existing.get(parsed['vtex_product_id'])
            if product is None:
                to_create.append(Product(
                    vtex_product_id=parsed['vtex_product_id'],
                    **{field: parsed[field] for field in product_fields},
                ))
                stats['created'] += 1
            else:
                changed = False
                for field in product_fields:
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

        products_by_vtex_id = {
            product.vtex_product_id: product
            for product in Product.objects.filter(vtex_product_id__in=vtex_ids)
        }
        price_rows = []
        for parsed in batch:
            product = products_by_vtex_id.get(parsed['vtex_product_id'])
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

    def _purge_old_records(self, today, keep_days):
        # today - (keep_days - 1) conserva exactamente keep_days fechas
        cutoff = today - timezone.timedelta(days=keep_days - 1)
        deleted, _ = PriceRecord.objects.filter(date__lt=cutoff).delete()
        return deleted

    def _mark_missing_unavailable(self, run_started, seen_vtex_ids, failed_categories):
        """Los productos que no aparecieron en esta corrida dejan de estar disponibles."""
        if not seen_vtex_ids:
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
        Product.objects.filter(last_seen__lt=run_started, is_available=True) \
            .update(is_available=False)
