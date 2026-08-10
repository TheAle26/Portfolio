"""
Vistas del Comparador: agrupa los productos de las tres cadenas por EAN
y muestra el mejor precio vigente, el histórico combinado y un gráfico
con una línea por tienda.

Reglas que salieron de la validación en vivo de los scrapers:
- El matching entre tiendas usa solo EANs con largo GTIN válido
  (8, 12, 13 o 14 dígitos); el resto no es comparable.
- Solo participan productos disponibles: los precios basura de Disco
  (stale/congelados) viven únicamente en SKUs sin stock.
- No todas las tiendas exponen promos ni list_price (Disco no):
  el comparador no asume que esos campos existan.
"""
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Min, Prefetch
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import cache_page

from .models import PriceRecord, Product, Supermarket
from .views import (
    MAX_CODE_LENGTH,
    MAX_QUERY_LENGTH,
    NOT_FOUND_CACHE_TTL,
    PRODUCTS_PER_PAGE,
    VALID_CODE_RE,
    build_search_filter,
)

# Colores de línea del gráfico por tienda. No usamos primary_color directo
# porque ChangoMás (#0071ce) y Carrefour (#005baa) son azules casi iguales
# y las líneas serían indistinguibles.
CHART_COLORS = {
    'changomas': '#0071ce',
    'carrefour': '#16a34a',
    'disco': '#ed1c24',
}
DEFAULT_CHART_COLOR = '#64748b'

HISTORY_DAYS = 30


def _comparable_products():
    """Productos que participan del comparador: disponibles, de tiendas
    activas y con EAN de largo GTIN válido (flag precalculado al scrapear
    para no evaluar un regex sobre toda la tabla en cada request)."""
    return Product.objects.filter(
        is_available=True,
        supermarket__is_active=True,
        is_comparable=True,
    )


def _history_cutoff():
    return timezone.localdate() - timezone.timedelta(days=HISTORY_DAYS - 1)


def _with_history(queryset):
    cutoff = _history_cutoff()
    return queryset.select_related('supermarket').prefetch_related(
        Prefetch(
            'prices',
            queryset=PriceRecord.objects.filter(date__gte=cutoff).order_by('-date'),
            to_attr='price_history',
        )
    )


def _latest_record(product):
    history = getattr(product, 'price_history', None)
    if history is None:
        cutoff = _history_cutoff()
        history = list(product.prices.filter(date__gte=cutoff).order_by('-date'))
        product.price_history = history
    return history[0] if history else None


def _build_group(members):
    """Arma el dict de un grupo de productos (misma identidad) para la UI.
    Devuelve None si ningún miembro tiene precio vigente.

    Una misma cadena puede tener DOS publicaciones con el mismo EAN
    (SKUs/variantes duplicadas del catálogo VTEX): se deduplica por tienda
    quedándose con la más barata, así el comparador compara cadenas y no
    publicaciones internas de una misma cadena."""
    best_by_store = {}
    for member in members:
        latest = _latest_record(member)
        if latest is None:
            continue
        offer = {
            'product': member,
            'record': latest,
            'effective': latest.effective_price,
        }
        current = best_by_store.get(member.supermarket_id)
        if current is None or offer['effective'] < current['effective']:
            best_by_store[member.supermarket_id] = offer
    if not best_by_store:
        return None
    offers = sorted(best_by_store.values(), key=lambda offer: offer['effective'])
    best = offers[0]
    return {
        'best': best,
        'offers': offers,
        'product': best['product'],   # nombre/imagen del que conviene comprar
        'store_count': len(offers),
    }


def search_groups(query, page_number, per_page=PRODUCTS_PER_PAGE):
    """Búsqueda paginada sobre las identidades comparables.

    Devuelve ``(page, groups)``: el objeto de paginación (para el contador y
    los links) y los grupos ya armados de la página pedida. Lo usan tanto el
    listado del comparador como el buscador del carrito, que necesitan
    exactamente el mismo conjunto de productos.
    """
    base = _comparable_products()
    if query:
        base = base.filter(build_search_filter(query))

    # Solo identidades con al menos un precio dentro de la ventana de 30
    # días: si no, el total/paginación contaría grupos que _build_group
    # descartaría después (páginas vacías, contador inconsistente).
    identities = (
        base.filter(prices__date__gte=_history_cutoff())
        .values('ean')
        .annotate(display_name=Min('name'))
        .order_by('display_name')
    )

    paginator = Paginator(identities, per_page)
    page = paginator.get_page(page_number)

    page_eans = [row['ean'] for row in page]
    members_by_ean = {}
    members = _with_history(_comparable_products().filter(ean__in=page_eans))
    for member in members:
        members_by_ean.setdefault(member.ean, []).append(member)

    groups = []
    for row in page:
        group = _build_group(members_by_ean.get(row['ean'], []))
        if group is not None:
            group['ean'] = row['ean']
            groups.append(group)
    return page, groups


