from django.forms import formsets, modelformset_factory
from django.template.loader import render_to_string


class BaseFormSet(formsets.BaseFormSet):
    template_name = 'flexiform/formset/base.html'

    def get_context(self):
        return {
            'forms': [form for form in self],
            'management_form': self.management_form
        }

    def as_table(self):
        return render_to_string(
            template_name=self.template_name,
            context=self.get_context(),
        )

    def save(self, object_id):
        for form in self:
            form.save(object_id)


def flexiformset_factory(model, parent_model, form, formfield_callback=None,
                         extra=1, can_delete=False,
                         can_order=False, max_num=None, fields=None, exclude=None,
                         widgets=None, validate_max=False, localized_fields=None,
                         labels=None, help_texts=None, error_messages=None,
                         min_num=None, validate_min=False, field_classes=None):

    form.Meta.parent_model = parent_model
    return modelformset_factory(model, form=form, formfield_callback=formfield_callback,
                         formset=BaseFormSet, extra=extra, can_delete=can_delete,
                         can_order=can_order, max_num=max_num, fields=fields, exclude=exclude,
                         widgets=widgets, validate_max=validate_max, localized_fields=localized_fields,
                         labels=labels, help_texts=help_texts, error_messages=error_messages,
                         min_num=min_num, validate_min=validate_min, field_classes=field_classes)
