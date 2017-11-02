from .json_structures import auto_spawn


def model_structure(model, **options):
    """
    Register a structure to spawn an instance at application start.
    
    Usage:
    @model_structure(Actor)
    class ActorStructure(JsonStructure):
        pass
    """

    def wrapper(structure_class):
        auto_spawn.register(model, structure_class, **options)
        return structure_class

    return wrapper
