from unittest.mock import MagicMock, sentinel

import pytest

from ...fields import JsonCharField
from ...forms import BaseForm
from ...json_structures import JsonStructure


class TestJsonStructure:

    @pytest.fixture(scope='class')
    def json_structure(self):
        class Form(BaseForm):
            testfield = JsonCharField()

            class Meta:
                pass

        class Structure(JsonStructure):
            form_list = (
                ('someform', Form),
            )

        return Structure(MagicMock())

    def test_form_structure(self):
        with pytest.raises(NotImplementedError):
            JsonStructure(MagicMock()).form_list

    def test_structure_sets_property(self, json_structure):
        assert isinstance(json_structure.model_class.someform_testfield, property)

    def test_structure_property_correct_value(self, json_structure):
        data_mock = MagicMock(data = {'someform': {'testfield': sentinel.value}})
        # property is not callable, but __get__ does the trick.
        assert json_structure.model_class.someform_testfield.__get__(data_mock) == \
               sentinel.value
