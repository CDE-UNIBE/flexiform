import collections

from django import forms
from django.forms import BaseFormSet
from django.template.loader import render_to_string
from django.utils.module_loading import import_string

from .fields import (JsonMixin, JsonMultiRowField, JsonStruct, LinkRowField,
                     ThroughRowField)
from .validators import validate_no_underscore

RepeatingRowField = collections.namedtuple(
    'RepeatingRowField', ['name', 'row', 'options']
)

ThroughRelation = collections.namedtuple(
    'ThroughRelation', [
        'from_field', 'to_id_field', 'through_manager', 'through_query']
)


class ThroughModelField:
    def __init__(self, name, through, to, row, options):
        self.name = name
        self.through_model = import_string(through)
        self.to_model = import_string(to)
        self.row = row
        self.options = options


class LinkModelField:
    def __init__(
            self, name: str, to: str, is_foreign_key: bool, row: dict,
            options: dict):
        self.name = name
        self.to_model = import_string(to)
        self.is_foreign_key = is_foreign_key
        self.row = row
        self.options = options


class ChainDict(dict):
    """
    Helper to access dynamic key paths
    """
    def set_key_chain(self, keys: str, value: str) -> None:
        current = self
        for key in keys[:-1]:
            current = current.setdefault(key, {})
        current[keys[-1]] = value


class NetworkFormMixin:
    template_name = 'flexiform/form/network.html'

    def get_context(self) -> dict:
        context = super().get_context()
        context.update({
            'graph_url': self.initial.get('graph_url'),
        })
        return context


class ReadOnlyMixin:

    def __init__(self, *args, **kwargs):
        self.readonly = kwargs.pop('readonly', False)
        super().__init__(*args, **kwargs)

        # None of the fields are required.
        for field in self.fields.values():
            field.disabled = self.readonly
            field.required = False


