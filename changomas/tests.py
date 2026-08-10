import json
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from .cart import MAX_CART_ITEMS, MAX_QUANTITY, parse_items, quote
from .models import GTIN_RE, PriceRecord, Product, Supermarket
from .scraper import (
    ScrapeError,
    VtexClient,
    _promo_from_text,
    _safe_url,
    parse_product,
    parse_products,
    parse_promo,
)


class PromoParserTests(SimpleTestCase):
    """El cálculo del precio efectivo de la promo es el corazón de la app."""

    def test_segunda_unidad_al_50(self):
        # 50% en la 2da unidad: se pagan 1.5 cada 2 -> 25% de descuento real
        result = _promo_from_text('50% en la 2da unidad', Decimal('1000'))
        self.assertIsNotNone(result)
        self.assertEqual(result[0], Decimal('750.00'))

    def test_2da_unidad_al_70(self):
        result = _promo_from_text('2da unidad al 70%', Decimal('1000'))
        self.assertIsNotNone(result)
        self.assertEqual(result[0], Decimal('650.00'))

    def test_segunda_unidad_variantes_de_texto(self):
        for text in ('2do al 50%', 'Segunda unidad al 50%', '50% OFF en la 2° unidad'):
            result = _promo_from_text(text, Decimal('200'))
            self.assertIsNotNone(result, f'No parseó: {text}')
            self.assertEqual(result[0], Decimal('150.00'), f'Falló: {text}')

    def test_3x2(self):
        # 3x2: se pagan 2 cada 3 -> 33% de descuento real
        result = _promo_from_text('Lleva 3x2', Decimal('900'))
        self.assertIsNotNone(result)
        self.assertEqual(result[0], Decimal('600.00'))

    def test_2x1(self):
        result = _promo_from_text('2x1 en toda la línea', Decimal('500'))
        self.assertIsNotNone(result)
        self.assertEqual(result[0], Decimal('250.00'))

    def test_texto_sin_promo(self):
        self.assertIsNone(_promo_from_text('Envío gratis', Decimal('100')))
        self.assertIsNone(_promo_from_text('', Decimal('100')))

    def test_pack_no_es_promo(self):
        # "Pack 6x1" describe el empaque, no una promo de cantidad
        self.assertIsNone(_promo_from_text('Galletitas Pack 6x1', Decimal('100')))

    def test_descuento_implausible_se_descarta(self):
        # 6x1 = 83% de descuento: casi seguro un falso positivo
        self.assertIsNone(_promo_from_text('6x1', Decimal('100')))

    def test_parse_promo_formato_legacy_vtex(self):
        # Formato del API legacy con claves '<Name>k__BackingField'
        offer = {
            'Teasers': [{'<Name>k__BackingField': '2da unidad al 50%'}],
            'PromotionTeasers': [],
            'DiscountHighLight': [],
        }
        promo_price, promo_text = parse_promo(offer, Decimal('1000'))
        self.assertEqual(promo_price, Decimal('750.00'))
        self.assertIn('50%', promo_text)

    def test_parse_promo_estructurado(self):
        # Teaser sin nombre parseable pero con estructura condiciones/efectos
        offer = {
            'Teasers': [{
                'name': 'Promo especial',
                'conditions': {'minimumQuantity': 2, 'parameters': []},
                'effects': {'parameters': [{'name': 'discount', 'value': '50'}]},
            }],
        }
        promo_price, _ = parse_promo(offer, Decimal('1000'))
        self.assertEqual(promo_price, Decimal('750.00'))

    def test_parse_promo_sin_promos(self):
        promo_price, promo_text = parse_promo({'Teasers': []}, Decimal('100'))
        self.assertIsNone(promo_price)
        self.assertEqual(promo_text, '')

    def test_parse_promo_elige_la_mejor(self):
        offer = {
            'Teasers': [
                {'name': '2da unidad al 50%'},   # efectivo 750
                {'name': '3x2'},                 # efectivo 666.67
            ],
        }
        promo_price, promo_text = parse_promo(offer, Decimal('1000'))
        self.assertEqual(promo_price, Decimal('666.67'))
        self.assertEqual(promo_text, '3x2')


class ParseProductTests(SimpleTestCase):

    def _raw_product(self, **overrides):
        raw = {
            'productId': '220932',
            'productReference': '103705567',
            'productName': 'Puré De Tomate Arcor 520 G',
            'brand': 'Arcor',
            'link': 'https://www.masonline.com.ar/pure-de-tomate/p',
            'categories': ['/Conservas/Tomates/Pure/', '/Conservas/'],
            'items': [{
                'ean': '7790580146115',
                'images': [{'imageUrl': 'https://img.example.com/p.jpg'}],
                'sellers': [{
                    'sellerDefault': True,
                    'commertialOffer': {
                        'Price': 1129.0,
                        'ListPrice': 1500.0,
                        'IsAvailable': True,
                        'Teasers': [],
                    },
                }],
            }],
        }
        raw.update(overrides)
        return raw

    def test_parseo_basico(self):
        parsed = parse_product(self._raw_product())
        self.assertEqual(parsed['reference_code'], '7790580146115')
        self.assertEqual(parsed['ean'], '7790580146115')
        self.assertEqual(parsed['vtex_product_id'], '220932')
        self.assertEqual(parsed['vtex_sku_id'], '220932')
        self.assertEqual(parsed['price'], Decimal('1129.00'))
        self.assertEqual(parsed['list_price'], Decimal('1500.00'))
        self.assertIsNone(parsed['promo_price'])
        self.assertEqual(parsed['category'], 'Conservas / Tomates / Pure')

    def test_sin_ean_usa_referencia_vtex(self):
        raw = self._raw_product()
        raw['items'][0]['ean'] = ''
        parsed = parse_product(raw)
        self.assertEqual(parsed['reference_code'], 'vtex-220932')

    def test_sin_precio_devuelve_none(self):
        raw = self._raw_product()
        raw['items'][0]['sellers'][0]['commertialOffer']['Price'] = 0
        self.assertIsNone(parse_product(raw))

    def test_sin_items_devuelve_none(self):
        self.assertIsNone(parse_product({'productId': '1', 'items': []}))

    def test_urls_con_esquema_peligroso_se_descartan(self):
        raw = self._raw_product()
        raw['items'][0]['images'] = [{'imageUrl': 'javascript:alert(1)'}]
        raw['link'] = 'data:text/html,<script>alert(1)</script>'
        parsed = parse_product(raw)
        self.assertEqual(parsed['image_url'], '')
        self.assertEqual(parsed['link'], '')

    def test_safe_url(self):
        self.assertEqual(_safe_url('https://ok.com/img.jpg'), 'https://ok.com/img.jpg')
        self.assertEqual(_safe_url('javascript:alert(1)'), '')
        self.assertEqual(_safe_url(None), '')

    def test_disco_descarta_list_price_implausible(self):
        raw = self._raw_product()
        raw['items'][0]['sellers'][0]['commertialOffer']['Price'] = 1110
        raw['items'][0]['sellers'][0]['commertialOffer']['ListPrice'] = 91736
        parsed = parse_product(raw, store='disco')
        self.assertEqual(parsed['price'], Decimal('1110.00'))
        self.assertIsNone(parsed['list_price'])

    def test_parsea_todos_los_skus_vendibles(self):
        raw = self._raw_product()
        second_item = {
            **raw['items'][0],
            'itemId': 'sku-2',
            'ean': '7790580146116',
            'nameComplete': 'Puré De Tomate Arcor 1 Kg',
        }
        raw['items'][0]['itemId'] = 'sku-1'
        raw['items'].append(second_item)
        products = parse_products(raw)
        self.assertEqual(len(products), 2)
        self.assertEqual(
            {product['vtex_sku_id'] for product in products}, {'sku-1', 'sku-2'},
        )

    def test_categoria_truncada_se_reporta_como_falla(self):
        client = VtexClient(delay=0)
        client._get_json = mock.Mock(return_value=[{}] * 50)
        with self.assertRaises(ScrapeError):
            list(client.iter_category_products('1/2'))


