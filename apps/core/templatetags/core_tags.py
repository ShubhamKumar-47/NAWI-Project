"""
apps/core/templatetags/core_tags.py
Core template filters and tags for NAWI-TRMS.
"""
import json
from django import template

register = template.Library()


@register.filter(name="from_json")
def from_json(value):
    """
    Safely parse a JSON string into a Python data structure.
    If already a list, tuple, or dict, returns it directly.
    Returns an empty list on failure or None.
    """
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        value_str = value.strip()
        if not value_str:
            return []
        try:
            parsed = json.loads(value_str)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
            return []
        except Exception:
            return []
    return []


@register.filter(name="parse_breadcrumbs")
def parse_breadcrumbs(value):
    """
    Parse breadcrumb input into a sanitized list of dicts.
    Filters out any items lacking a valid non-empty 'label'
    to prevent empty <li> breadcrumb items and extraneous separators.
    """
    items = from_json(value)
    clean_items = []
    for it in items:
        if isinstance(it, dict) and it.get("label"):
            clean_items.append({
                "label": str(it.get("label", "")).strip(),
                "url": str(it.get("url", "")).strip() if it.get("url") else None,
            })
    return clean_items

