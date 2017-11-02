from django.apps import AppConfig


class FlexiFormConfig(AppConfig):
    name = 'flexiform'

    def ready(self):
        from . import receivers  # noqa

        # Discover all structures.
        from .models import autodiscover
        autodiscover()

        # 'Auto' spawn an instance of all registered structures.
        from .json_structures import auto_spawn
        auto_spawn.start()
