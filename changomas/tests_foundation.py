from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless, mock

from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .cart import parse_items, quote
from .models import PriceObservation, PriceRecord, Product, SourceRun, Supermarket
from .pricing import line_total, normalize_gtin, record_observation
from .scraper import parse_promotion_rule


class TrackerFoundationTests(TestCase):
    def setUp(self):
        self.store = Supermarket.objects.get(pk='changomas')
        self.product = Product.objects.create(supermarket=self.store, reference_code='7790742363107',
            ean='7790742363107', vtex_product_id='1', vtex_sku_id='1', name='Leche La Serenísima 1L',
            brand='La Serenísima', category='Lácteos / Leches', is_comparable=True)

    def observe(self, **kwargs):
        parsed = {'price': Decimal('1000'), 'list_price': None, 'promo_price': None, 'promo_text': '', **kwargs}
        return record_observation(self.product, parsed)

    def test_quantity_promotions_apply_to_complete_groups_only(self):
        record = PriceRecord(price=Decimal('1000'), promo_text='3x2', promotion={'kind': 'nxm', 'take': 3, 'pay': 2})
        self.assertEqual([line_total(record, q) for q in (1, 2, 3, 4, 6)], [1000, 2000, 2000, 3000, 4000])
        record.promotion = {'kind': 'second_unit', 'percent': '50'}
        self.assertEqual([line_total(record, q) for q in (1, 2, 3)], [1000, 1500, 2500])

    def test_restricted_expired_and_unknown_promos_do_not_reduce_total(self):
        record = PriceRecord(price=Decimal('1000'), promo_price=Decimal('1'), promo_text='Beneficio especial')
        self.assertEqual(line_total(record, 1), 1000)
        record.promotion = {'kind': 'nxm', 'take': 2, 'pay': 1, 'restricted': True}
        self.assertEqual(line_total(record, 2), 2000)
        record.promotion = {'kind': 'nxm', 'take': 2, 'pay': 1, 'ends_on': '2000-01-01'}
        self.assertEqual(line_total(record, 2), 2000)
        self.assertTrue(parse_promotion_rule('2x1 con tarjeta del banco')['restricted'])

    def test_promo_date_range_handles_expiry_and_new_year(self):
        from datetime import date
        with mock.patch('changomas.scraper.timezone.localdate', return_value=date(2026, 11, 5)):
            rule = parse_promotion_rule('2x1 del 1/11 al 3/11')
        self.assertEqual(rule['ends_on'], '2026-11-03')
        self.assertEqual(line_total(PriceRecord(price=1000, promotion=rule), 2), 2000)
        with mock.patch('changomas.scraper.timezone.localdate', return_value=date(2027, 1, 2)):
            rule = parse_promotion_rule('2x1 del 28/12 al 5/1')
        self.assertEqual(rule['starts_on'], '2026-12-28')
        self.assertEqual(rule['ends_on'], '2027-01-05')

    def test_intraday_change_updates_daily_row_and_appends_change(self):
        self.observe()
        self.observe(price=Decimal('900'))
        self.observe(price=Decimal('900'))
        self.assertEqual(PriceRecord.objects.count(), 1)
        self.assertEqual(PriceRecord.objects.get().price, 900)
        self.assertEqual(PriceObservation.objects.count(), 2)
        self.product.refresh_from_db()
        self.assertIsNotNone(self.product.catalog_item_id)
        self.assertIsNotNone(self.product.last_price_checked_at)

    def test_stale_price_remains_in_history_but_not_catalog_or_quote(self):
        self.observe()
        Product.objects.filter(pk=self.product.pk).update(last_price_checked_at=timezone.now() - timedelta(hours=37))
        self.assertEqual(self.client.get(reverse('changomas:product_list')).context['total'], 0)
        self.assertEqual(len(quote([(self.product.ean, 1)])['missing']), 1)
        self.assertEqual(PriceRecord.objects.count(), 1)
        response = self.client.get(reverse('changomas:product_detail', args=[self.product.ean]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['freshness'])

    def test_catalog_groups_valid_gtin_and_searches_without_accents(self):
        self.observe()
        other = Product.objects.create(supermarket_id='disco', reference_code='other', ean=self.product.ean,
            vtex_product_id='2', name=self.product.name, brand=self.product.brand, is_comparable=True)
        record_observation(other, {'price': Decimal('1100')})
        response = self.client.get(reverse('changomas:product_list'), {'q': 'serenisima leche'})
        self.assertEqual(response.context['total'], 1)
        self.assertEqual(response.context['groups'][0]['store_count'], 2)
        self.assertContains(response, 'data-comparison-store="changomas"')
        self.assertContains(response, 'data-comparison-store="disco"')
        detail = self.client.get(reverse('changomas:product_detail', args=[self.product.ean]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context['group']['store_count'], 2)
        self.assertEqual(detail.context['best']['effective'], Decimal('1000'))
        padded = self.client.get(reverse('changomas:product_detail', args=['07790742363107']))
        self.assertEqual(padded.status_code, 200)
        self.assertEqual(padded.context['group']['store_count'], 2)


    def test_single_store_listing_without_ean_can_be_added_and_quoted(self):
        self.product.ean = ''
        self.product.is_comparable = False
        self.product.save()
        self.observe()
        key = f'listing-{self.product.pk}'
        self.assertEqual(parse_items([{'ean': key, 'qty': 2}]), [(key, 2)])
        result = quote([(key, 2)])
        self.assertEqual(result['optimal']['total'], 2000)
        self.assertEqual(result['stores'][0]['covered_count'], 1)

    def test_new_api_quotes_quantity_and_flags_incomplete_stores(self):
        self.observe(promo_text='2x1', promo_price=Decimal('500'), promotion={'kind': 'nxm', 'take': 2, 'pay': 1})
        response = self.client.post('/api/v2/supermarkets/quote/', {'items': [{'ean': self.product.ean, 'qty': 1}]}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['optimal_total'], '1000.00')
        self.assertFalse(response.json()['shipping_included'])
        self.assertEqual(self.client.get('/api/v1/supermarkets/products/').status_code, 200)

    def test_legacy_redirect_preserves_queries_and_post_method(self):
        response = self.client.get('/changomas/?q=leche&page=2')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/supermarket-tracker/?q=leche&page=2')
        response = self.client.post('/changomas/carrito/cotizar/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response['Location'], reverse('changomas:cart_quote'))
        self.assertIn('/changomas/producto/', self.client.get('/changomas/producto/123/')['Location'])

    def test_gtin_normalization_checks_digit_and_preserves_zeroes(self):
        self.assertEqual(normalize_gtin('7790742363107'), '07790742363107')
        self.assertIsNone(normalize_gtin('7790742363108'))
        self.assertIsNone(normalize_gtin('vtex-123'))

    @skipUnless(connection.vendor == 'postgresql', 'Production search requires PostgreSQL')
    def test_postgresql_typo_search_and_indexes(self):
        self.observe()
        response = self.client.get(reverse('changomas:product_list'), {'q': 'serenisma'})
        self.assertEqual(response.context['total'], 1)
        with connection.cursor() as cursor:
            cursor.execute("SELECT indexname FROM pg_indexes WHERE tablename='changomas_product'")
            indexes = {row[0] for row in cursor.fetchall()}
        self.assertIn('tracker_search_words', indexes)
        self.assertIn('tracker_search_typos', indexes)


class PayloadBoundsTests(TestCase):
    def test_json_depth_is_bounded_independently_of_python_version(self):
        from .payloads import loads_bounded
        for endpoint in ['/supermarket-tracker/carrito/cotizar/', '/supermarket-tracker/api/quote-html/', '/api/v2/supermarkets/quote/']:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint, '[' * 5000 + ']' * 5000, content_type='application/json')
                self.assertEqual(response.status_code, 400)

    def test_brackets_inside_json_strings_do_not_count_as_nesting(self):
        import json
        from .payloads import loads_bounded
        payload = {'value': '[{' * 1000 + '"escaped"'}
        self.assertEqual(loads_bounded(json.dumps(payload)), payload)
