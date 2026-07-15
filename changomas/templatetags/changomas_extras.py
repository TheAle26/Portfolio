from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


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
