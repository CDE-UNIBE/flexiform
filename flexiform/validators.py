from .conf import settings


def validate_no_underscore(value: str) -> None:
    if settings.FLEXIFORM_MODEL_JSON_PROPERTIES_DELIMITER in value:
        raise ValueError('No underscore allowed in value %s' % value)
