import re

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import cache_page

from .models import PriceRecord, Product, Supermarket

PRODUCTS_PER_PAGE = 48
MAX_QUERY_LENGTH = 100
MAX_SEARCH_TOKENS = 6

# Clases de caracteres para búsqueda insensible a acentos: "pure" matchea
# "Puré" y viceversa. Funciona igual en SQLite (re de Python) y Postgres (~*).
_ACCENT_CLASSES = {
    'a': '[aá]', 'á': '[aá]',
    'e': '[eé]', 'é': '[eé]',
    'i': '[ií]', 'í': '[ií]',
    'o': '[oó]', 'ó': '[oó]',
    'u': '[uúü]', 'ú': '[uúü]', 'ü': '[uúü]',
    'n': '[nñ]', 'ñ': '[nñ]',
}


def _accent_insensitive_pattern(token):
    """Regex literal (sin cuantificadores: inmune a ReDoS) que matchea el
    token ignorando acentos. Los metacaracteres del usuario se escapan."""
    return ''.join(
        _ACCENT_CLASSES.get(char, re.escape(char))
        for char in token.lower()
    )


def build_search_filter(query, fields=('name', 'brand')):
    """
    Filtro de búsqueda flexible: cada palabra del query debe aparecer en
    alguno de los campos (nombre o marca), en cualquier orden y sin
    importar acentos. 'pure tomate arcor' encuentra 'Puré De Tomate' de
    marca Arcor aunque icontains literal no lo haría.
    """
    combined = Q()
    for token in query.split()[:MAX_SEARCH_TOKENS]:
        pattern = _accent_insensitive_pattern(token)
        token_q = Q()
        for field in fields:
            token_q |= Q(**{f'{field}__iregex': pattern})
        combined &= token_q
    return combined
CATEGORIES_CACHE_KEY = 'changomas:top_categories'
CATEGORIES_CACHE_TTL = 60 * 60 * 6  # el dato cambia una vez por día


def categories_cache_key(store_slug):
    return f'{CATEGORIES_CACHE_KEY}:{store_slug}'


def _get_supermarket(store_slug):
    return get_object_or_404(Supermarket, slug=store_slug, is_active=True)


def _get_top_categories(supermarket):
    """Primer nivel de categorías, cacheado: la query DISTINCT sobre toda la
    tabla es cara para correrla en cada request en la Raspberry."""
    cache_key = categories_cache_key(supermarket.slug)
    top_level = cache.get(cache_key)
    if top_level is None:
        paths = (
            Product.objects.filter(supermarket=supermarket, is_available=True)
            .exclude(category='')
            .values_list('category', flat=True)
            .distinct()
        )
        # Solo el primer nivel de la ruta ("Almacén / Harinas" -> "Almacén")
        top_level = sorted({c.split(' / ')[0] for c in paths})
        cache.set(cache_key, top_level, CATEGORIES_CACHE_TTL)
    return top_level


@cache_page(60 * 15)
def product_list(request, store='changomas'):
    """Góndola: todos los productos trackeados con su último precio."""
    supermarket = _get_supermarket(store)
    products = (
        Product.objects
        .filter(supermarket=supermarket, is_available=True)
        .select_related('supermarket')
        .prefetch_related(
            Prefetch('prices', queryset=PriceRecord.objects.order_by('-date'), to_attr='price_history')
        )
    )

    query = request.GET.get('q', '').strip()[:MAX_QUERY_LENGTH]
    if query:
        products = products.filter(build_search_filter(query))

    category = request.GET.get('cat', '').strip()[:MAX_QUERY_LENGTH]
    if category:
        # Ancla en el separador para que "Bebidas" no matchee "BebidasX"
        products = products.filter(
            Q(category=category) | Q(category__startswith=category + ' / ')
        )

    paginator = Paginator(products, PRODUCTS_PER_PAGE)
    page = paginator.get_page(request.GET.get('page'))

    for product in page:
        history = getattr(product, 'price_history', [])
        product.today = history[0] if history else None

    context = {
        'page': page,
        'query': query,
        'category': category,
        'categories': _get_top_categories(supermarket),
        'total': paginator.count,
        'supermarket': supermarket,
        'supermarkets': Supermarket.objects.filter(is_active=True),
    }
    return render(request, 'changomas/product_list.html', context)


