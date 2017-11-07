# from django.contrib.gis.forms import OSMWidget
from django.forms import widgets

from .conf import settings


class RepeatingSelectMultipleWidget(widgets.SelectMultiple):
    """
    Use this widget if you have a SelectMultiple in a repeating row.
    """

    def value_from_datadict(self, data, files, name):
        """
        Do not return an empty list if no value was selected, this causes the
        validation to crash. Instead return an empty string.
        """
        try:
            getter = data.getlist
        except AttributeError:
            getter = data.get
        value = getter(name)
        if value == ['']:
            return ''
        return value


class RepeatingWidget(widgets.MultiWidget):
    """
    Widget displaying repeating fields. The logic to split columns per row
    is in the template, so no logic for subwidgets must be re-implemented.
    """
    template_name = 'flexiform/widgets/columns.html'

    def decompress(self, value):
        # 'Opposite' of compress on field. Prepare data from db to use in the
        # form.
        if value:
            return list(value)
        return []

    def value_from_datadict(self, data, files, name):
        """
        Overwriting the default method under the assumption that data keys are
        of format name_<int>. Usually integers are starting from 1 and counting
        up. However, if a row is deleted in the form, the ints of the submitted
        data are not in sequence anymore, the original implementation of this
        method therefore not working anymore. Attempt to handle this here
        instead of updating field values in template after removing a row.
        """
        valid_keys = []
        for key in data.keys():
            try:
                int(key.replace(name + '_', ''))
            except ValueError:
                continue
            valid_keys.append(key)

        if len(valid_keys) != len(self.widgets):
            raise Exception('Submitted data and widgets do not match')

        return [self.widgets[i].value_from_datadict(data, files, key) for
                i, key in enumerate(valid_keys)]

    def get_context(self, name, value, attrs):
        """
        Add attributes for JS and markup.
        """
        context = super().get_context(name, value, attrs)
        disabled = bool(
            attrs.get('disabled') or
            self.attrs['field_options'].get('disabled'))

        len_subwidgets = len(context.get('widget', {}).get(
            'subwidgets', []))
        rows_shown = len_subwidgets / self.attrs['columns_per_row']
        show_delete_buttons = rows_shown > 1 and \
            disabled is not True and \
            rows_shown > self.attrs['field_options'].get('min_rows', 1)
        if self.attrs.get('show_add_button') is False:
            show_add_button = False
        else:
            show_add_button = disabled is not True and \
                rows_shown < self.attrs['field_options'].get('max_rows', 10000)

        custom_columns = self.attrs.get('field_options', {}).get('columns', [])
        if custom_columns:
            columns = custom_columns * int(rows_shown)
        else:
            columns = [int(12 / self.attrs['columns_per_row'])] * len_subwidgets

        context.update({
            'columns': columns,
            'columns_per_row': self.attrs['columns_per_row'],
            'rows_shown': rows_shown,
            'labels': self.attrs['labels'],
            'field_options': self.attrs['field_options'],
            'show_delete_buttons': show_delete_buttons,
            'show_add_button': show_add_button,
            'disabled': disabled,
        })
        return context


class ThroughWidget(RepeatingWidget):
    class Media:
        css = {
            'all': ('css/jquery-ui.css', ),
        }
        js = ('js/jquery-ui-min.js', )

    template_name = 'flexiform/widgets/through.html'


class LinkWidget(ThroughWidget):

    template_name = 'flexiform/widgets/link.html'


class DatepickerWidget(widgets.DateInput):
    """
    Widget to render a Datepicker (from jQuery UI) for a date field.
    """
    class Media:
        css = {
            'all': ('css/jquery-ui.css', ),
        }
        js = ('js/jquery-ui-min.js', )

    def __init__(self, attrs=None, format=None):
        if attrs is None:
            attrs = {}
        attrs.update({
            'class': 'js-datepicker',
            'placeholder': settings.CORE_PLACEHOLDER_DATE
        })
        super(DatepickerWidget, self).__init__(attrs, format)


# class MapWidget(OSMWidget):

#     class Media:
#         extend = False
#         css = {
#             'all': (
#                 'css/ol.css',
#                 'gis/css/ol3.css',
#             )
#         }
#         js = (
#             'js/ol-min.js',
#             'gis/js/OLMapWidget.js',
#             'js/map_forms-min.js',
#         )

#     template_name = 'flexiform/widgets/map.html'


class ResizableMultiSelectWidget(widgets.SelectMultiple):

    class Media:
        css = {
            'all': ('css/jquery-ui.css',),
        }
        js = ('js/jquery-ui-min.js',)

    def get_context(self, name, value, attrs):
        context = super(ResizableMultiSelectWidget, self).get_context(name, value, attrs)
        context['widget']['attrs']['class'] = 'js-resizable multi-select-resizable'
        return context
