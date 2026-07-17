"""
Cliente compartido para los catálogos públicos VTEX de ChangoMás,
Carrefour y Disco, con parser de promociones por unidad.
"""
import logging
import re
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoreConfig:
    slug: str
    name: str
    base_url: str
    category_tree_depth: int = 3
    max_list_price_multiplier: Decimal | None = None

    @property
    def search_url(self):
        return self.base_url + '/api/catalog_system/pub/products/search'

    @property
    def tree_url(self):
        return self.base_url + f'/api/catalog_system/pub/category/tree/{self.category_tree_depth}'


STORE_CONFIGS = {
    config.slug: config
    for config in (
        StoreConfig('changomas', 'ChangoMás', 'https://www.masonline.com.ar'),
        StoreConfig('carrefour', 'Carrefour', 'https://www.carrefour.com.ar'),
        # Disco publica ListPrice desfasados de forma casi sistematica: para la
        # gran mayoria de los items ListPrice ~= 82x el Price real (dato basura,
        # no un precio de lista). El guard de 10x los descarta para no inventar
        # descuentos; en la practica Disco casi nunca deja un list_price usable.
        StoreConfig(
            'disco', 'Disco', 'https://www.disco.com.ar',
            max_list_price_multiplier=Decimal('10'),
        ),
    )
}

# Alias conservados para integraciones que importaban estas constantes.
BASE_URL = STORE_CONFIGS['changomas'].base_url
SEARCH_URL = STORE_CONFIGS['changomas'].search_url
TREE_URL = STORE_CONFIGS['changomas'].tree_url

PAGE_SIZE = 50
# La API de búsqueda de VTEX no permite paginar más allá del registro 2500.
VTEX_MAX_OFFSET = 2500

# Nodos del árbol de categorías que no son parte del catálogo navegable.
IGNORED_CATEGORY_NAMES = {'(old)', 'categoria mercadolibre'}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; PortfolioPriceTracker/1.0)',
    'Accept': 'application/json',
}


class ScrapeError(Exception):
    """La API no respondió tras los reintentos: la categoría quedó incompleta."""


class VtexClient:
    """Acceso HTTP a un catálogo VTEX, con reintentos y pausa entre requests."""

    def __init__(self, store='changomas', delay=0.3, timeout=30, max_retries=3):
        try:
            self.config = STORE_CONFIGS[store] if isinstance(store, str) else store
        except KeyError as exc:
            raise ValueError(f'Supermercado desconocido: {store}') from exc
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get_json(self, url, params=None):
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                # 200 y 206 (contenido parcial) son respuestas válidas de VTEX
                if response.status_code in (200, 206):
                    time.sleep(self.delay)
                    return response.json()
                if response.status_code == 429:
                    # Rate limit: esperamos bastante más antes de reintentar
                    time.sleep(10 * attempt)
                    continue
                last_error = f'HTTP {response.status_code}'
            except (requests.RequestException, ValueError) as exc:
                last_error = str(exc)
            time.sleep(2 * attempt)
        logger.warning('GET %s falló tras %s intentos: %s', url, self.max_retries, last_error)
        return None

    def get_leaf_categories(self):
        """
        Devuelve las categorías hoja como tuplas (ruta_de_ids, 'ruta / completa').
        La ruta de ids ('200051/300226') es la que exige el filtro fq=C:/.../
        de VTEX; los ids sueltos no devuelven resultados en esta tienda.
        Se recorren las hojas para no duplicar productos de nodos padre.
        """
        tree = self._get_json(self.config.tree_url)
        if not tree:
            return []
        leaves = []

        def walk(node, id_path, name_path):
            name = (node.get('name') or '').strip()
            if name.lower() in IGNORED_CATEGORY_NAMES:
                return
            current_ids = id_path + [str(node['id'])]
            current_names = name_path + [name]
            children = node.get('children') or []
            if children:
                for child in children:
                    walk(child, current_ids, current_names)
            else:
                leaves.append(('/'.join(current_ids), ' / '.join(current_names)))

        for root in tree:
            walk(root, [], [])
        return leaves

    def iter_category_products(self, category_id_path):
        """
        Pagina todos los productos crudos de una categoría (ruta de ids).
        Lanza ScrapeError si la API dejó de responder a mitad de la categoría,
        para que el llamador pueda distinguir 'categoría vacía' de 'falla'.
        """
        offset = 0
        while offset < VTEX_MAX_OFFSET:
            params = {
                'fq': f'C:/{category_id_path}/',
                '_from': offset,
                '_to': offset + PAGE_SIZE - 1,
            }
            page = self._get_json(self.config.search_url, params=params)
            if page is None:
                raise ScrapeError(f'La API no respondió paginando la categoría {category_id_path}')
            if not page:
                return
            yield from page
            if len(page) < PAGE_SIZE:
                return
            offset += PAGE_SIZE
        raise ScrapeError(
            f'La categoría {category_id_path} alcanzó el límite de '
            f'{VTEX_MAX_OFFSET} productos de VTEX y quedó truncada.'
        )


