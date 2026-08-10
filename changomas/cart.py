"""
Carrito: una lista de compra que se cotiza entera en cada cadena y contra la
compra óptima repartida entre todas.

Decisiones que vienen del resto de la app:

- El carrito vive en el localStorage del navegador. La app no tiene cuentas
  y todas las demás vistas son cacheables; el servidor no guarda nada, sólo
  recibe la lista y devuelve la cotización armada. Así el cálculo (que es lo
  que se puede equivocar) queda en Python y testeado, y no duplicado en JS.
- Sólo entran identidades comparables (EAN de largo GTIN válido): son las
  únicas que se pueden precificar en las tres cadenas. Es el mismo conjunto
  que muestra el comparador.
- Una tienda que no tiene todos los ítems igual cotiza: suma lo que sí tiene
  y declara cuántos le faltan. Con catálogos parciales, exigir cobertura
  total dejaría casi todos los carritos sin ninguna tienda que mostrar.
- El precio unitario es el efectivo (promo si existe), igual que en el
  comparador. Ojo: ``promo_price`` ya viene con el descuento prorrateado de
  promos por cantidad ("2da al 50%" -> 25% real), así que una línea con
  cantidad 1 se cotiza un poco por debajo de lo que se pagaría en la caja.
  Es la misma convención que usa el resto de la app; la UI lo aclara.
"""
import json

from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .comparador import (
    _build_group,
    _comparable_products,
    _with_history,
    search_groups,
)
from .models import GTIN_RE, Product, Supermarket
from .views import MAX_QUERY_LENGTH

# Techos del carrito. No son preferencias de UI: acotan el trabajo que un
# POST anónimo puede pedirle a la base (la app corre en una Raspberry).
MAX_CART_ITEMS = 60
MAX_QUANTITY = 99


def parse_items(payload):
    """Normaliza lo que manda el cliente a ``[(ean, qty)]``.

    Todo lo que no sea un EAN de largo GTIN válido se descarta acá: son los
    únicos que pueden estar en el carrito, así que un código raro no llega
    nunca a la query.
    """
    if not isinstance(payload, list):
        return []
    items, seen = [], set()
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        ean = str(entry.get('ean', ''))[:32].strip()
        if not GTIN_RE.match(ean) or ean in seen:
            continue
        try:
            quantity = int(entry.get('qty', 1))
        except (TypeError, ValueError):
            continue
        seen.add(ean)
        items.append((ean, max(1, min(quantity, MAX_QUANTITY))))
        if len(items) >= MAX_CART_ITEMS:
            break
    return items


def _missing_details(eans):
    """Los faltantes con su nombre, cuando lo sabemos.

    El producto puede seguir existiendo en la tabla aunque ninguna cadena
    tenga precio suyo dentro de la ventana de 30 días. Mostrar el nombre (y
    no un EAN pelado) es lo que le permite al usuario reconocer qué le
    estamos dejando afuera de la cuenta y decidir si lo saca.
    """
    names = dict(
        Product.objects.filter(ean__in=eans)
        .exclude(name='')
        .values_list('ean', 'name')
    )
    return [{'ean': ean, 'name': names.get(ean, '')} for ean in eans]


def _build_lines(items):
    """Una línea por ítem del carrito, con la oferta de cada tienda.

    Devuelve ``(lines, missing)``; en ``missing`` van los ítems que ya no
    tienen precio vigente (producto discontinuado o sin stock en ninguna
    cadena). Van con nombre porque la UI los lista uno por uno con un botón
    para sacarlos: si no, quedan pesando en el contador del carrito sin
    aparecer en ninguna cuenta y sin forma de eliminarlos salvo vaciar todo.
    """
    eans = [ean for ean, _ in items]
    members_by_ean = {}
    for member in _with_history(_comparable_products().filter(ean__in=eans)):
        members_by_ean.setdefault(member.ean, []).append(member)

    lines, missing = [], []
    for ean, quantity in items:
        group = _build_group(members_by_ean.get(ean, []))
        if group is None:
            missing.append(ean)
            continue
        lines.append({
            'ean': ean,
            'quantity': quantity,
            'product': group['product'],
            'best': group['best'],
            'best_subtotal': group['best']['effective'] * quantity,
            'offers': group['offers'],
            'offer_by_store': {
                offer['product'].supermarket_id: offer
                for offer in group['offers']
            },
            'store_count': group['store_count'],
        })
    # La query de nombres sólo se paga cuando efectivamente falta algo.
    return lines, _missing_details(missing) if missing else []


def _store_totals(lines):
    """Qué sale el carrito en cada cadena, comprando todo en esa sola.

    Ordenadas por cobertura y después por total: un supermercado que tiene
    dos de los diez ítems siempre va a "salir más barato" que uno completo,
    así que el total pelado no alcanza para rankear.
    """
    totals = []
    for supermarket in Supermarket.objects.filter(is_active=True):
        covered = [
            line for line in lines
            if supermarket.pk in line['offer_by_store']
        ]
        if not covered:
            continue
        total = sum(
            line['offer_by_store'][supermarket.pk]['effective'] * line['quantity']
            for line in covered
        )
        # Lo mismo que cubre esta tienda, pero comprando cada ítem donde
        # esté más barato: la diferencia es lo que se paga de más por
        # hacer todo en un solo lugar, y es comparable manzana con manzana.
        optimal_on_covered = sum(line['best_subtotal'] for line in covered)
        totals.append({
            'supermarket': supermarket,
            'total': total,
            'covered_count': len(covered),
            'missing_count': len(lines) - len(covered),
            'is_complete': len(covered) == len(lines),
            'extra': total - optimal_on_covered,
        })
    totals.sort(key=lambda row: (-row['covered_count'], row['total']))
    return totals


