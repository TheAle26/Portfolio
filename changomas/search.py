"""Shared catalog search; PostgreSQL indexes accelerate production queries."""
import re
import unicodedata

from django.db import connection
from django.db.models import Case, FloatField, Q, Value, When


def normalize(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', str(value).lower())
                           if not unicodedata.combining(c)).split())


def build_search_filter(query, fields=('name', 'brand')):
    from .views import _accent_insensitive_pattern
    combined = Q()
    for token in query.split()[:6]:
        token_q = Q()
        for field in fields:
            token_q |= Q(**{f'{field}__iregex': _accent_insensitive_pattern(token)})
        combined &= token_q
    return combined


def search_products(queryset, query):
    query = str(query or '').strip()[:100]
    if not query:
        return queryset.annotate(search_rank=Value(0.0, output_field=FloatField()))
    exact = Q(ean=query) | Q(reference_code=query) | Q(vtex_product_id=query)
    if query.isdigit():
        exact |= Q(catalog_item__gtin=query.zfill(14))
    if connection.vendor == 'postgresql':
        from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramWordSimilarity
        vector = SearchVector('search_text', config='simple')
        words = SearchQuery(normalize(query), config='simple')
        queryset = queryset.annotate(document=vector, similarity=TrigramWordSimilarity(normalize(query), 'search_text'))
        matches = Q(document=words) | exact
        if len(query) >= 3:
            matches |= Q(search_text__trigram_word_similar=normalize(query))
        return queryset.filter(matches).annotate(search_rank=Case(
            When(exact, then=Value(100.0)),
            default=SearchRank(vector, words) + TrigramWordSimilarity(normalize(query), 'search_text') + Case(When(search_text__startswith=normalize(query.split()[0]), then=Value(5.0)), default=Value(0.0), output_field=FloatField()),
            output_field=FloatField(),
        ))
    return queryset.filter(exact | build_search_filter(query)).annotate(search_rank=Case(
        When(exact, then=Value(100.0)),
        When(name__istartswith=query.split()[0], then=Value(10.0)),
        default=Value(1.0), output_field=FloatField(),
    ))
