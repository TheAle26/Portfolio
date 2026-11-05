"""Global shopping experience and the versioned comparison API."""
from urllib.parse import urlencode

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Case, CharField, F, Max, Min, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Cast, Concat
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import cart, comparador
from .models import PriceRecord, Product, Supermarket
from .pricing import is_fresh, line_total, promotion_details, normalize_gtin, legacy_cutoff_date
from .search import normalize, search_products


def legacy_redirect(request, suffix=''):
    if suffix.startswith('producto/') or suffix == 'escanear/':
        suffix = 'changomas/' + suffix
    destination = '/supermarket-tracker/' + suffix
    if request.META.get('QUERY_STRING'):
        destination += '?' + request.META['QUERY_STRING']
    response = HttpResponse(status=301 if request.method in ('GET', 'HEAD') else 307)
    response['Location'] = destination
    return response


def _groups(request):
    filters = {key: request.GET.get(key, '').strip()[:100] for key in ('store', 'category', 'brand', 'sort', 'offers')}
    query = request.GET.get('q', '').strip()[:100]
    base = Product.objects.filter(supermarket__is_active=True, is_available=True)
    store = filters['store']
    if store:
        base = base.filter(supermarket_id=store)
    categories = {}
    for path in base.exclude(category='').order_by().values_list('category', flat=True).distinct():
        category = path.split(' / ')[0]
        categories.setdefault(normalize(category), category.capitalize())
    if filters['category']:
        paths = [p for p in base.order_by().values_list('category', flat=True).distinct()
                 if normalize(p.split(' / ')[0]) == normalize(filters['category'])]
        base = base.filter(category__in=paths)
    brands = list(base.exclude(brand='').order_by('brand').values_list('brand', flat=True).distinct())
    if filters['brand']:
        base = base.filter(brand__iexact=filters['brand'])
    latest = PriceRecord.objects.filter(product_id=OuterRef('pk')).order_by('-date')
    base = base.annotate(current_price=Subquery(latest.values('price')[:1]),
                         current_date=Subquery(latest.values('date')[:1]),
                         current_list=Subquery(latest.values('list_price')[:1]),
                         current_rule=Subquery(latest.values('promotion')[:1]))
    cutoff = timezone.now() - timezone.timedelta(hours=36)
    base = base.filter(Q(last_price_checked_at__gte=cutoff) | Q(
        last_price_checked_at__isnull=True, current_date__gte=legacy_cutoff_date()))
    if filters['offers']:
        base = base.filter(Q(current_list__gt=F('current_price')) | (
            Q(current_rule__kind__in=['nxm', 'second_unit']) & Q(current_rule__restricted=False)))
    matches = search_products(base, query).annotate(identity=Case(
        When(catalog_item_id__isnull=False, then=Concat(Value('canonical:'), Cast('catalog_item_id', CharField()))),
        default=Concat(Value('listing:'), Cast('pk', CharField())), output_field=CharField()))
    identities = matches.values('identity').annotate(
        first_pk=Min('pk'), display=Min('name'), relevance=Max('search_rank'), price=Min('current_price'))
    order = {'price': ('price', 'display', 'identity'), 'name': ('display', 'identity')}.get(
        filters['sort'], ('-relevance', 'display', 'identity'))
    paginator = Paginator(identities.order_by(*order), 24)
    page = paginator.get_page(request.GET.get('page'))
    keys = []
    for row in page:
        kind, value = row['identity'].split(':', 1)
        keys.append(((kind, int(value) if kind != 'ean' else value), row['first_pk']))
    groups = _load_groups(keys)
    return {'page': page, 'groups': groups, 'query': query, 'filters': filters,
            'total': paginator.count, 'categories': sorted(categories.values()), 'brands': brands,
            'stores': Supermarket.objects.filter(is_active=True),
            'supermarkets': Supermarket.objects.filter(is_active=True), 'suggestions': [],
            'querystring': urlencode({**filters, 'q': query})}


def _load_groups(keys):
    if not keys:
        return []
    canonical_ids = [key[1] for key, _ in keys if key[0] == 'canonical']
    eans = [key[1] for key, _ in keys if key[0] == 'ean']
    ids = [key[1] for key, _ in keys if key[0] == 'listing']
    members = comparador._with_history(Product.objects.filter(
        Q(catalog_item_id__in=canonical_ids) | Q(ean__in=eans) | Q(pk__in=ids),
        supermarket__is_active=True, is_available=True))
    indexed = {}
    for member in members:
        for key in [('canonical', member.catalog_item_id), ('ean', member.ean), ('listing', member.pk)]:
            indexed.setdefault(key, []).append(member)
    groups = []
    for key, _ in keys:
        group = comparador._build_group(indexed.get(key, []))
        if group:
            group['ean'] = group['product'].ean if normalize_gtin(group['product'].ean) else 'listing-' + str(group['product'].pk)
            groups.append(group)
    return groups


