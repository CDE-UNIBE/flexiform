import contextlib

from .conf import FlexiFormConf  # noqa


def autodiscover():
    """
    Auto-discover INSTALLED_APPS json_structures.py modules and fail silently 
    when not present. This forces an import on them to register for the auto
    spawning of instances.
    """

    from importlib import import_module
    from django.apps import apps
    app_names = [app_config.name for app_config in apps.get_app_configs()]

    for app in app_names:
        # Fail silently
        with contextlib.suppress(Exception):
            import_module(f'{app}.forms')