def _attach_cells(lines, stores):
    """Alinea cada línea con las columnas de tiendas.

    La UI muestra el carrito como una matriz (una fila por ítem, una columna
    por cadena) y las plantillas de Django no pueden indexar un dict por una
    clave variable, así que la grilla se arma acá: ``line['cells']`` queda en
    el mismo orden que ``stores``.

    Toda celda lleva su ``store``, incluso las vacías: en pantallas angostas
    la tabla se apila y cada celda pasa a ser un renglón que necesita decir
    de qué cadena habla, sin encabezado de columna que la explique.
    """
    for line in lines:
        cells = []
        for row in stores:
            offer = line['offer_by_store'].get(row['supermarket'].pk)
            cells.append({
                'store': row['supermarket'],
                'offer': offer,
                'subtotal': offer['effective'] * line['quantity'] if offer else None,
                # Empate entre cadenas: se marcan las dos. Elegir una sola
                # por el orden del ranking sería arbitrario y confuso.
                'is_best': bool(offer) and offer['effective'] == line['best']['effective'],
            })
        line['cells'] = cells


def _optimal_split(lines):
    """La compra óptima: cada ítem donde está más barato, agrupado por tienda."""
    by_store = {}
    for line in lines:
        supermarket = line['best']['product'].supermarket
        bucket = by_store.setdefault(supermarket.pk, {
            'supermarket': supermarket,
            'lines': [],
            'subtotal': 0,
        })
        bucket['lines'].append(line)
        bucket['subtotal'] += line['best_subtotal']
    stops = sorted(by_store.values(), key=lambda stop: -stop['subtotal'])
    return {
        'total': sum(line['best_subtotal'] for line in lines),
        'stops': stops,
        'store_count': len(stops),
    }


def quote(items):
    """Cotiza el carrito completo. ``items`` viene de :func:`parse_items`."""
    lines, missing = _build_lines(items)
    if not lines:
        return {
            'lines': [],
            'missing': missing,
            'stores': [],
            'optimal': None,
            'best_single': None,
            'savings': None,
            'item_count': 0,
            'unit_count': 0,
        }

    stores = _store_totals(lines)
    _attach_cells(lines, stores)
    optimal = _optimal_split(lines)
    # El "mejor precio en una sola tienda" es la primera de la lista: la de
    # mayor cobertura y, entre esas, la más barata.
    best_single = stores[0] if stores else None
    return {
        'lines': lines,
        'missing': missing,
        'stores': stores,
        'optimal': optimal,
        'best_single': best_single,
        # Ahorro de repartir la compra contra hacerla toda en la mejor
        # tienda, medido sólo sobre los ítems que esa tienda efectivamente
        # tiene (si le faltan, la UI lo aclara).
        'savings': best_single['extra'] if best_single else None,
        'item_count': len(lines),
        'unit_count': sum(line['quantity'] for line in lines),
    }


def cart_page(request):
    """Armado del carrito: buscador de productos arriba y la cotización
    abajo. La cotización la pide el navegador con el contenido guardado en
    localStorage, así que esta vista no se cachea ni conoce carritos."""
    query = request.GET.get('q', '').strip()[:MAX_QUERY_LENGTH]
    page, groups = (None, [])
    if query:
        page, groups = search_groups(query, request.GET.get('page'))

    return render(request, 'changomas/carrito.html', {
        'is_cart': True,
        'query': query,
        'page': page,
        'groups': groups,
        'results_total': page.paginator.count if page else 0,
        'max_items': MAX_CART_ITEMS,
        'supermarkets': Supermarket.objects.filter(is_active=True),
    })


@require_POST
def cart_quote(request):
    """Cotiza la lista que manda el navegador y devuelve el HTML del carrito.

    Responde HTML y no JSON a propósito: el cálculo y su presentación
    (precios formateados, plurales, traducciones) ya viven en Django, y así
    el JS del cliente se limita a guardar la lista e inyectar la respuesta.
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, ValueError, RecursionError):
        # RecursionError no es un ValueError: un JSON muy anidado
        # ('[[[[...]]]]' entra de sobra en el límite de body de Django)
        # revienta el parser, y sin atraparlo el endpoint contesta 500.
        return HttpResponseBadRequest('invalid payload')

    items = parse_items(payload.get('items') if isinstance(payload, dict) else payload)
    return render(request, 'changomas/carrito_quote.html', {
        'cart': quote(items) if items else None,
        'max_items': MAX_CART_ITEMS,
        'max_quantity': MAX_QUANTITY,
    })
