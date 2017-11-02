from django import template
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def svg_icon(icon_id, **kwargs):
    """
    Add an SVG icon to the HTML. The <svg> tag has per default at least
    class="icon". Additional classes can be added using kwargs.
    :param icon_id: The ID of the icon (as in <symbol id="">)
    :param kwargs: Optional arguments:
        - inline (bool): Add "is-inline" to the CSS classes. Default: True
        - classes (str). Additional CSS classes to be added.
        - rotate (bool): If true, icon is rotated (works best with class
            "is-inline".
    :return:
    """
    css_class_list = ['icon']
    if kwargs.get('inline') is not False:
        css_class_list.append('is-inline')
    if kwargs.get('classes'):
        css_class_list.append(kwargs.get('classes'))
    css_classes = ' '.join(css_class_list)
    svg_sprite = static('svg/icons.svg')
    rotate_string = ''
    if kwargs.get('rotate') is True:
        rotate_string = '<animateTransform attributeType="xml" ' \
                        'attributeName="transform" type="rotate" ' \
                        'from="0 7 7" to="360 7 7" dur="1s" ' \
                        'repeatCount="indefinite"/>'
    return mark_safe(
        f'<svg class="{css_classes}"><use xlink:href="{svg_sprite}#{icon_id}">{rotate_string}</use></svg>')