class ModelTests(TestCase):

    def test_mismo_ean_y_vtex_id_puede_existir_en_distintos_supermercados(self):
        carrefour = Supermarket.objects.get(slug='carrefour')
        disco = Supermarket.objects.get(slug='disco')
        Product.objects.create(
            supermarket=carrefour, reference_code='779', ean='779',
            vtex_product_id='1', name='Producto Carrefour',
        )
        Product.objects.create(
            supermarket=disco, reference_code='779', ean='779',
            vtex_product_id='1', name='Producto Disco',
        )
        self.assertEqual(Product.objects.filter(ean='779').count(), 2)

    def test_effective_price_y_descuento(self):
        product = Product.objects.create(
            reference_code='7790580146115',
            ean='7790580146115',
            vtex_product_id='220932',
            name='Puré De Tomate',
        )
        record = PriceRecord.objects.create(
            product=product,
            date=timezone.localdate(),
            price=Decimal('1000.00'),
            list_price=Decimal('2000.00'),
            promo_price=Decimal('750.00'),
            promo_text='2da al 50%',
        )
        self.assertEqual(record.effective_price, Decimal('750.00'))
        self.assertEqual(record.discount_percent, 50)
        self.assertEqual(product.latest_price, record)

    def test_precio_unico_por_dia(self):
        product = Product.objects.create(
            reference_code='x', vtex_product_id='1', name='Test',
        )
        today = timezone.localdate()
        PriceRecord.objects.create(product=product, date=today, price=Decimal('10'))
        rows = PriceRecord.objects.bulk_create(
            [PriceRecord(product=product, date=today, price=Decimal('99'))],
            ignore_conflicts=True,
        )
        self.assertEqual(PriceRecord.objects.filter(product=product, date=today).count(), 1)
        self.assertEqual(PriceRecord.objects.get(product=product, date=today).price, Decimal('10'))