class BaseForm(ReadOnlyMixin, forms.ModelForm):
    template_name = 'flexiform/form/default.html'

    def __init__(self, *args, **kwargs) -> None:
        """
        Check for valid fieldnames (no characters used to access the json values
        as model properties) and create the required number of repeating fields.
        """
        self._validate_fieldnames()
        super().__init__(*args, **kwargs)
        if self.has_repeating_fields:
            self._setup_repeating_fields()
        if self.has_through_fields:
            self._setup_through_fields()
        if self.has_link_fields:
            self._setup_link_fields()

    def _validate_fieldnames(self):
        for name, _, is_json_field in self.model_fields():
            if is_json_field:
                validate_no_underscore(name)

    @property
    def keyword(self):
        return self.Meta.keyword

    @property
    def label(self):
        if hasattr(self.Meta, 'label'):
            return self.Meta.label
        return self.keyword

    @property
    def has_repeating_fields(self):
        return hasattr(self.Meta, 'repeating_fields')

    @property
    def has_through_fields(self):
        return hasattr(self.Meta, 'through_fields')

    @property
    def has_link_fields(self):
        return hasattr(self.Meta, 'link_fields')

    def _setup_repeating_fields(self):
        for field in self.Meta.repeating_fields:
            self.fields[field.name] = JsonMultiRowField(
                row=field.row, nb_rows=self.get_nb_repeating_rows(field),
                options=field.options)

        # Reorder fields according to defined fields order.
        if hasattr(self.Meta, 'fields_order'):
            index_map = {v: i for i, v in enumerate(self.Meta.fields_order)}
            try:
                self.fields = collections.OrderedDict(sorted(
                    self.fields.items(), key=lambda pair: index_map[pair[0]]))
            except KeyError:
                pass

    def _setup_through_fields(self):
        for field in self.Meta.through_fields:
            self.fields[field.name] = ThroughRowField(
                row=field.row, nb_rows=self.get_nb_repeating_rows(field),
                options=field.options)

    def _setup_link_fields(self):
        for field in self.Meta.link_fields:
            if field.is_foreign_key is True:
                nb_rows = 1
            else:
                nb_rows = self.get_nb_repeating_rows(field)
            self.fields[field.name] = LinkRowField(
                row=field.row, nb_rows=nb_rows, options=field.options,
                is_foreign_key=field.is_foreign_key)

    def get_nb_repeating_rows(self, field) -> int:
        """
        Calculate the number of rows to show. The field values of all rows are
        in a flat list, so divide it by number of fields per row to get the row
        count.

        For readonly forms, always show at least one row. In the edit form,
        always add an additional row.

        self.data (POST request) takes precedence over self.initial (GET
        request).
        """
        rows_shown = 0
        readonly = bool(self.readonly or field.options.get('disabled'))

        # Always show at least 1 row for readonly forms
        if readonly:
            rows_shown = 1

        min_rows = field.options.get('min_rows', 1)
        max_rows = field.options.get('max_rows', 10000)

        fields_per_row = len(field.row)
        if self.data:
            prefixed_name = f'{self.prefix}-{field.name}'
            submitted_fields = [k for k in self.data.keys() if k.startswith(prefixed_name)]
            submitted_rows = int(len(submitted_fields) / fields_per_row)
            rows_shown = max(rows_shown, submitted_rows)
        elif self.initial:
            initial_fields = self.initial.get(field.name, [])

            initial_rows = int(len(initial_fields) / fields_per_row)
            rows_shown = max(rows_shown, initial_rows)

            # In the edit form, always show an additional row unless the limit
            # is reached
            if not readonly and rows_shown < max_rows:
                rows_shown += 1

        rows_shown = max(rows_shown, min_rows)

        return rows_shown

    def get_context(self) -> dict:
        return {
            'form': self,
            'grouped_fields': getattr(self.Meta, 'grouped_fields', []),
        }

    @property
    def render(self) -> str:
        return render_to_string(
            template_name=self.template_name,
            context=self.get_context(),
        )

    def to_model(self, data: dict) -> tuple:
        """
        Get the values required to save/update a model instance. Return default
        DB fields separately (to be stored as attributes) from JSON fields (to
        be stored as data dictionary). For the latter, the field's to_json is
        used to retrieve the data. Repeating fields are added to the JSON fields
        by calling the JsonMultiRowField's to_json method.

        :param data: the data dictionary as submitted by the form.
        :return: tuple(dict, list): A tuple containing (1) default DB fields
            attribute values as dict and (2) JSON field values as list of
            JsonStructs.
        """
        fields = {}
        json_fields = []
        for name, field, is_json in self.model_fields():
            if is_json:
                json_fields.append(
                    field.to_json(keyword=self.Meta.keyword, key=name, value=data[name])
                )
            else:
                fields[name] = data[name]

        if self.has_repeating_fields:
            for field in self.Meta.repeating_fields:
                json_fields.append(
                    self.fields[field.name].to_json(
                        keyword=self.Meta.keyword, key=field.name,
                        data_list=data.get(field.name, [])))

        return fields, json_fields

    @classmethod
    def from_model(cls, instance) -> dict:
        """
        Retrieve data of the instance to be used in the form. For JSON fields,
        the field's 'from_json' method is called. For other fields, the data is
        retrieved as attribute of the instance. Repeating fields are retrieved
        differently.

        :param instance: The model instance (e.g. <Actor: 1>)
        :return: dict. A dictionary of form fields.
        """

        fields = {}
        for name, field, is_json in cls.model_fields():
            if is_json:
                if instance.data:
                    fields[name] = field.from_json(
                        data=instance.data.get(cls.Meta.keyword, {}), name=name
                    )
            else:
                fields[name] = getattr(instance, name)

        if hasattr(cls.Meta, 'repeating_fields'):
            for field in cls.Meta.repeating_fields:
                if not instance.data:
                    fields[field.name] = []
                    continue

                values = instance.data.get(cls.Meta.keyword, {}).get(field.name, [])

                values_as_list = []
                for v in values:
                    for k in field.row.keys():
                        values_as_list.append(v.get(k))

                fields[field.name] = values_as_list

        if hasattr(cls.Meta, 'through_fields'):
            for field in cls.Meta.through_fields:
                m2m = cls._get_through_relation(instance, field)

                field_data = []
                for obj in m2m.through_query:
                    for key in field.row.keys():
                        if key == 'to_id':
                            field_data.append(
                                getattr(obj, m2m.to_id_field))
                        elif key == 'through_id':
                            field_data.append(obj.id)
                        elif isinstance(obj.data, dict):
                            field_data.append(obj.data.get(key))
                        else:
                            field_data.append(None)

                fields[field.name] = field_data

        if hasattr(cls.Meta, 'link_fields'):
            for field in cls.Meta.link_fields:
                if field.is_foreign_key is True:
                    fk_object = getattr(instance, field.name)
                    if fk_object:
                        field_data = [fk_object.id]
                    else:
                        field_data = []

                else:
                    related_manager = getattr(instance, field.name)
                    field_data = related_manager.values_list('id', flat=True)

                fields[field.name] = field_data

        return fields

    @classmethod
    def model_fields(cls):
        fields = {
            **cls.base_fields, **cls.declared_fields
        }
        for name, field in fields.items():
            exclude_fields = getattr(cls.Meta, 'exclude_fields_for_model', [])
            if name not in exclude_fields:
                yield name, field, isinstance(field, JsonMixin)

    def save(self, object_id=None):
        fields, json_fields = self.to_model(data=self.cleaned_data)
        # Create or update model with its own attributes
        obj, _ = self.Meta.model.objects.update_or_create(
            pk=object_id, defaults=fields
        )

        # Write all json fields to the `data` column
        for field in json_fields:
            obj.data = self._update_data_dict(obj.data or {}, field)

        obj.save()

        if self.has_through_fields:
            for field in self.Meta.through_fields:
                data_list = self.fields[field.name].to_model(
                    data_list=self.cleaned_data.get(field.name, []))
                self.save_through(obj, field, data_list)

        if self.has_link_fields:
            for field in self.Meta.link_fields:
                self.save_link(
                    obj, field, self.cleaned_data.get(field.name, []))

        return obj

    def clean(self):
        """Manually check if through fields have a valid ID set"""
        super().clean()
        if self.has_through_fields:
            for field in self.Meta.through_fields:
                data_list = self.fields[field.name].to_model(
                    data_list=self.cleaned_data.get(field.name, []))
                for to_id, through_id, data in data_list:
                    if data and not to_id:
                        raise forms.ValidationError('Please select a valid link.')

    def save_through(self, obj, field, data_list):
        m2m = self._get_through_relation(obj, field)

        # Only the IDs of the current through objects are needed to keep track
        # of which through objects were removed
        through_ids = list(m2m.through_query.values_list('id', flat=True))

        for to_id, through_id, data in data_list:
            try:
                through_obj = m2m.through_manager.objects.get(pk=through_id)
                # Through object existed already, remove it from the list of IDs
                through_ids.remove(int(through_id))
            except (m2m.through_manager.DoesNotExist, ValueError):
                fields = {
                    m2m.from_field: obj,
                    m2m.to_id_field: to_id
                }
                through_obj = m2m.through_manager.objects.create(**fields)

            through_obj.data = data
            through_obj.save()

        # If there are any IDs of through objects left, these were removed.
        # Delete these links.
        for delete_id in through_ids:
            m2m.through_manager.objects.get(pk=delete_id).delete()

    def save_link(self, obj, field, data_list):
        link_objects = []
        for link_id in data_list:
            try:
                link_objects.append(field.to_model.objects.get(pk=int(link_id)))
            except (field.to_model.DoesNotExist, ValueError):
                pass

        if field.is_foreign_key is True:
            if link_objects:
                link_obj = link_objects[0]
            else:
                link_obj = None
            setattr(obj, field.name, link_obj)
        else:
            setattr(obj, field.name, link_objects)

        obj.save()

    @staticmethod
    def _get_through_relation(obj, field: ThroughModelField) -> ThroughRelation:
        # Find the right many2many relation
        m2m_field = None
        for rel in obj._meta.many_to_many:
            if rel.related_model == field.to_model:
                m2m_field = rel
        m2m_manager = getattr(obj, m2m_field.name)
        from_field = m2m_field.m2m_field_name()
        through_filter = {
            # Only look at relations of current object
            from_field: obj,
        }
        through_query = m2m_manager.through.objects.filter(**through_filter)
        return ThroughRelation(
            from_field=from_field,
            to_id_field=m2m_field.m2m_reverse_name(),
            through_manager=m2m_manager.through,
            through_query=through_query
        )

    @staticmethod
    def _update_data_dict(data: dict, field: JsonStruct) -> dict:
        data = ChainDict(data)
        data.set_key_chain(field.path, field.value)
        return data


def get_form_list(*forms):
    """
    Setup a form list for the wizard based on the keywords as used for the json
    keys.
    """
    for form in forms:
        yield (form.Meta.keyword, form )
