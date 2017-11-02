import collections

from django.forms import fields

from .widgets import (DatepickerWidget, LinkWidget, RepeatingWidget,
                      ThroughWidget)

JsonStruct = collections.namedtuple('ToJsonStruct', ['path', 'value'])


class JsonMixin:
    topics = []

    def from_json(self, data: dict, name: str) -> str:
        return data.get(name)

    def to_json(self, keyword: str, key: str, value: str) -> JsonStruct:
        return JsonStruct(path=[keyword, key], value=value)


class JsonCharField(JsonMixin, fields.CharField):
    """
    Create fields for various access types.
    """
    pass


class JsonIntegerField(JsonMixin, fields.IntegerField):
    pass


class JsonEmailField(JsonMixin, fields.EmailField):
    pass


class JsonNullBooleanField(JsonMixin, fields.NullBooleanField):
    pass


class JsonChoiceField(JsonMixin, fields.ChoiceField):
    pass


class JsonMultipleChoiceField(JsonMixin, fields.MultipleChoiceField):

    def prepare_value(self, value):
        """
        Problem: Report builder cannot handle list data, needs string. Field in
        form cannot handle string, needs list.
        Solution: Instead of splitting values in from_json method (works in form
        but causes report builder to crash), values are split only for the form.
        """
        if isinstance(value, str):
            return value.split(',')
        return value

    def to_json(self, keyword: str, key: str, value: str) -> JsonStruct:
        return JsonStruct(path=[keyword, key], value=','.join(value))


class JsonDateField(JsonMixin, fields.DateField):
    widget = DatepickerWidget

    def to_json(self, keyword: str, key: str, value: str) -> JsonStruct:
        if value:
            value = str(value)
        return super().to_json(keyword, key, value)


class JsonMultiRowField(JsonMixin, fields.MultiValueField):

    widget = RepeatingWidget

    def __init__(self, row: dict, nb_rows: int, options: dict, *args, **kwargs):
        self.row = row
        self.nb_rows = nb_rows
        self.options = options
        if options.get('label') is not None:
            kwargs.update({'label': options.get('label')})
        super().__init__(
            fields=self.get_fields(),
            widget=self.get_widget(),
            *args, **kwargs
        )

    def to_json(self, keyword: str, key: str, data_list: list) -> JsonStruct:
        data = list(self.compress(data_list=data_list))
        return JsonStruct(path=[keyword, key], value=data)

    def get_fields(self):
        return tuple(field[0] for field in list(self.row.values())) * self.nb_rows

    def get_widget(self):
        return self.widget(
            widgets=(field[1] for field in list(self.row.values()) * self.nb_rows)
        )

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget=widget)
        attrs.update({
            'columns_per_row': len(self.row),
            'labels': self.get_labels(),
            'field_options': self.options,
        })
        return attrs

    def get_labels(self):
        """
        Return all labels of the row.
        :return: list. A list of labels.
        """
        for field, widget in self.row.values():
            if widget.is_hidden is False:
                yield field.label

    def compress(self, data_list: list) -> list:
        """
        Return a data_list (a flat list of values - all rows concatenated) into
        a list of dictionaries, each one representing one row. Thus turning the
        submitted values into the format in which it is stored in the database.
        Rows which contain only empty fields are not returned.

        :param data_list: list. A flat list of values - the values of all rows
            concatenated
        :return: A list of dictionaries, each one representing one row.
        """
        fields_per_row = len(self.row)
        for i in range(0, len(data_list), fields_per_row):
            chunk = data_list[i:i + fields_per_row]
            # Return only rows which are not empty
            if any(c not in ['', None] for c in chunk):
                yield collections.OrderedDict(zip(self.row.keys(), chunk))

    def clean(self, value):
        """
        Don't raise a validationerror for empty fields. Also do not actually
        "clean" anything, removing empty rows is handled by `compress`.
        """
        return value


class ThroughRowField(JsonMultiRowField):
    """A through relation to another model."""

    widget = ThroughWidget

    def to_model(self, data_list):
        """
        Separate the required fields to_id and through_id from the remaining
        data attributes.
        """
        for row in self.compress(data_list=data_list):
            yield (row.pop('to_id'), row.pop('through_id'), row)


class LinkRowField(JsonMultiRowField):
    """A foreign key relation to/from another model."""

    widget = LinkWidget

    def __init__(self, row: dict, nb_rows: int, options: dict, *args, **kwargs):
        self.is_foreign_key = kwargs.pop('is_foreign_key', False)
        super().__init__(row, nb_rows, options, *args, **kwargs)

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget=widget)
        attrs['show_add_button'] = self.is_foreign_key is False
        return attrs
