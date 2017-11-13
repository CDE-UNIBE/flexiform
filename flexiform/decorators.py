from .json_structures import auto_spawn


def json_modelform(**options):
    """
    Register a structure to spawn an instance at application start.
    
    Usage:
    @json_modelform()
    class ActorForm(BaseForm):
        pass
    """

    def wrapper(form_class):
        auto_spawn.register(form_class, **options)
        return form_class

    return wrapper
