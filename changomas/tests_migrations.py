"""Exercise the upgrade with existing listings, rather than an empty test DB."""
from contextlib import redirect_stdout
from importlib import import_module
from io import StringIO
from types import SimpleNamespace

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext


foundation = import_module('changomas.migrations.0004_tracker_foundation')


def ean_for(number):
    body = f'200{number:09d}'
    check = (-sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))) % 10
    return body + str(check)


class CatalogBackfillTests(TestCase):
    def setUp(self):
        self.apps = MigrationExecutor(connection).loader.project_state(
            [('changomas', '0004_tracker_foundation')]).apps
        self.Product = self.apps.get_model('changomas', 'Product')
        self.Item = self.apps.get_model('changomas', 'CatalogItem')

    def run_backfill(self):
        with redirect_stdout(StringIO()) as output:
            foundation.seed_and_link(self.apps, SimpleNamespace(connection=connection))
        return output.getvalue()

    def test_large_catalog_has_bounded_queries_and_is_idempotent(self):
        products = [self.Product(supermarket_id='changomas', reference_code=f'bulk-{i}',
            vtex_product_id=str(i), name='  Café   MOLIDO ', brand='Águila', ean=ean_for(i))
            for i in range(1201)]
        self.Product.objects.bulk_create(products)
        with CaptureQueriesContext(connection) as queries:
            output = self.run_backfill()
        # A per-row implementation exceeds 4000 queries on this fixture.
        self.assertLess(len(queries), 100)
        self.assertEqual(self.Item.objects.count(), 1201)
        self.assertEqual(self.Product.objects.filter(search_text='cafe molido aguila',
            catalog_item__isnull=False).count(), 1201)
        self.assertIn('1201/1201', output)
        with CaptureQueriesContext(connection) as rerun:
            self.run_backfill()
        self.assertFalse(any(q['sql'].lstrip().upper().startswith('UPDATE') for q in rerun))
        self.assertEqual(self.Item.objects.count(), 1201)

    def test_gtin_variants_share_identity_and_invalid_codes_remain_unlinked(self):
        codes = ['7790742363107', '07790742363107', '036000291452', '96385074',
                 '7790742363108', '', '７７９０７４２３６３１０７', 'vtex-42']
        self.Product.objects.bulk_create([
            self.Product(supermarket_id='changomas', reference_code=f'code-{i}',
                vtex_product_id=str(i), name='Leche', ean=code)
            for i, code in enumerate(codes)])
        self.run_backfill()
        rows = list(self.Product.objects.order_by('pk'))
        self.assertEqual(rows[0].catalog_item_id, rows[1].catalog_item_id)
        self.assertIsNotNone(rows[0].catalog_item_id)
        self.assertEqual(self.Item.objects.count(), 3)
        self.assertTrue(all(p.catalog_item_id is None for p in rows[4:]))
        self.assertEqual(foundation.canonical_gtin(codes[2]), '00036000291452')


class PopulatedCatalogUpgradeTests(TransactionTestCase):
    """Run actual schema changes, backfill, deferred checks and GIN creation."""
    def test_upgrade_from_0003_preserves_catalog_and_price_history(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        old_target = [('changomas', '0003_product_is_comparable')]
        try:
            executor.migrate(old_target)
            old_apps = executor.loader.project_state(old_target).apps
            Product = old_apps.get_model('changomas', 'Product')
            Price = old_apps.get_model('changomas', 'PriceRecord')
            Product.objects.bulk_create([
                Product(supermarket_id='changomas', reference_code=f'legacy-{i}',
                    vtex_product_id=str(i), name='Arroz clásico', brand='Águila',
                    ean=ean_for(i % 500)) for i in range(1001)])
            product = Product.objects.order_by('pk').first()
            stamp = (product.first_seen, product.last_seen)
            Price.objects.create(product=product, date='2026-11-05', price='123.45')
            executor = MigrationExecutor(connection)
            with redirect_stdout(StringIO()):
                executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            upgraded = apps.get_model('changomas', 'Product')
            item = apps.get_model('changomas', 'CatalogItem')
            self.assertEqual(upgraded.objects.count(), 1001)
            self.assertEqual(item.objects.count(), 500)
            self.assertEqual(upgraded.objects.filter(search_text='arroz clasico aguila',
                catalog_item__isnull=False).count(), 1001)
            restored = upgraded.objects.get(pk=product.pk)
            self.assertEqual((restored.first_seen, restored.last_seen), stamp)
            self.assertEqual(str(apps.get_model('changomas', 'PriceRecord').objects.get(
                product_id=product.pk).price), '123.45')
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute("SELECT indexname FROM pg_indexes WHERE tablename='changomas_product'")
                    names = {row[0] for row in cursor.fetchall()}
                self.assertTrue({'tracker_search_words', 'tracker_search_typos'} <= names)
        finally:
            MigrationExecutor(connection).migrate(latest)
