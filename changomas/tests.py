from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from .models import PriceRecord, Product, Supermarket
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
        self.assertContains(response, 'Run <code>python manage.py scrape_supermarkets</code>')


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