@require_GET
def catalog(request):
    context = _groups(request)
    return render(request, 'changomas/tracker_catalog.html', context)


@require_GET
def offers(request):
    request.GET = request.GET.copy()
    request.GET['offers'] = '1'
    context = _groups(request)
    context['is_offers'] = True
    return render(request, 'changomas/tracker_catalog.html', context)


@require_GET
def detail(request, code):
    if code.startswith('listing-') and code[8:].isascii() and code[8:].isdigit() and 1 <= len(code[8:]) <= 18:
        product = get_object_or_404(Product.objects.select_related('supermarket'), pk=int(code[8:]), supermarket__is_active=True)
    else:
        from .views import VALID_CODE_RE
        if not VALID_CODE_RE.fullmatch(code):
            raise Http404
        identity = Q(ean=code)
        gtin = normalize_gtin(code)
        if gtin:
            identity |= Q(catalog_item__gtin=gtin)
        listings = Product.objects.filter(supermarket__is_active=True).select_related('supermarket').order_by('-is_available', 'pk')
        product = listings.filter(identity).first()
        if product is None:
            product = listings.filter(reference_code=code).first()
        if product is None:
            raise Http404
    if product.catalog_item_id:
        base = Product.objects.filter(catalog_item_id=product.catalog_item_id)
    elif product.ean:
        base = Product.objects.filter(ean=product.ean)
    else:
        base = Product.objects.filter(pk=product.pk)
    members = list(comparador._with_history(base.filter(supermarket__is_active=True, is_available=True)))
    group = comparador._build_group(members)
    if group:
        group['ean'] = product.ean if normalize_gtin(product.ean) else 'listing-' + str(product.pk)
    records = list(product.prices.order_by('-date')[:30])
    stats = {'min': min(r.price for r in records), 'max': max(r.price for r in records), 'days': len(records)} if records else {}
    # Historical-only products remain followable; never label their price current.
    return render(request, 'changomas/tracker_detail.html', {
        'product': product, 'group': group, 'best': group['best'] if group else None,
        'offers': group['offers'] if group else [], 'price_records': records,
        'chart': comparador._build_multi_chart(group['offers']) if group else None,
        'code': code, 'freshness': bool(group), 'stats': stats,
        'stores': Supermarket.objects.filter(is_active=True),
    })


@require_GET
def cart_page(request):
    context = {'is_cart': True, 'max_items': cart.MAX_CART_ITEMS}
    if request.GET.get('q'):
        context.update(_groups(request))
        context['results_total'] = context['total']
    response = render(request, 'changomas/tracker_cart.html', context)
    response['Cache-Control'] = 'private, no-store'
    return response


@require_POST
def cart_quote(request):
    import json
    try:
        payload = json.loads(request.body)
        items = cart.parse_items(payload.get('items', []) if isinstance(payload, dict) else payload)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return JsonResponse({'error': 'Datos de carrito inválidos.'}, status=400)
    response = render(request, 'changomas/_tracker_quote.html', {
        'cart': cart.quote(items) if items else None, 'max_items': 60, 'max_quantity': 99})
    response['Cache-Control'] = 'private, no-store'
    return response


@require_GET
def catalog_api(request):
    context = _groups(request)
    results = []
    for group in context['groups']:
        results.append({'code': group['ean'], 'id': group['product'].pk,
                        'name': group['product'].name, 'brand': group['product'].brand,
                        'offers': [{'store': offer['product'].supermarket_id,
                                    'price': str(offer['effective']), 'quantity': 1,
                                    'promotion': promotion_details(offer['record']),
                                    'checked_at': offer['product'].last_price_checked_at,
                                    'date': offer['record'].date} for offer in group['offers']]})
    return JsonResponse({'count': context['total'], 'page': context['page'].number, 'results': results})


@require_POST
def quote_api(request):
    import json
    try:
        payload = json.loads(request.body)
        items = cart.parse_items(payload.get('items', []) if isinstance(payload, dict) else payload)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return JsonResponse({'error': 'Invalid cart'}, status=400)
    result = cart.quote(items)
    return JsonResponse({'quantity_aware': True, 'shipping_included': False,
                         'missing': result['missing'], 'stores': [
        {'store': row['supermarket'].pk, 'total': str(row['total']),
         'complete': row['is_complete'] and not result['missing'], 'missing_count': row['missing_count'] + len(result['missing'])}
        for row in result['stores']],
        'optimal_total': str(result['optimal']['total']) if result['optimal'] else None})
