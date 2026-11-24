from decimal import Decimal

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from ..flags import flag_label as _flag_label

register = template.Library()


@register.filter
def hrs(value):
    """Format hours with two decimals, e.g. 1.5 -> '1.50'."""
    if value in (None, ""):
        return "0.00"
    return f"{Decimal(value):,.2f}"


@register.filter
def flag_label(code):
    return _flag_label(code)


@register.simple_tag(takes_context=True)
def page_url(context, page_number):
    query = context.get("querystring", "")
    return f"?{query}&page={page_number}" if query else f"?page={page_number}"


@register.simple_tag(takes_context=True)
def sort_th(context, key, label, numeric=False):
    """Header cell that links to the server-side sort for `key` (see views.SORTS)."""
    current = context.get("sort", "")
    if current == key:
        target, state = f"-{key}", "ascending"
    elif current == f"-{key}":
        target, state = key, "descending"
    else:
        target, state = (f"-{key}" if numeric or key == "date" else key), ""
    base = context.get("sort_query", "")
    href = f"?{base}&sort={target}" if base else f"?sort={target}"
    return format_html(
        '<th scope="col"{}{}><a class="sort" href="{}">{}</a></th>',
        mark_safe(' class="num"') if numeric else "",
        format_html(' aria-sort="{}"', state) if state else "",
        href,
        label,
    )
