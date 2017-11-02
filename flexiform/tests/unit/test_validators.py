import pytest
from django.test import override_settings

from flexiform.validators import validate_no_underscore


class TestValidators:

    @override_settings(FLEXIFORM_MODEL_JSON_PROPERTIES_DELIMITER='--')
    def test_no_underscore(self):
        with pytest.raises(ValueError):
            validate_no_underscore('foo--bar')
