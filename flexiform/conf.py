from django.conf import settings
from appconf import AppConf


class FlexiFormConf(AppConf):
    # Delimiter for form_keyword and fields in json-fields. Also used to put
    # properties to model.
    MODEL_JSON_PROPERTIES_DELIMITER = '_'