@cache_page(60 * 15)
def product_list(request):
    """Listado del comparador: un card por identidad de producto (EAN),
    mostrando el precio más bajo entre las tiendas."""
    query = request.GET.get('q', '').strip()[:MAX_QUERY_LENGTH]
    page, groups = search_groups(query, request.GET.get('page'))

    context = {
        'page': page,
        'groups': groups,
        'query': query,
        'total': page.paginator.count,
        'supermarkets': Supermarket.objects.filter(is_active=True),
    }
    return render(request, 'changomas/comparador_list.html', context)


def scan_page(request):
    """Escáner del comparador: mismo template que el de tienda, pero el
    código escaneado se busca en las tres cadenas a la vez."""
    return render(request, 'changomas/scan.html', {
        'supermarket': None,
        'comparador': True,
        'supermarkets': Supermarket.objects.filter(is_active=True),
    })


def _resolve_group_members(code):
    """
    Resuelve un código a los miembros de su identidad de producto.
    Primero como EAN compartido; si no, como código propio de alguna tienda
    (reference_code / vtex id / referencia interna) y de ahí a su EAN.
    """
    members = list(_with_history(_comparable_products().filter(ean=code)))
    if members:
        return members

    # Por etapas y en orden de prioridad: el mismo código puede existir en
    # DOS tiendas identificando productos distintos (los ids de VTEX solo
    # son únicos por tienda) — un OR plano elegiría uno arbitrario.
    owner = None
    for lookup in ('reference_code', 'vtex_product_id', 'product_reference'):
        owner = (
            Product.objects.filter(supermarket__is_active=True, **{lookup: code})
            .order_by('-is_available', '-last_seen')
            .first()
        )
        if owner is not None:
            break
    if owner is None:
        return []
    if owner.ean:
        members = list(_with_history(
            _comparable_products().filter(ean=owner.ean)
        ))
        if members:
            return members
    # Producto sin EAN comparable: el grupo es él solo (si está disponible).
    if owner.is_available:
        return list(_with_history(
            Product.objects.filter(pk=owner.pk)
        ))
    return []


def _build_multi_chart(offers):
    """
    Gráfico SVG multi-serie (viewBox 600x200): una línea por tienda,
    eje X alineado por fecha para que las líneas sean comparables.
    """
    series_data = []
    for offer in offers:
        records = sorted(
            getattr(offer['product'], 'price_history', []),
            key=lambda r: r.date,
        )
        if records:
            series_data.append((offer['product'], records))
    all_points = [
        (record.date, float(record.effective_price))
        for _, records in series_data
        for record in records
    ]
    if len(all_points) < 2:
        return None

    dates = [point[0] for point in all_points]
    prices = [point[1] for point in all_points]
    start, end = min(dates), max(dates)
    low, high = min(prices), max(prices)
    date_span = (end - start).days or 1
    price_span = (high - low) or 1.0
    width, height, pad = 600.0, 200.0, 14.0

    def coords(record):
        x = pad + (width - 2 * pad) * (record.date - start).days / date_span
        y = pad + (height - 2 * pad) * (1 - (float(record.effective_price) - low) / price_span)
        return f'{x:.1f}', f'{y:.1f}'

    series = []
    for product, records in series_data:
        points = [coords(record) for record in records]
        last_x, last_y = points[-1]
        series.append({
            'name': product.supermarket.name,
            'color': CHART_COLORS.get(product.supermarket.slug, DEFAULT_CHART_COLOR),
            'points': ' '.join(f'{x},{y}' for x, y in points),
            'single': len(points) == 1,
            'last_x': last_x,
            'last_y': last_y,
        })
    return {'series': series}


@cache_page(60 * 15)
def product_detail(request, code):
    """Ficha del comparador: mejor precio vigente y en qué tienda,
    mínimo/actual/máximo combinado de 30 días y gráfico por tienda."""
    code = code.strip()[:MAX_CODE_LENGTH]

    not_found_key = f'changomas:notfound:comparador:{code}'
    if cache.get(not_found_key):
        return render(request, 'changomas/product_not_found.html', {
            'code': code,
            'supermarket': None,
            'comparador': True,
        }, status=404)

    members = []
    if code and VALID_CODE_RE.match(code):
        members = _resolve_group_members(code)
    group = _build_group(members) if members else None
    if group is None:
        cache.set(not_found_key, True, NOT_FOUND_CACHE_TTL)
        return render(request, 'changomas/product_not_found.html', {
            'code': code,
            'supermarket': None,
            'comparador': True,
        }, status=404)

    # Stats combinadas: min/max sobre el precio efectivo de TODOS los
    # registros de 30 días de las tiendas participantes.
    all_records = [
        record
        for offer in group['offers']
        for record in getattr(offer['product'], 'price_history', [])
    ]
    effective_prices = [record.effective_price for record in all_records]
    stats = {
        'current': group['best']['effective'],
        'current_store': group['best']['product'].supermarket,
        'min': min(effective_prices),
        'max': max(effective_prices),
        'days': len({record.date for record in all_records}),
    }

    context = {
        'group': group,
        'stats': stats,
        'chart': _build_multi_chart(group['offers']),
        'code': code,
    }
    return render(request, 'changomas/comparador_detail.html', context)
