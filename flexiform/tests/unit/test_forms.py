import collections
from unittest.mock import MagicMock

import pytest
from django.forms import fields, widgets
from django.test import override_settings

from ...fields import JsonCharField, JsonStruct
from ...forms import BaseForm, RepeatingRowField


class TestBaseForm:

    @pytest.fixture
    def invalid_form(self):
        class Tmp(BaseForm):
            invalid__fieldname = JsonCharField()

            class Meta:
                exclude_fields_for_model = []

        return Tmp

    @pytest.fixture
    def repeating_form(self):

        class Tmp(BaseForm):

            class Meta:
                repeating_fields = [
                    RepeatingRowField(
                        name='one',
                        row={
                            'one1': (
                                fields.CharField(label='One 1'), widgets.TextInput),
                            'one2': (
                                fields.IntegerField(label='One 2'), widgets.NumberInput),
                        },
                        options={},
                    )
                ]

                keyword = 'section2'
                model = MagicMock()
                model.objects.update_or_create.return_value = MagicMock(), None

        return Tmp

    @override_settings(MODEL_JSON_PROPERTIES_DELIMITER='__')
    def test_no_underscore_field_names(self, invalid_form):
        with pytest.raises(ValueError):
            invalid_form()

    def test_repeating_none(self, repeating_form):
        form = repeating_form()
        invalid = form.to_model({'foo': 'bar'})
        assert invalid == ({}, [JsonStruct(path=['section2', 'one'], value=[])])

    def test_repeating_one(self, repeating_form):
        form = repeating_form()
        repeating_one = form.to_model({'one': ['un', '1']})
        repeating_one_expected = {'one1': 'un', 'one2': '1'}
        assert repeating_one == ({}, [JsonStruct(
            path=['section2', 'one'], value=[
                collections.OrderedDict(repeating_one_expected)])])

    def test_repeating_multiple(self, repeating_form):
        form = repeating_form()
        repeating_two = form.to_model({'one': ['un', '1', 'dos', '2']})
        repeating_two_expected = [
            {'one1': 'un', 'one2': '1'}, {'one1': 'dos', 'one2': '2'}]
        assert repeating_two == ({}, [JsonStruct(
            path=['section2', 'one'], value=repeating_two_expected)])

    def test_save_single(self, repeating_form):
        form = repeating_form(prefix='section2', data={'section2-one_0': 'Un', 'section2-one_1': '1'})
        assert form.is_valid()
        obj = form.save()
        assert obj.data == {'section2': {'one': [{'one1': 'Un', 'one2': '1'}]}}

    def test_save_repeating(self, repeating_form):
        form = repeating_form(prefix='section2', data={
            'section2-one_0': 'Un', 'section2-one_1': '1',
            'section2-one_2': 'Dos', 'section2-one_3': '2',
        })
        assert form.is_valid()
        obj = form.save()
        assert obj.data == {'section2': {'one': [
            {'one1': 'Un', 'one2': '1'},
            {'one1': 'Dos', 'one2': '2'},
        ]}}

    def test_save_repeating_deleted_first_row(self, repeating_form):
        form = repeating_form(prefix='section2', data={
            'section2-one_2': 'Dos', 'section2-one_3': '2',
        })
        assert form.is_valid()
        obj = form.save()
        assert obj.data == {'section2': {'one': [
            {'one1': 'Dos', 'one2': '2'},
        ]}}

    def test_save_repeating_only_one_entry_not_beginning(self, repeating_form):
        form = repeating_form(prefix='section2', data={
            'section2-one_2': '', 'section2-one_3': '2',
        })
        assert form.is_valid()
        obj = form.save()
        assert obj.data == {'section2': {'one': [
            {'one1': '', 'one2': '2'},
        ]}}
