from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.simple_tag
def cart_limits():
    """Topes del carrito, para que el JS del navegador use los mismos que el
    servidor. El script vive en base.html (está en todas las páginas) y no
    tiene una vista propia que se los pase por contexto."""
    from ..cart import MAX_CART_ITEMS, MAX_QUANTITY
    return {'items': MAX_CART_ITEMS, 'quantity': MAX_QUANTITY}


@register.filter
def precio(value):
    """Formatea un precio al estilo argentino: 18999.5 -> '18.999,50'."""
    if value is None:
        return ''
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value
    formatted = f'{number:,.2f}'  # '18,999.50'
    return formatted.replace(',', '\x00').replace('.', ',').replace('\x00', '.')