def scan_page(request, store='changomas'):
    """Escáner de códigos de barras con la cámara del celular. Sin estado:
    todo corre en el navegador y soporta usuarios simultáneos sin cuenta."""
    supermarket = _get_supermarket(store)
    return render(request, 'changomas/scan.html', {
        'supermarket': supermarket,
        'supermarkets': Supermarket.objects.filter(is_active=True),
    })


MAX_CODE_LENGTH = 64
# EANs son numéricos; los códigos internos ('vtex-123', '0274011000000')
# son alfanuméricos con guiones. Cualquier otra cosa no puede existir en la
# DB, así que la descartamos sin consultar (barato ante requests basura).
VALID_CODE_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
NOT_FOUND_CACHE_TTL = 60 * 5


def _find_product(supermarket, code):
    """
    Busca por cualquiera de los identificadores, en orden de prioridad:
    primero los únicos (reference_code, vtex_product_id) y después los que
    pueden repetirse (ean, product_reference). El orden importa: dos productos
    pueden compartir EAN, y el "dueño" del código es el que lo tiene como
    reference_code — un OR sin prioridad podía devolver el equivocado.
    """
    if not VALID_CODE_RE.match(code):
        return None
    for lookup in ('reference_code', 'vtex_product_id'):
        product = Product.objects.filter(
            supermarket=supermarket,
            **{lookup: code},
        ).first()
        if product:
            return product
    # ean / product_reference admiten duplicados: criterio determinístico,
    # preferimos el disponible visto más recientemente.
    return (
        Product.objects
        .filter(supermarket=supermarket)
        .filter(Q(ean=code) | Q(product_reference=code))
        .order_by('-is_available', '-last_seen')
        .first()
    )


def _build_chart(records):
    """Puntos para el gráfico SVG del histórico (viewBox 600x180)."""
    if len(records) < 2:
        return None
    prices = [float(r.effective_price) for r in records]
    low, high = min(prices), max(prices)
    span = (high - low) or 1.0
    width, height, pad = 600.0, 180.0, 12.0
    step = (width - 2 * pad) / (len(prices) - 1)
    points = []
    last_x = last_y = 0.0
    for i, value in enumerate(prices):
        last_x = pad + i * step
        last_y = pad + (height - 2 * pad) * (1 - (value - low) / span)
        points.append(f'{last_x:.1f},{last_y:.1f}')
    return {'points': ' '.join(points), 'last_x': f'{last_x:.1f}', 'last_y': f'{last_y:.1f}'}


@cache_page(60 * 15)
def product_detail(request, code, store='changomas'):
    """Ficha del producto escaneado: precio actual, histórico de 30 días
    y máximo/mínimo del período."""
    code = code.strip()[:MAX_CODE_LENGTH]
    supermarket = _get_supermarket(store)
    # cache_page solo cachea respuestas 200: cacheamos a mano los códigos
    # inexistentes para que un loop de códigos random no golpee la DB.
    not_found_key = f'changomas:notfound:{supermarket.slug}:{code}'
    if cache.get(not_found_key):
        return render(request, 'changomas/product_not_found.html', {
            'code': code,
            'supermarket': supermarket,
        }, status=404)

    product = _find_product(supermarket, code) if code else None
    if product is None:
        cache.set(not_found_key, True, NOT_FOUND_CACHE_TTL)
        return render(request, 'changomas/product_not_found.html', {
            'code': code,
            'supermarket': supermarket,
        }, status=404)

    # Filtro explícito de 30 días: si el job de purga se atrasa unos días,
    # el "últimos 30 días" de la UI sigue siendo cierto.
    cutoff = timezone.localdate() - timezone.timedelta(days=29)
    records = list(product.prices.filter(date__gte=cutoff).order_by('date'))
    stats = None
    if records:
        effective = [r.effective_price for r in records]
        stats = {
            'current': records[-1],
            'min': min(effective),
            'max': max(effective),
            'days': len(records),
        }

    context = {
        'product': product,
        'records': list(reversed(records)),  # tabla: más reciente primero
        'stats': stats,
        'chart': _build_chart(records),
        'supermarket': supermarket,
        'supermarkets': Supermarket.objects.filter(is_active=True),
    }
    return render(request, 'changomas/product_detail.html', context)