class MasOnlineClient(VtexClient):
    """Compatibilidad con el cliente original de ChangoMás."""

    def __init__(self, delay=0.3, timeout=30, max_retries=3):
        super().__init__(
            store='changomas',
            delay=delay,
            timeout=timeout,
            max_retries=max_retries,
        )


# ---------------------------------------------------------------------------
# Parseo de promociones
# ---------------------------------------------------------------------------

TWO_DECIMALS = Decimal('0.01')
FOUR_DECIMALS = Decimal('0.0001')

# "50% en la 2da unidad", "2da unidad al 50%", "2do al 70%", "Segunda unidad 50% off"
RE_SECOND_UNIT = re.compile(
    r'(?:(\d{1,2})\s*%.*?(?:2\s*(?:da|do|º|°)|segund[ao]))'
    r'|(?:(?:2\s*(?:da|do|º|°)|segund[ao]).*?(\d{1,2})\s*%)',
    re.IGNORECASE,
)
# "3x2", "2x1", "4 x 3"
RE_N_X_M = re.compile(r'\b(\d{1,2})\s*x\s*(\d{1,2})\b', re.IGNORECASE)
# "Pack 6x1" describe el empaque, no una promo "llevá 6 pagá 1"
RE_PACK = re.compile(r'\bpack\b', re.IGNORECASE)

# Descuento efectivo máximo creíble para una promo por cantidad (3x1 ≈ 67%).
# Por encima de esto casi seguro es un falso positivo del regex.
MAX_QUANTITY_DISCOUNT = Decimal('0.70')


def _to_decimal(value):
    return Decimal(str(value)).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)


def _to_unit_multiplier(value):
    try:
        return Decimal(str(value or 1)).quantize(FOUR_DECIMALS, rounding=ROUND_HALF_UP)
    except (ArithmeticError, ValueError):
        return Decimal('1.0000')


def _normalize_key(key):
    """VTEX legacy serializa claves como '<Name>k__BackingField' -> 'name'."""
    return key.strip('<>').replace('>k__BackingField', '').replace('k__BackingField', '').strip('<>').lower()


