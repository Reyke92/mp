from __future__ import annotations

from django import template

register = template.Library()

@register.filter(name="dict_get")
def dict_get(value, key):
    if not isinstance(value, dict):
        return None
    return value.get(key)