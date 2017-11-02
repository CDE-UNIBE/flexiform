from unittest import TestCase
from unittest.mock import sentinel

from ...fields import JsonCharField, JsonStruct


class TestJsonValueField(TestCase):

    def setUp(self):
        self.field = JsonCharField()

    def test_from_json_dict(self):
        data = {sentinel.key: sentinel.value}
        value = self.field.from_json(data=data, name=sentinel.key)
        assert sentinel.value, value

    def test_to_json(self):
        self.assertEqual(
            self.field.to_json(sentinel.keyword, sentinel.key, sentinel.value),
            JsonStruct(path=[sentinel.keyword, sentinel.key], value=sentinel.value)
        )