def _normalize(obj):
    if isinstance(obj, dict):
        return {_normalize_key(k): _normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    return obj


def _promo_from_text(text, price):
    """
    Interpreta el texto de una promo y devuelve (precio_efectivo, texto) o None.
    - '50% en la 2da unidad' => se pagan 1.5 unidades cada 2 => 25% real.
    - 'NxM' (3x2, 2x1) => se pagan M unidades cada N.
    """
    match = RE_N_X_M.search(text)
    if match and not RE_PACK.search(text):
        take, pay = int(match.group(1)), int(match.group(2))
        if take > pay > 0:
            discount = 1 - Decimal(pay) / Decimal(take)
            if discount <= MAX_QUANTITY_DISCOUNT:
                return _to_decimal(price * pay / take), text
            logger.info('Promo NxM descartada por descuento implausible (%s): %s', discount, text)

    match = RE_SECOND_UNIT.search(text)
    if match:
        percent = int(match.group(1) or match.group(2))
        if 0 < percent <= 100:
            effective = price * Decimal(2 * 100 - percent) / Decimal(200)
            return _to_decimal(effective), text
    return None


def _promo_from_structured(teaser, price):
    """
    Fallback genérico: si el teaser trae cantidad mínima N y un porcentaje X
    en sus efectos, asumimos X% de descuento sobre una de las N unidades.
    """
    try:
        conditions = teaser.get('conditions') or {}
        effects = teaser.get('effects') or {}
        minimum = int(conditions.get('minimumquantity') or 0)
        if minimum < 2:
            return None
        for param in effects.get('parameters') or []:
            # Solo parámetros cuyo nombre sugiere un porcentaje de descuento:
            # tomar el primer valor numérico a ciegas podría agarrar otra cosa
            # (ej. maxNumberOfItems) y persistir un precio promo incorrecto.
            param_name = str(param.get('name', '')).lower()
            if not any(hint in param_name for hint in ('discount', 'descuento', 'desconto', 'percent', 'porcent')):
                continue
            value = str(param.get('value', ''))
            if value.replace('.', '', 1).isdigit():
                percent = Decimal(value)
                if 0 < percent <= 100:
                    effective = price * (minimum - percent / 100) / minimum
                    name = teaser.get('name') or f'{percent}% llevando {minimum}'
                    return _to_decimal(effective), str(name)
    except (TypeError, ValueError, ArithmeticError):
        pass
    return None


def parse_promo(offer, price):
    """
    Busca promos por unidad en Teasers / PromotionTeasers / DiscountHighLight
    de un commertialOffer de VTEX. Devuelve (promo_price, promo_text):
    el precio efectivo por unidad y la descripción, o (None, '') si no hay.
    """
    price = Decimal(str(price))
    teasers = (offer.get('Teasers') or []) + (offer.get('PromotionTeasers') or [])
    highlights = offer.get('DiscountHighLight') or []

    candidates = []
    for raw in teasers:
        teaser = _normalize(raw)
        name = str(teaser.get('name') or '')
        result = _promo_from_text(name, price) if name else None
        if result is None:
            result = _promo_from_structured(teaser, price)
        if result:
            candidates.append(result)

    for raw in highlights:
        highlight = _normalize(raw) if isinstance(raw, dict) else {'name': raw}
        name = str(highlight.get('name') or '')
        if name:
            result = _promo_from_text(name, price)
            if result:
                candidates.append(result)

    if not candidates:
        return None, ''
    # Si hay varias promos nos quedamos con la de mejor precio efectivo
    best_price, best_text = min(candidates, key=lambda c: c[0])
    return best_price, best_text[:200]


# ---------------------------------------------------------------------------
# Parseo de productos
# ---------------------------------------------------------------------------

def _safe_url(value):
    """Solo aceptamos URLs http/https: los datos vienen de una API de terceros
    y no queremos persistir esquemas como javascript: (bulk_create no valida
    los URLField del modelo)."""
    url = (value or '').strip()
    if url and urlparse(url).scheme in ('http', 'https'):
        return url
    return ''


def _parse_item(raw, item, category_path, config):
    offer = None
    for seller in item.get('sellers') or []:
        candidate = seller.get('commertialOffer') or {}
        if candidate.get('Price'):
            if seller.get('sellerDefault') or offer is None:
                offer = candidate
            if seller.get('sellerDefault'):
                break
    if not offer or not offer.get('Price'):
        return None

    price = _to_decimal(offer['Price'])
    list_price = _to_decimal(offer['ListPrice']) if offer.get('ListPrice') else None
    if (
        list_price is not None
        and config.max_list_price_multiplier is not None
        and list_price > price * config.max_list_price_multiplier
    ):
        logger.warning(
            '%s: ListPrice implausible descartado para productId=%s (%s vs %s)',
            config.name, raw.get('productId'), list_price, price,
        )
        list_price = None
    promo_price, promo_text = parse_promo(offer, price)

    ean = (item.get('ean') or '').strip()[:32]
    vtex_id = str(raw.get('productId') or '')
    sku_id = str(item.get('itemId') or vtex_id)
    if not vtex_id or not sku_id or len(vtex_id) > 32 or len(sku_id) > 32:
        logger.warning('Producto VTEX descartado por identificador inválido: %r/%r', vtex_id, sku_id)
        return None
    reference_code = ean if ean else f'vtex-{sku_id}'

    images = item.get('images') or []
    image_url = _safe_url(images[0].get('imageUrl', '')) if images else ''

    # 'categories' viene con la ruta más específica primero: "/Almacén/Harinas/..."
    categories = raw.get('categories') or []
    category = category_path or (categories[0].strip('/').replace('/', ' / ') if categories else '')

    return {
        'vtex_product_id': vtex_id,
        'vtex_sku_id': sku_id,
        'reference_code': reference_code,
        'ean': ean,
        'product_reference': str(raw.get('productReference') or '')[:64],
        'measurement_unit': str(item.get('measurementUnit') or '')[:16],
        'unit_multiplier': _to_unit_multiplier(item.get('unitMultiplier')),
        'name': (
            item.get('nameComplete') or raw.get('productName') or ''
        ).strip()[:300],
        'brand': (raw.get('brand') or '').strip()[:150],
        'category': category[:300],
        'image_url': image_url[:500],
        'link': _safe_url(raw.get('link'))[:500],
        'is_available': bool(offer.get('IsAvailable', True)),
        'price': price,
        'list_price': list_price,
        'promo_price': promo_price,
        'promo_text': promo_text,
    }


def parse_products(raw, category_path='', store='changomas'):
    """Convierte cada SKU con oferta de un producto VTEX en una publicacion."""
    config = STORE_CONFIGS[store] if isinstance(store, str) else store
    parsed = []
    for item in raw.get('items') or []:
        product = _parse_item(raw, item, category_path, config)
        if product is not None:
            parsed.append(product)
    return parsed


def parse_product(raw, category_path='', store='changomas'):
    """Compatibilidad: devuelve el primer SKU vendible o ``None``."""
    products = parse_products(raw, category_path=category_path, store=store)
    return products[0] if products else None