class ViewTests(TestCase):

    def setUp(self):
        # cache_page + LocMemCache persisten entre tests del mismo proceso
        cache.clear()

    def test_vista_gondola(self):
        product = Product.objects.create(
            reference_code='7790580146115',
            ean='7790580146115',
            vtex_product_id='220932',
            name='Puré De Tomate Arcor',
            brand='Arcor',
            category='Conservas / Tomates',
        )
        PriceRecord.objects.create(
            product=product,
            date=timezone.localdate(),
            price=Decimal('1129.00'),
            list_price=Decimal('1500.00'),
            promo_price=Decimal('846.75'),
            promo_text='2da unidad al 50%',
        )
        response = self.client.get(reverse('changomas:product_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Puré De Tomate Arcor')
        self.assertContains(response, '7790580146115')
        self.assertContains(response, '2da unidad al 50%')

    def test_busqueda(self):
        Product.objects.create(reference_code='a', vtex_product_id='1', name='Leche Entera')
        Product.objects.create(reference_code='b', vtex_product_id='2', name='Pan Lactal')
        response = self.client.get(reverse('changomas:product_list'), {'q': 'leche'})
        self.assertContains(response, 'Leche Entera')
        self.assertNotContains(response, 'Pan Lactal')

    def test_busqueda_flexible(self):
        Product.objects.create(
            reference_code='c', vtex_product_id='3',
            name='Puré De Tomate Arcor 520 G', brand='Arcor')
        Product.objects.create(
            reference_code='d', vtex_product_id='4',
            name='Café Torrado La Virginia', brand='La Virginia')
        Product.objects.create(
            reference_code='e', vtex_product_id='5', name='Pan Lactal')

        # Palabras en cualquier orden y sin la preposición
        response = self.client.get(reverse('changomas:product_list'), {'q': 'tomate pure'})
        self.assertContains(response, 'Puré De Tomate')
        self.assertNotContains(response, 'Pan Lactal')

        # Sin acento encuentra el acentuado (y viceversa)
        response = self.client.get(reverse('changomas:product_list'), {'q': 'cafe'})
        self.assertContains(response, 'Café Torrado')
        response = self.client.get(reverse('changomas:product_list'), {'q': 'café'})
        self.assertContains(response, 'Café Torrado')

        # Busca también por marca
        response = self.client.get(reverse('changomas:product_list'), {'q': 'virginia'})
        self.assertContains(response, 'Café Torrado')

        # Mezcla nombre + marca en el mismo query
        response = self.client.get(reverse('changomas:product_list'), {'q': 'arcor tomate'})
        self.assertContains(response, 'Puré De Tomate')
        self.assertNotContains(response, 'Café Torrado')

    def test_busqueda_con_metacaracteres_no_rompe(self):
        Product.objects.create(reference_code='f', vtex_product_id='6', name='Gaseosa 2.25 L')
        response = self.client.get(
            reverse('changomas:product_list'), {'q': 'c++ (test) [x]'})
        self.assertEqual(response.status_code, 200)
        # El punto se trata como literal, no como comodín
        response = self.client.get(reverse('changomas:product_list'), {'q': '2.25'})
        self.assertContains(response, 'Gaseosa 2.25 L')

    def test_catalogos_estan_aislados_por_supermercado(self):
        carrefour = Supermarket.objects.get(slug='carrefour')
        Product.objects.create(
            supermarket=carrefour, reference_code='carrefour-1',
            vtex_product_id='1', name='Solo Carrefour',
        )
        changomas = self.client.get(reverse('changomas:product_list'))
        carrefour_response = self.client.get(
            reverse('changomas:store_product_list', args=['carrefour'])
        )
        self.assertNotContains(changomas, 'Solo Carrefour')
        self.assertContains(carrefour_response, 'Solo Carrefour')

    def test_selector_y_estado_vacio_tienen_traduccion_inglesa(self):
        response = self.client.get(
            reverse('changomas:store_product_list', args=['disco']),
            HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertContains(response, 'Supermarkets')
        self.assertContains(response, 'Run the scraper to populate the database')
        self.assertContains(response, '<code>python manage.py scrape_supermarkets</code>')


class ProductDetailViewTests(TestCase):

    def setUp(self):
        cache.clear()

    def _make_product_with_history(self):
        product = Product.objects.create(
            reference_code='7790580146115',
            ean='7790580146115',
            vtex_product_id='220932',
            product_reference='103705567',
            name='Puré De Tomate Arcor',
            brand='Arcor',
            category='Conservas / Tomates',
        )
        today = timezone.localdate()
        for days_ago, price in ((20, '1000.00'), (10, '1500.00'), (0, '1200.00')):
            PriceRecord.objects.create(
                product=product,
                date=today - timezone.timedelta(days=days_ago),
                price=Decimal(price),
            )
        return product

    def test_detalle_por_ean_muestra_max_min(self):
        self._make_product_with_history()
        response = self.client.get(
            reverse('changomas:product_detail', args=['7790580146115']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Puré De Tomate Arcor')
        self.assertContains(response, '1.000,00')   # mínimo 30 días
        self.assertContains(response, '1.500,00')   # máximo 30 días
        self.assertContains(response, '1.200,00')   # precio actual
        self.assertContains(response, 'Evolución del precio')
        # links cruzados con el escáner y el catálogo
        self.assertContains(
            response, reverse('changomas:store_scan', args=['changomas']))
        self.assertContains(
            response, reverse('changomas:store_product_list', args=['changomas']))

    def test_detalle_por_referencia_vtex(self):
        # Si el EAN no está, se puede buscar por la referencia interna de VTEX
        self._make_product_with_history()
        for code in ('103705567', '220932'):
            response = self.client.get(
                reverse('changomas:product_detail', args=[code]))
            self.assertEqual(response.status_code, 200, f'Falló con código {code}')
            self.assertContains(response, 'Puré De Tomate Arcor')

    def test_max_min_usa_precio_efectivo_de_promo(self):
        product = Product.objects.create(
            reference_code='779', vtex_product_id='1', name='Con Promo')
        today = timezone.localdate()
        PriceRecord.objects.create(
            product=product, date=today - timezone.timedelta(days=5),
            price=Decimal('1000.00'), promo_price=Decimal('750.00'),
            promo_text='2da al 50%')
        PriceRecord.objects.create(
            product=product, date=today, price=Decimal('900.00'))
        response = self.client.get(reverse('changomas:product_detail', args=['779']))
        # el mínimo debe ser el precio efectivo de la promo (750), no 900
        self.assertContains(response, '750,00')

    def test_codigo_inexistente_devuelve_404(self):
        response = self.client.get(
            reverse('changomas:product_detail', args=['0000000000000']))
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'no encontrado', status_code=404)

    def test_codigo_con_caracteres_invalidos_devuelve_404(self):
        response = self.client.get('/changomas/producto/%3Cscript%3Ealert(1)%3C%2Fscript%3E/')
        self.assertEqual(response.status_code, 404)
        # el input queda escapado por el autoescape del template
        self.assertNotContains(response, '<script>alert', status_code=404)

    def test_404_se_cachea_y_no_vuelve_a_consultar_la_db(self):
        url = reverse('changomas:product_detail', args=['9999999999999'])
        self.assertEqual(self.client.get(url).status_code, 404)
        with self.assertNumQueries(1):  # valida el supermercado; no consulta Product
            response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_producto_sin_historial(self):
        Product.objects.create(reference_code='sin-datos', vtex_product_id='9', name='Nuevo')
        response = self.client.get(reverse('changomas:product_detail', args=['sin-datos']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'no hay precios registrados')

    def test_ean_duplicado_devuelve_al_dueno_del_codigo(self):
        # Dos productos comparten EAN; el "dueño" es el que lo tiene como
        # reference_code, aunque su nombre ordene alfabéticamente después.
        Product.objects.create(
            reference_code='vtex-2', vtex_product_id='2',
            ean='7790000000001', name='AAA Impostor')
        Product.objects.create(
            reference_code='7790000000001', vtex_product_id='1',
            ean='7790000000001', name='ZZZ Dueño')
        response = self.client.get(
            reverse('changomas:product_detail', args=['7790000000001']))
        self.assertContains(response, 'ZZZ Dueño')
        self.assertNotContains(response, 'AAA Impostor')

    def test_solo_muestra_registros_de_los_ultimos_30_dias(self):
        product = Product.objects.create(
            reference_code='r', vtex_product_id='7', name='Con Historia Vieja')
        today = timezone.localdate()
        PriceRecord.objects.create(
            product=product, date=today - timezone.timedelta(days=45),
            price=Decimal('1.00'))  # este mínimo NO debe aparecer
        PriceRecord.objects.create(product=product, date=today, price=Decimal('500.00'))
        response = self.client.get(reverse('changomas:product_detail', args=['r']))
        self.assertNotContains(response, '$ 1,00')
        self.assertContains(response, '500,00')


class BuildChartTests(SimpleTestCase):

    def _record(self, price):
        record = mock.Mock()
        record.effective_price = Decimal(price)
        return record

    def test_sin_registros_o_uno_solo_devuelve_none(self):
        from .views import _build_chart
        self.assertIsNone(_build_chart([]))
        self.assertIsNone(_build_chart([self._record('100')]))

    def test_dos_precios_iguales_no_divide_por_cero(self):
        from .views import _build_chart
        chart = _build_chart([self._record('100'), self._record('100')])
        self.assertIsNotNone(chart)
        self.assertEqual(len(chart['points'].split()), 2)

    def test_puntos_del_grafico(self):
        from .views import _build_chart
        chart = _build_chart([self._record('100'), self._record('200'), self._record('150')])
        points = chart['points'].split()
        self.assertEqual(len(points), 3)
        # el máximo (200) debe estar más arriba (y menor) que el mínimo (100)
        y_values = [float(p.split(',')[1]) for p in points]
        self.assertLess(y_values[1], y_values[0])
        self.assertEqual(chart['last_x'], points[-1].split(',')[0])


class ScanViewTests(TestCase):

    def setUp(self):
        cache.clear()

    def test_pagina_escanear(self):
        response = self.client.get(reverse('changomas:scan'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'BarcodeDetector')
        self.assertContains(
            response, reverse('changomas:store_product_list', args=['changomas']))

    def test_catalogo_linkea_al_escaner(self):
        response = self.client.get(reverse('changomas:product_list'))
        self.assertContains(response, reverse('changomas:store_scan', args=['changomas']))


def _raw(vtex_id, ean, name='Producto', price=100.0):
    return {
        'productId': vtex_id,
        'productReference': f'ref-{vtex_id}',
        'productName': name,
        'brand': 'Marca',
        'link': 'https://www.masonline.com.ar/p',
        'categories': ['/Almacen/'],
        'items': [{
            'ean': ean,
            'images': [],
            'sellers': [{
                'sellerDefault': True,
                'commertialOffer': {'Price': price, 'ListPrice': price, 'IsAvailable': True},
            }],
        }],
    }


class ScrapeCommandTests(TestCase):
    """Integración del comando con el cliente HTTP mockeado."""

    def _run_command(self, categories, products_by_category):
        with mock.patch('changomas.management.commands.scrape_masonline.MasOnlineClient') as client_cls:
            client = client_cls.return_value
            client.get_leaf_categories.return_value = categories

            def iterate(category_id):
                items = products_by_category[category_id]
                if isinstance(items, Exception):
                    raise items
                yield from items

            client.iter_category_products.side_effect = iterate
            call_command('scrape_masonline', verbosity=0)

    def test_is_comparable_se_recalcula_si_cambia_el_ean(self):
        # Primera corrida con EAN de largo inválido: no comparable
        self._run_command([('1', 'Almacén')], {'1': [_raw('10', '123')]})
        product = Product.objects.get(vtex_product_id='10')
        self.assertFalse(product.is_comparable)
        # El catálogo corrige el EAN: el flag debe recalcularse en el update
        self._run_command([('1', 'Almacén')], {'1': [_raw('10', '7790000000135')]})
        product.refresh_from_db()
        self.assertTrue(product.is_comparable)

    def test_ean_duplicado_en_el_mismo_lote_no_rompe(self):
        # Dos productos NUEVOS con el mismo EAN en la misma categoría:
        # el segundo debe caer al código vtex- sin abortar la corrida.
        self._run_command(
            [('1', 'Almacén')],
            {'1': [_raw('10', '779000000001', 'Uno'), _raw('11', '779000000001', 'Dos')]},
        )
        self.assertEqual(Product.objects.count(), 2)
        codes = set(Product.objects.values_list('reference_code', flat=True))
        self.assertEqual(codes, {'779000000001', 'vtex-11'})
        self.assertEqual(PriceRecord.objects.count(), 2)

    def test_purga_historial_viejo(self):
        product = Product.objects.create(reference_code='x', vtex_product_id='10', name='Viejo')
        old_date = timezone.localdate() - timezone.timedelta(days=35)
        edge_date = timezone.localdate() - timezone.timedelta(days=29)
        PriceRecord.objects.create(product=product, date=old_date, price=Decimal('1'))
        PriceRecord.objects.create(product=product, date=edge_date, price=Decimal('2'))
        self._run_command([('1', 'Almacén')], {'1': [_raw('10', 'x', 'Viejo')]})
        dates = set(PriceRecord.objects.values_list('date', flat=True))
        self.assertNotIn(old_date, dates)      # purgado (> 30 días)
        self.assertIn(edge_date, dates)        # conservado (día 30 exacto)

    def test_producto_ausente_se_marca_no_disponible(self):
        stale = Product.objects.create(reference_code='old', vtex_product_id='99', name='Ausente')
        Product.objects.filter(pk=stale.pk).update(
            last_seen=timezone.now() - timezone.timedelta(days=2))
        self._run_command([('1', 'Almacén')], {'1': [_raw('10', 'nuevo-ean')]})
        stale.refresh_from_db()
        self.assertFalse(stale.is_available)

    def test_corrida_parcial_no_marca_no_disponibles(self):
        # --max-categories es para pruebas: no vio el catálogo completo,
        # así que no debe marcar productos como no disponibles.
        stale = Product.objects.create(reference_code='old', vtex_product_id='99', name='Ausente')
        Product.objects.filter(pk=stale.pk).update(
            last_seen=timezone.now() - timezone.timedelta(days=2))
        with mock.patch('changomas.management.commands.scrape_masonline.MasOnlineClient') as client_cls:
            client = client_cls.return_value
            client.get_leaf_categories.return_value = [('1', 'Almacén')]
            client.iter_category_products.side_effect = lambda cid: iter([_raw('10', 'nuevo-ean')])
            call_command('scrape_masonline', max_categories=1, verbosity=0)
        stale.refresh_from_db()
        self.assertTrue(stale.is_available)

    def test_categoria_fallida_no_marca_no_disponibles(self):
        # Si una categoría falló, no podemos saber si sus productos
        # desaparecieron o simplemente no se pudieron bajar: no se marca nada.
        stale = Product.objects.create(reference_code='old', vtex_product_id='99', name='Ausente')
        Product.objects.filter(pk=stale.pk).update(
            last_seen=timezone.now() - timezone.timedelta(days=2))
        with self.assertRaises(CommandError):
            self._run_command(
                [('1', 'Almacén'), ('2', 'Bebidas')],
                {'1': [_raw('10', 'nuevo-ean')], '2': ScrapeError('API caída')},
            )
        stale.refresh_from_db()
        self.assertTrue(stale.is_available)
        # Lo que sí se bajó, se guardó igual
        self.assertTrue(Product.objects.filter(vtex_product_id='10').exists())

    def test_arbol_vacio_hace_fallar_el_comando(self):
        with mock.patch('changomas.management.commands.scrape_masonline.MasOnlineClient') as client_cls:
            client_cls.return_value.get_leaf_categories.return_value = []
            with self.assertRaises(CommandError):
                call_command('scrape_masonline', verbosity=0)

    def test_purga_solo_afecta_al_supermercado_ejecutado(self):
        disco = Supermarket.objects.get(slug='disco')
        old_date = timezone.localdate() - timezone.timedelta(days=20)
        changomas_product = Product.objects.create(
            reference_code='chango-old', vtex_product_id='200', name='Chango viejo',
        )
        disco_product = Product.objects.create(
            supermarket=disco, reference_code='disco-old',
            vtex_product_id='200', name='Disco viejo',
        )
        PriceRecord.objects.create(
            product=changomas_product, date=old_date, price=Decimal('1'),
        )
        disco_price = PriceRecord.objects.create(
            product=disco_product, date=old_date, price=Decimal('1'),
        )
        with mock.patch('changomas.management.commands.scrape_masonline.MasOnlineClient') as client_cls:
            client = client_cls.return_value
            client.get_leaf_categories.return_value = [('1', 'Almacén')]
            client.iter_category_products.return_value = iter([_raw('10', 'nuevo')])
            call_command('scrape_masonline', keep_days=7, verbosity=0)
        self.assertFalse(PriceRecord.objects.filter(product=changomas_product).exists())
        self.assertTrue(PriceRecord.objects.filter(pk=disco_price.pk).exists())

    def test_un_product_id_con_dos_skus_guarda_dos_publicaciones(self):
        raw = _raw('10', 'ean-1')
        raw['items'][0]['itemId'] = 'sku-1'
        raw['items'].append({
            **raw['items'][0], 'itemId': 'sku-2', 'ean': 'ean-2',
        })
        self._run_command([('1', 'Almacén')], {'1': [raw]})
        self.assertEqual(Product.objects.filter(vtex_product_id='10').count(), 2)
        self.assertEqual(PriceRecord.objects.count(), 2)

    def test_scrape_de_disco_no_modifica_changomas(self):
        disco = Supermarket.objects.get(slug='disco')
        changomas_product = Product.objects.create(
            reference_code='compartido', vtex_product_id='99', name='Chango',
        )
        disco_product = Product.objects.create(
            supermarket=disco, reference_code='viejo',
            vtex_product_id='98', name='Disco viejo',
        )
        old_seen = timezone.now() - timezone.timedelta(days=2)
        Product.objects.filter(pk__in=[changomas_product.pk, disco_product.pk]).update(
            last_seen=old_seen,
        )

        with mock.patch('changomas.management.commands.scrape_masonline.VtexClient') as client_cls:
            client = client_cls.return_value
            client.get_leaf_categories.return_value = [('1', 'Almacén')]
            client.iter_category_products.return_value = iter([
                _raw('99', 'compartido', 'Disco nuevo'),
            ])
            call_command('scrape_masonline', store='disco', verbosity=0)

        changomas_product.refresh_from_db()
        disco_product.refresh_from_db()
        self.assertTrue(changomas_product.is_available)
        self.assertFalse(disco_product.is_available)
        self.assertTrue(Product.objects.filter(
            supermarket=disco, vtex_product_id='99',
        ).exists())


class SupermarketApiTests(TestCase):

    def setUp(self):
        cache.clear()
        carrefour = Supermarket.objects.get(slug='carrefour')
        disco = Supermarket.objects.get(slug='disco')
        self.carrefour_product = Product.objects.create(
            supermarket=carrefour, reference_code='7790580146115',
            ean='7790580146115', vtex_product_id='739689',
            name='Puré Carrefour', brand='Arcor', category='Almacén / Conservas',
        )
        self.disco_product = Product.objects.create(
            supermarket=disco, reference_code='7790580146115',
            ean='7790580146115', vtex_product_id='420198',
            name='Puré Disco', brand='Arcor', category='Almacén / Conservas',
        )
        PriceRecord.objects.create(
            product=self.carrefour_product, date=timezone.localdate(),
            price=Decimal('1110.00'),
        )

    def test_lista_supermercados(self):
        response = self.client.get(reverse('supermarkets_api:store-list'))
        self.assertEqual(response.status_code, 200)
        slugs = {item['slug'] for item in response.json()}
        self.assertEqual(slugs, {'changomas', 'carrefour', 'disco'})

    def test_productos_se_pueden_filtrar_por_ean_y_supermercado(self):
        url = reverse('supermarkets_api:product-list')
        response = self.client.get(url, {'ean': '7790580146115'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 2)

        response = self.client.get(url, {
            'ean': '7790580146115', 'store': 'carrefour',
        })
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(
            response.json()['results'][0]['supermarket']['slug'], 'carrefour',
        )

    def test_detalle_incluye_precio_e_historial(self):
        response = self.client.get(reverse(
            'supermarkets_api:product-detail', args=[self.carrefour_product.pk],
        ))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['latest_price']['price'], '1110.00')
        self.assertEqual(len(payload['price_history']), 1)
        self.assertEqual(payload['stats']['days'], 1)

    def test_no_expone_productos_de_supermercado_inactivo(self):
        Supermarket.objects.filter(slug='disco').update(is_active=False)
        response = self.client.get(reverse('supermarkets_api:product-list'), {
            'ean': '7790580146115',
        })
        self.assertEqual(response.json()['count'], 1)
        detail = self.client.get(reverse(
            'supermarkets_api:product-detail', args=[self.disco_product.pk],
        ))
        self.assertEqual(detail.status_code, 404)


class ScrapeAllCommandTests(SimpleTestCase):

    def test_una_tienda_fallida_no_impide_intentar_las_restantes(self):
        target = 'changomas.management.commands.scrape_supermarkets.call_command'
        with mock.patch(target) as nested_call:
            nested_call.side_effect = [CommandError('Carrefour caído'), None, None]
            with self.assertRaises(CommandError):
                call_command('scrape_supermarkets', verbosity=0)
        self.assertEqual(nested_call.call_count, 3)


class ComparadorTests(TestCase):
    """Vista Comparador: agrupación por EAN entre tiendas, mejor precio,
    stats combinadas y resolución de códigos."""

    def setUp(self):
        cache.clear()
        self.changomas = Supermarket.objects.get(slug='changomas')
        self.carrefour = Supermarket.objects.get(slug='carrefour')
        self.disco = Supermarket.objects.get(slug='disco')

    def _make(self, store, ean, name, price, promo_price=None, promo_text='',
              days_ago=0, available=True, reference_code=None):
        product, _ = Product.objects.get_or_create(
            supermarket=store,
            reference_code=reference_code or ean or f'ref-{store.slug}-{name}',
            defaults={
                'ean': ean,
                'vtex_product_id': f'{store.slug}-{ean or name}',
                'name': name,
                'is_available': available,
                'is_comparable': bool(GTIN_RE.match(ean or '')),
            },
        )
        PriceRecord.objects.create(
            product=product,
            date=timezone.localdate() - timezone.timedelta(days=days_ago),
            price=Decimal(price),
            promo_price=Decimal(promo_price) if promo_price else None,
            promo_text=promo_text,
        )
        return product

    def test_agrupa_por_ean_y_muestra_el_mejor_precio(self):
        self._make(self.changomas, '7790000000012', 'Leche Entera 1L', '1500')
        self._make(self.carrefour, '7790000000012', 'Leche Entera 1L', '1200')
        response = self.client.get(reverse('changomas:comparador_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1.200,00')
        self.assertContains(response, 'Carrefour')
        self.assertContains(response, 'en 2 tiendas')
        # un solo card para el grupo (un solo link al detalle)
        detail_url = reverse('changomas:comparador_detail', args=['7790000000012'])
        self.assertContains(response, detail_url, count=1)

    def test_promo_cuenta_para_el_mejor_precio(self):
        self._make(self.changomas, '7790000000029', 'Galletitas', '1000')
        self._make(self.carrefour, '7790000000029', 'Galletitas', '1100',
                   promo_price='800', promo_text='2da al 50%')
        response = self.client.get(reverse('changomas:comparador_list'))
        self.assertContains(response, '800,00')
        # El mejor precio es el efectivo de la promo de Carrefour
        content = response.content.decode()
        best_pos = content.find('class="store-name')
        self.assertNotEqual(best_pos, -1, 'no se encontró la etiqueta de tienda')
        self.assertIn('Carrefour', content[best_pos:best_pos + 200])

    def test_producto_de_una_sola_tienda_aparece(self):
        self._make(self.disco, '7790000000036', 'Yerba Especial', '5000')
        response = self.client.get(reverse('changomas:comparador_list'))
        self.assertContains(response, 'Yerba Especial')
        self.assertContains(response, 'en 1 tienda')

    def test_ean_invalido_o_vacio_queda_fuera(self):
        self._make(self.changomas, '', 'Sin EAN', '100', reference_code='vtex-991')
        self._make(self.changomas, '12345', 'EAN corto', '100', reference_code='12345')
        response = self.client.get(reverse('changomas:comparador_list'))
        self.assertNotContains(response, 'Sin EAN')
        self.assertNotContains(response, 'EAN corto')

    def test_no_disponible_no_participa(self):
        self._make(self.changomas, '7790000000043', 'Aceite', '2000')
        self._make(self.disco, '7790000000043', 'Aceite', '20', available=False)
        response = self.client.get(reverse('changomas:comparador_list'))
        # El precio basura del SKU no disponible de Disco no gana
        self.assertContains(response, '2.000,00')
        self.assertContains(response, 'en 1 tienda')

    def test_busqueda(self):
        self._make(self.changomas, '7790000000050', 'Pan Lactal', '3000')
        self._make(self.changomas, '7790000000067', 'Arroz Largo', '2000')
        response = self.client.get(reverse('changomas:comparador_list'), {'q': 'pan'})
        self.assertContains(response, 'Pan Lactal')
        self.assertNotContains(response, 'Arroz Largo')

    def test_busqueda_flexible_en_comparador(self):
        self._make(self.changomas, '7790000000149', 'Puré De Tomate Salsati', '1500')
        self._make(self.disco, '7790000000149', 'Puré De Tomate Salsati', '1400')
        self._make(self.changomas, '7790000000156', 'Arroz Largo', '2000')
        # multi-palabra, sin acentos y en otro orden
        response = self.client.get(
            reverse('changomas:comparador_list'), {'q': 'tomate pure'})
        self.assertContains(response, 'Puré De Tomate Salsati')
        self.assertNotContains(response, 'Arroz Largo')

    def test_detalle_combina_las_tiendas(self):
        # Historia en dos tiendas: el mínimo vive en Carrefour (900, hace 10
        # días) y el máximo en ChangoMás (1800, hace 5); hoy gana Carrefour.
        self._make(self.changomas, '7790000000074', 'Café Molido', '1500')
        self._make(self.changomas, '7790000000074', 'Café Molido', '1800', days_ago=5)
        self._make(self.carrefour, '7790000000074', 'Café Molido', '1300')
        self._make(self.carrefour, '7790000000074', 'Café Molido', '900', days_ago=10)
        response = self.client.get(
            reverse('changomas:comparador_detail', args=['7790000000074']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '900,00')    # mínimo combinado
        self.assertContains(response, '1.800,00')  # máximo combinado
        self.assertContains(response, '1.300,00')  # mejor precio hoy
        self.assertContains(response, 'MÁS BARATO')
        # Gráfico con una línea por tienda
        self.assertContains(response, 'polyline', count=2)
        # Links a las fichas por tienda
        self.assertContains(response, reverse(
            'changomas:store_product_detail', args=['changomas', '7790000000074']))
        self.assertContains(response, reverse(
            'changomas:store_product_detail', args=['carrefour', '7790000000074']))

    def test_detalle_por_codigo_propio_de_una_tienda(self):
        # El producto de Disco no tiene el EAN como reference_code, pero
        # escanear su código interno tiene que llegar al grupo completo.
        self._make(self.changomas, '7790000000081', 'Queso Cremoso', '4000')
        self._make(self.disco, '7790000000081', 'Queso Cremoso', '3500',
                   reference_code='vtex-disco-55')
        response = self.client.get(
            reverse('changomas:comparador_detail', args=['vtex-disco-55']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ChangoMás')
        self.assertContains(response, 'Disco')
        self.assertContains(response, '3.500,00')

    def test_detalle_codigo_inexistente_404_y_cache_negativa(self):
        url = reverse('changomas:comparador_detail', args=['0000000000000'])
        self.assertEqual(self.client.get(url).status_code, 404)
        with self.assertNumQueries(0):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'comparador', status_code=404)

    def test_escaner_del_comparador(self):
        response = self.client.get(reverse('changomas:comparador_scan'))
        self.assertEqual(response.status_code, 200)
        # El escáner apunta al detalle del comparador, no al de una tienda
        self.assertContains(response, '/changomas/comparador/producto/')
        self.assertContains(response, reverse('changomas:comparador_list'))

    def test_listado_linkea_al_comparador_y_viceversa(self):
        response = self.client.get(
            reverse('changomas:store_product_list', args=['changomas']))
        self.assertContains(response, reverse('changomas:comparador_list'))
        self._make(self.changomas, '7790000000098', 'Fideos', '1000')
        response = self.client.get(reverse('changomas:comparador_list'))
        self.assertContains(response, reverse(
            'changomas:store_product_list', args=['changomas']))

    def test_ean_duplicado_en_la_misma_tienda_no_duplica_ofertas(self):
        # Dos publicaciones del mismo EAN dentro de ChangoMás (SKUs
        # duplicados del catálogo): el comparador debe mostrar UNA sola
        # oferta para la tienda, con el precio más barato de las dos.
        self._make(self.changomas, '7790000000104', 'Leche Pack A', '1000')
        duplicate = Product.objects.create(
            supermarket=self.changomas, reference_code='vtex-dup-2',
            ean='7790000000104', vtex_product_id='dup-2',
            vtex_sku_id='dup-2-sku', name='Leche Pack B', is_comparable=True)
        PriceRecord.objects.create(
            product=duplicate, date=timezone.localdate(), price=Decimal('900'))

        response = self.client.get(reverse('changomas:comparador_list'))
        self.assertContains(response, 'en 1 tienda')   # una sola cadena real
        self.assertContains(response, '900,00')        # gana el más barato

        response = self.client.get(
            reverse('changomas:comparador_detail', args=['7790000000104']))
        # Contamos dentro del bloque de ofertas: el nombre de la cadena también
        # aparece en la ficha de arriba, así que un count global no dice nada.
        offers = response.content.decode().split('class="offers"', 1)[1]
        self.assertEqual(offers.count('class="offer__store"'), 1)
        self.assertEqual(offers.count('ChangoMás'), 1)

    def test_disponible_sin_precio_reciente_queda_fuera_del_listado(self):
        # Producto que sigue "disponible" pero cuyo último precio es de hace
        # 40 días (fuera de la ventana): no debe contarse ni renderizarse,
        # así el total del header y la paginación quedan consistentes.
        self._make(self.changomas, '7790000000111', 'Producto Viejo', '1000',
                   days_ago=40)
        response = self.client.get(reverse('changomas:comparador_list'))
        self.assertNotContains(response, 'Producto Viejo')
        self.assertContains(response, 'No hay productos comparables')

    def test_grafico_con_un_solo_punto_por_tienda_dibuja_circulos(self):
        self._make(self.changomas, '7790000000128', 'Té Verde', '2000')
        self._make(self.disco, '7790000000128', 'Té Verde', '1900')
        response = self.client.get(
            reverse('changomas:comparador_detail', args=['7790000000128']))
        content = response.content.decode()
        # 1 registro por tienda: dos círculos, ninguna línea
        self.assertEqual(content.count('<circle'), 2)
        self.assertNotIn('<polyline', content)

    def test_la_ruta_comparador_no_la_captura_el_slug_de_tienda(self):
        # 'comparador' también matchea <slug:store>; el orden de URLs debe
        # ganarle y responder con la vista del comparador, no un 404 de tienda.
        response = self.client.get('/changomas/comparador/')
        self.assertEqual(response.status_code, 200)


class CartParseItemsTests(SimpleTestCase):
    """Saneado de la lista que manda el navegador: nada de lo que llega por
    POST se toca sin normalizar primero."""

    def test_descarta_lo_que_no_es_ean_gtin(self):
        items = parse_items([
            {'ean': '7790000000012', 'qty': 1},
            {'ean': '12345', 'qty': 1},          # largo inválido
            {'ean': 'vtex-991', 'qty': 1},       # código interno
            {'ean': '', 'qty': 1},
            'no soy un dict',
        ])
        self.assertEqual(items, [('7790000000012', 1)])

    def test_cantidad_se_acota_y_se_sanea(self):
        items = parse_items([
            {'ean': '7790000000012', 'qty': 0},
            {'ean': '7790000000029', 'qty': -5},
            {'ean': '7790000000036', 'qty': 999},
            {'ean': '7790000000043', 'qty': 'dos'},
            {'ean': '7790000000050'},
        ])
        self.assertEqual(items, [
            ('7790000000012', 1),
            ('7790000000029', 1),
            ('7790000000036', MAX_QUANTITY),
            # 'dos' no es un entero: la línea entera se descarta
            ('7790000000050', 1),
        ])

    def test_deduplica_y_corta_en_el_tope(self):
        repeated = parse_items([
            {'ean': '7790000000012', 'qty': 2},
            {'ean': '7790000000012', 'qty': 9},
        ])
        self.assertEqual(repeated, [('7790000000012', 2)])

        many = [{'ean': f'{7790000000000 + i}', 'qty': 1} for i in range(200)]
        self.assertEqual(len(parse_items(many)), MAX_CART_ITEMS)

    def test_payload_que_no_es_lista(self):
        self.assertEqual(parse_items({'ean': '7790000000012'}), [])
        self.assertEqual(parse_items(None), [])


class CartQuoteTests(TestCase):
    """El cálculo del carrito: total por cadena, compra óptima repartida
    y comparación honesta cuando a una tienda le faltan productos."""

    LECHE = '7790000000012'
    PAN = '7790000000029'
    YERBA = '7790000000036'

    def setUp(self):
        cache.clear()
        self.changomas = Supermarket.objects.get(slug='changomas')
        self.carrefour = Supermarket.objects.get(slug='carrefour')
        self.disco = Supermarket.objects.get(slug='disco')

    def _make(self, store, ean, name, price, promo_price=None, promo_text=''):
        product, _ = Product.objects.get_or_create(
            supermarket=store,
            reference_code=ean,
            defaults={
                'ean': ean,
                'vtex_product_id': f'{store.slug}-{ean}',
                'name': name,
                'is_comparable': bool(GTIN_RE.match(ean)),
            },
        )
        PriceRecord.objects.create(
            product=product,
            date=timezone.localdate(),
            price=Decimal(price),
            promo_price=Decimal(promo_price) if promo_price else None,
            promo_text=promo_text,
        )
        return product

    def _stores_by_slug(self, cart):
        return {row['supermarket'].slug: row for row in cart['stores']}

    def test_total_por_tienda_respeta_las_cantidades(self):
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        self._make(self.carrefour, self.LECHE, 'Leche', '1200')
        cart = quote([(self.LECHE, 3)])

        stores = self._stores_by_slug(cart)
        self.assertEqual(stores['changomas']['total'], Decimal('3000'))
        self.assertEqual(stores['carrefour']['total'], Decimal('3600'))
        self.assertEqual(cart['optimal']['total'], Decimal('3000'))
        self.assertEqual(cart['unit_count'], 3)
        self.assertEqual(cart['item_count'], 1)

    def test_optimo_reparte_y_calcula_el_ahorro(self):
        # La leche conviene en ChangoMás y el pan en Carrefour: comprar todo
        # en la mejor tienda única sale más caro que repartir.
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        self._make(self.carrefour, self.LECHE, 'Leche', '1200')
        self._make(self.changomas, self.PAN, 'Pan', '900')
        self._make(self.carrefour, self.PAN, 'Pan', '500')

        cart = quote([(self.LECHE, 1), (self.PAN, 1)])
        self.assertEqual(cart['optimal']['total'], Decimal('1500'))
        self.assertEqual(cart['optimal']['store_count'], 2)
        # Mejor tienda única: Carrefour (1700) contra ChangoMás (1900)
        self.assertEqual(cart['best_single']['supermarket'], self.carrefour)
        self.assertEqual(cart['best_single']['total'], Decimal('1700'))
        self.assertTrue(cart['best_single']['is_complete'])
        self.assertEqual(cart['savings'], Decimal('200'))

    def test_tienda_incompleta_suma_lo_que_tiene_y_declara_los_faltantes(self):
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        self._make(self.carrefour, self.LECHE, 'Leche', '800')
        self._make(self.changomas, self.PAN, 'Pan', '900')

        cart = quote([(self.LECHE, 1), (self.PAN, 1)])
        stores = self._stores_by_slug(cart)
        self.assertEqual(stores['carrefour']['total'], Decimal('800'))
        self.assertEqual(stores['carrefour']['covered_count'], 1)
        self.assertEqual(stores['carrefour']['missing_count'], 1)
        self.assertFalse(stores['carrefour']['is_complete'])
        self.assertTrue(stores['changomas']['is_complete'])

    def test_la_mejor_tienda_unica_prioriza_cobertura_sobre_precio(self):
        # Carrefour es más barato en lo único que tiene, pero le falta el pan:
        # rankearlo primero por total pelado sería mentir.
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        self._make(self.carrefour, self.LECHE, 'Leche', '800')
        self._make(self.changomas, self.PAN, 'Pan', '900')

        cart = quote([(self.LECHE, 1), (self.PAN, 1)])
        self.assertEqual(cart['best_single']['supermarket'], self.changomas)
        self.assertEqual(cart['best_single']['total'], Decimal('1900'))
        # El ahorro se mide sólo sobre lo que ChangoMás sí cubre (todo, acá):
        # la leche conviene en Carrefour a 800 -> 1900 - 1700
        self.assertEqual(cart['savings'], Decimal('200'))

    def test_ahorro_cero_cuando_una_sola_tienda_ya_es_lo_mejor(self):
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        self._make(self.changomas, self.PAN, 'Pan', '900')
        self._make(self.carrefour, self.LECHE, 'Leche', '1100')
        self._make(self.carrefour, self.PAN, 'Pan', '950')

        cart = quote([(self.LECHE, 1), (self.PAN, 1)])
        self.assertEqual(cart['savings'], Decimal('0'))
        self.assertEqual(cart['optimal']['store_count'], 1)
        self.assertEqual(cart['best_single']['supermarket'], self.changomas)

    def test_la_promo_define_donde_conviene(self):
        # Carrefour es más caro de lista pero su promo lo deja abajo.
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        self._make(self.carrefour, self.LECHE, 'Leche', '1100',
                   promo_price='750', promo_text='2da al 50%')

        cart = quote([(self.LECHE, 2)])
        self.assertEqual(cart['optimal']['total'], Decimal('1500'))
        self.assertEqual(cart['best_single']['supermarket'], self.carrefour)

    def test_producto_sin_precio_vigente_va_a_faltantes(self):
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        cart = quote([(self.LECHE, 1), (self.YERBA, 1)])
        self.assertEqual([item['ean'] for item in cart['missing']], [self.YERBA])
        self.assertEqual(cart['item_count'], 1)

    def test_los_faltantes_traen_su_nombre_cuando_lo_sabemos(self):
        """Se listan para que el usuario los saque; con el EAN pelado no
        podría reconocer qué está descartando."""
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        # Existe en la tabla pero su último precio quedó fuera de la ventana
        viejo = self._make(self.changomas, self.YERBA, 'Yerba Playadito', '5000')
        viejo.prices.all().delete()
        PriceRecord.objects.create(
            product=viejo,
            date=timezone.localdate() - timezone.timedelta(days=40),
            price=Decimal('5000'),
        )

        cart = quote([(self.LECHE, 1), (self.YERBA, 2)])
        self.assertEqual(cart['missing'], [
            {'ean': self.YERBA, 'name': 'Yerba Playadito'},
        ])

    def test_faltante_desconocido_queda_sin_nombre(self):
        """Un EAN que nunca vimos igual se lista: el usuario tiene que poder
        sacarlo aunque no sepamos cómo se llama."""
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        cart = quote([(self.LECHE, 1), (self.YERBA, 1)])
        self.assertEqual(cart['missing'], [{'ean': self.YERBA, 'name': ''}])

    def test_carrito_sin_nada_cotizable(self):
        cart = quote([(self.YERBA, 1)])
        self.assertEqual(cart['lines'], [])
        self.assertEqual(cart['stores'], [])
        self.assertIsNone(cart['optimal'])
        self.assertIsNone(cart['best_single'])
        # Mismas claves que una cotización con contenido: quien consuma el
        # dict no tiene que preguntarse si el carrito estaba vacío.
        self.assertIsNone(cart['savings'])

    def test_celdas_alineadas_con_las_columnas_de_tiendas(self):
        # La matriz de la UI se arma en Python: una celda por tienda, en el
        # mismo orden, con None donde la cadena no tiene el producto.
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        self._make(self.carrefour, self.LECHE, 'Leche', '800')
        self._make(self.changomas, self.PAN, 'Pan', '900')

        cart = quote([(self.LECHE, 2), (self.PAN, 1)])
        columns = [row['supermarket'].slug for row in cart['stores']]
        leche, pan = cart['lines']
        self.assertEqual(len(leche['cells']), len(columns))
        self.assertEqual(len(pan['cells']), len(columns))

        cells = dict(zip(columns, leche['cells']))
        self.assertEqual(cells['carrefour']['subtotal'], Decimal('1600'))
        self.assertTrue(cells['carrefour']['is_best'])
        self.assertFalse(cells['changomas']['is_best'])
        # Carrefour no tiene el pan: celda sin oferta, pero con su tienda
        # (la vista apilada de celular la usa como etiqueta del renglón).
        empty = dict(zip(columns, pan['cells']))['carrefour']
        self.assertIsNone(empty['offer'])
        self.assertIsNone(empty['subtotal'])
        self.assertFalse(empty['is_best'])
        self.assertEqual(empty['store'], self.carrefour)

    def test_empate_marca_las_dos_tiendas(self):
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        self._make(self.carrefour, self.LECHE, 'Leche', '1000')
        cart = quote([(self.LECHE, 1)])
        self.assertEqual([cell['is_best'] for cell in cart['lines'][0]['cells']],
                         [True, True])


class CartViewTests(TestCase):
    """Vistas del carrito: la página con el buscador y el endpoint que
    cotiza la lista guardada en el navegador."""

    LECHE = '7790000000012'
    PAN = '7790000000029'

    def setUp(self):
        cache.clear()
        self.changomas = Supermarket.objects.get(slug='changomas')
        self.carrefour = Supermarket.objects.get(slug='carrefour')

    def _make(self, store, ean, name, price):
        product, _ = Product.objects.get_or_create(
            supermarket=store, reference_code=ean,
            defaults={
                'ean': ean, 'vtex_product_id': f'{store.slug}-{ean}',
                'name': name, 'is_comparable': True,
            },
        )
        PriceRecord.objects.create(
            product=product, date=timezone.localdate(), price=Decimal(price))
        return product

    def _post(self, items):
        return self.client.post(
            reverse('changomas:cart_quote'),
            data=json.dumps({'items': items}),
            content_type='application/json',
        )

    def test_pagina_del_carrito_abre_vacia(self):
        response = self.client.get(reverse('changomas:cart'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Agregá productos')
        self.assertContains(response, reverse('changomas:cart_quote'))

    def test_la_ruta_carrito_no_la_captura_el_slug_de_tienda(self):
        response = self.client.get('/changomas/carrito/')
        self.assertEqual(response.status_code, 200)

    def test_buscador_ofrece_agregar_solo_comparables(self):
        self._make(self.changomas, self.LECHE, 'Leche Entera', '1000')
        Product.objects.create(
            supermarket=self.changomas, reference_code='vtex-77',
            ean='', vtex_product_id='77', name='Leche Suelta',
            is_comparable=False)

        response = self.client.get(reverse('changomas:cart'), {'q': 'leche'})
        self.assertContains(response, 'Leche Entera')
        self.assertNotContains(response, 'Leche Suelta')
        self.assertContains(response, f'data-ean="{self.LECHE}"')
        self.assertContains(response, 'data-cart-add')

    def test_cotizacion_devuelve_los_totales_renderizados(self):
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        self._make(self.carrefour, self.LECHE, 'Leche', '1200')
        self._make(self.changomas, self.PAN, 'Pan', '900')
        self._make(self.carrefour, self.PAN, 'Pan', '500')

        response = self._post([
            {'ean': self.LECHE, 'qty': 1},
            {'ean': self.PAN, 'qty': 2},
        ])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2.000,00')   # óptima: 1000 + 2x500
        self.assertContains(response, '2.200,00')   # Carrefour: 1200 + 1000
        self.assertContains(response, '2.800,00')   # ChangoMás: 1000 + 1800
        self.assertContains(response, 'Cómo se reparte')
        # Django sólo saca los {# #} que empiezan y terminan en la misma
        # línea: uno multilínea se imprime como texto en la página.
        self.assertNotContains(response, '{#')

    def test_cotizacion_de_un_carrito_vacio(self):
        response = self._post([])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'carrito está vacío')

    def test_cotizacion_ignora_eans_basura(self):
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        response = self._post([
            {'ean': self.LECHE, 'qty': 1},
            {'ean': "'; DROP TABLE", 'qty': 1},
            {'ean': '999', 'qty': 1},
        ])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1.000,00')

    def test_cotizacion_rechaza_get_y_json_invalido(self):
        self.assertEqual(
            self.client.get(reverse('changomas:cart_quote')).status_code, 405)
        response = self.client.post(
            reverse('changomas:cart_quote'),
            data='esto no es json', content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_cotizacion_rechaza_json_patologicamente_anidado(self):
        """Un JSON muy anidado hace que json.loads tire RecursionError, que
        NO es subclase de ValueError: si el except no lo incluye, un body de
        40 KB (muy por debajo del tope de 2,5 MB de Django) saca un 500."""
        payload = '[' * 5000 + ']' * 5000
        response = self.client.post(
            reverse('changomas:cart_quote'),
            data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_el_carrito_aparece_en_la_navegacion(self):
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        for url in (
            reverse('changomas:store_product_list', args=['changomas']),
            reverse('changomas:comparador_list'),
        ):
            self.assertContains(self.client.get(url), reverse('changomas:cart'))

    def test_carrito_es_slug_reservado(self):
        store = Supermarket(slug='carrito', name='X', base_url='https://x.com')
        with self.assertRaises(ValidationError):
            store.clean()


class CartRegressionTests(TestCase):
    """Regresiones de bugs que la suite no veía porque no rompían el cálculo:
    sólo se notaban mirando la página renderizada."""

    LECHE = '7790000000012'
    PAN = '7790000000029'

    def setUp(self):
        cache.clear()
        self.changomas = Supermarket.objects.get(slug='changomas')
        self.carrefour = Supermarket.objects.get(slug='carrefour')
        self.disco = Supermarket.objects.get(slug='disco')

    def _make(self, store, ean, name, price):
        product, _ = Product.objects.get_or_create(
            supermarket=store, reference_code=ean,
            defaults={
                'ean': ean, 'vtex_product_id': f'{store.slug}-{ean}',
                'name': name, 'is_comparable': True,
            },
        )
        # Idempotente a propósito: hay un precio por producto por día, así
        # que sembrar dos veces en el mismo test reventaría el UNIQUE.
        PriceRecord.objects.update_or_create(
            product=product, date=timezone.localdate(),
            defaults={'price': Decimal(price)},
        )
        return product

    def _quote_html(self):
        """La cotización con leche en las tres cadenas y pan sin Disco."""
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        self._make(self.carrefour, self.LECHE, 'Leche', '1200')
        self._make(self.disco, self.LECHE, 'Leche', '900')
        self._make(self.changomas, self.PAN, 'Pan', '800')
        self._make(self.carrefour, self.PAN, 'Pan', '700')
        return self.client.post(
            reverse('changomas:cart_quote'),
            data=json.dumps({'items': [
                {'ean': self.LECHE, 'qty': 1},
                {'ean': self.PAN, 'qty': 1},
            ]}),
            content_type='application/json',
        )

    def test_ninguna_pagina_imprime_comentarios_de_template(self):
        """Django sólo saca los ``{# #}`` que abren y cierran en la MISMA
        línea: uno multilínea se renderiza como texto visible. Pasó con el
        encabezado del parcial del carrito y con el script compartido, que
        va incluido en todas las páginas desde base.html."""
        quote = self._quote_html()  # además siembra el catálogo

        pages = [
            reverse('changomas:cart'),
            reverse('changomas:cart') + '?q=leche',
            reverse('changomas:comparador_list'),
            reverse('changomas:comparador_detail', args=[self.LECHE]),
            reverse('changomas:comparador_scan'),
            reverse('changomas:store_product_list', args=['changomas']),
            reverse('changomas:store_product_detail',
                    args=['changomas', self.LECHE]),
            reverse('changomas:store_scan', args=['changomas']),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), '{#')
        self.assertNotContains(quote, '{#')

    def test_cada_celda_de_precio_declara_su_cadena(self):
        """En pantallas angostas la tabla se apila y cada celda pasa a ser un
        renglón rotulado con ``data-store``; sin encabezado de columna que lo
        explique, una celda sin el atributo muestra un precio sin decir de
        qué cadena es. Las celdas vacías ('—') también lo necesitan."""
        response = self._quote_html()
        content = response.content.decode()

        # 2 productos + el renglón de totales = 3 celdas por cadena, incluso
        # para Disco, que no tiene el pan.
        for store in (self.changomas, self.carrefour, self.disco):
            with self.subTest(store=store.slug):
                self.assertEqual(
                    content.count(f'data-store="{store.name}"'), 3,
                    f'faltan celdas rotuladas para {store.name}')

        # La celda faltante de Disco existe y está marcada como vacía
        self.assertIn('is-empty', content)

    def test_la_explicacion_de_la_tabla_va_afuera_de_la_tabla(self):
        """Como <caption> formaba parte del ancho de la tabla, en el celular
        se cortaba con el scroll horizontal en lugar de partirse en varios
        renglones. Ahora es un <p> afuera, atado con aria-describedby."""
        response = self._quote_html()
        self.assertNotContains(response, '<caption>')
        self.assertContains(response, 'id="cart-table-help"')
        self.assertContains(response, 'aria-describedby="cart-table-help"')

    def _con_faltante(self, qty_faltante=2):
        """Carrito con un producto cotizable y otro cuyo precio quedó viejo."""
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        self._make(self.carrefour, self.LECHE, 'Leche', '1200')
        viejo = self._make(self.changomas, self.PAN, 'Pan Lactal', '800')
        viejo.prices.all().delete()
        PriceRecord.objects.create(
            product=viejo,
            date=timezone.localdate() - timezone.timedelta(days=40),
            price=Decimal('800'),
        )
        return self.client.post(
            reverse('changomas:cart_quote'),
            data=json.dumps({'items': [
                {'ean': self.LECHE, 'qty': 1},
                {'ean': self.PAN, 'qty': qty_faltante},
            ]}),
            content_type='application/json',
        )

    def test_los_faltantes_se_pueden_sacar_del_carrito(self):
        """Los ítems sin precio vigente siguen ocupando lugar en el carrito
        del navegador. Si el HTML no los nombra ni les da botón, inflan el
        contador para siempre sin aparecer en ninguna cuenta, y la única
        salida es 'Vaciar' (que borra todo)."""
        response = self._con_faltante()
        content = response.content.decode()

        self.assertContains(response, 'Pan Lactal')
        # El bloque de faltantes trae el EAN y su propio botón de borrado
        bloque = content.split('cart-gone', 1)[1].split('</div>', 1)[0]
        self.assertIn(f'data-ean="{self.PAN}"', bloque)
        self.assertIn('data-cart-remove', bloque)
        # ...y no se cuela como una línea cotizable de la tabla
        self.assertNotIn(f'<tr data-cart-control data-ean="{self.PAN}"', content)

    def test_carrito_solo_con_faltantes_no_publica_un_total(self):
        """Sin líneas cotizables no hay total que mostrar. Si el parcial no
        emite data-cart-total, la barra fija del celular se queda con el
        '$ 0,00' del placeholder al lado de un contador distinto de cero;
        el JS la esconde justamente porque el total no está."""
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        viejo = self._make(self.changomas, self.PAN, 'Pan Lactal', '800')
        viejo.prices.all().delete()
        PriceRecord.objects.create(
            product=viejo,
            date=timezone.localdate() - timezone.timedelta(days=40),
            price=Decimal('800'),
        )
        response = self.client.post(
            reverse('changomas:cart_quote'),
            data=json.dumps({'items': [{'ean': self.PAN, 'qty': 2}]}),
            content_type='application/json',
        )
        self.assertNotContains(response, 'data-cart-total')
        self.assertContains(response, 'data-cart-remove')   # igual se puede sacar
        self.assertContains(response, 'Pan Lactal')

    def test_la_barra_de_celular_se_apaga_sin_cotizacion(self):
        """La barra sólo se enciende si hay un total confirmado por el
        servidor; el contador crudo del navegador no alcanza."""
        response = self.client.get(reverse('changomas:cart'))
        self.assertContains(response, 'units > 0 && total !== null')

    def test_la_barra_cuenta_las_unidades_que_cubre_su_total(self):
        """El total sólo cubre lo cotizable. Si las unidades salieran del
        contador del navegador, con un producto sin precio en el carrito la
        barra anunciaría más unidades de las que paga ese total."""
        response = self._con_faltante(qty_faltante=4)
        # 1 unidad cotizable; las 4 del faltante no entran
        self.assertContains(response, '<span hidden data-cart-units>1</span>')

    def test_el_mas_llega_deshabilitado_del_servidor_en_el_tope(self):
        """En MAX_QUANTITY la cantidad ya no sube (Cart.set recorta en
        silencio), así que el '+' tiene que venir apagado en el HTML."""
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        response = self.client.post(
            reverse('changomas:cart_quote'),
            data=json.dumps({'items': [{'ean': self.LECHE, 'qty': MAX_QUANTITY}]}),
            content_type='application/json',
        )
        fila = response.content.decode().split('cartrow__qty', 1)[1][:400]
        self.assertIn('data-cart-inc', fila)
        self.assertIn('disabled', fila)

    def test_el_mas_sigue_activo_por_debajo_del_tope(self):
        self._make(self.changomas, self.LECHE, 'Leche', '1000')
        response = self.client.post(
            reverse('changomas:cart_quote'),
            data=json.dumps({'items': [{'ean': self.LECHE, 'qty': 3}]}),
            content_type='application/json',
        )
        fila = response.content.decode().split('cartrow__qty', 1)[1][:400]
        self.assertNotIn('disabled', fila)

    def test_la_cotizacion_inyectada_se_vuelve_a_pintar(self):
        """Inyectar la cotización reemplaza el DOM y se lleva puestos los
        estados que había puesto el cliente (el '+' apagado en el tope, por
        ejemplo). Hay que repintar después de cada inyección."""
        response = self.client.get(reverse('changomas:cart'))
        self.assertContains(response, 'ChangoCart.repaint()')
        # Repintar NO puede disparar 'changocart:change': encadenaría otra
        # cotización y no pararía más.
        script = response.content.decode().split('repaint: function', 1)[1][:200]
        self.assertNotIn('dispatchEvent', script)

    def test_la_barra_de_celular_reserva_su_espacio(self):
        """La barra fija está DESPUÉS de <main> en el DOM, así que ningún
        selector de hermanos puede reservarle lugar: ``.cartbar.is-on ~ main``
        no matcheaba nunca y la barra tapaba el final del contenido. El
        espacio lo reserva una clase que el JS pone en <body>."""
        response = self.client.get(reverse('changomas:cart'))
        self.assertNotContains(response, '~ main')
        self.assertContains(response, 'body.has-cartbar .wrap')
        self.assertContains(response, "classList.toggle('has-cartbar'")
