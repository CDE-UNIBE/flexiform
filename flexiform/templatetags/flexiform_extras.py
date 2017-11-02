from django import template

register = template.Library()


@register.filter
def keyvalue(dict, key):
    """
    Return the value of a key from a dictionary.
    """
    return dict[key]


@register.filter
def index(items, i):
    """
    Return a list item at a given index.
    """
    return items[int(i)]
