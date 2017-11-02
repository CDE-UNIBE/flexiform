from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save)
def update_report_builder_properties(sender, **kwargs):
    """
    Update the properties for repeating form fields if a structure is set.
    """
    if hasattr(sender, '_meta') and hasattr(sender._meta, 'structure'):
        sender._meta.structure.update_properties()
