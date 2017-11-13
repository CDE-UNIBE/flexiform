=========
flexiform
=========

(Name is not good, but 'flexifom' can be grepped and replaced!)
Born out of the need to store structured data (such as geojson) and unstructured
document data (json) into the same model, based a wizard containing mixed forms.

All document data is stored in the same model field, getter-properties are
available.

Example
=======

Forms
-----
Use default django forms, mix with fields that store input to json. See
'translator', this information will be stored into the json-field on the model.
Camelcase is required for these fields, so the getter-properties can be properly
set up.

.. code-block:: python

    from flexiform import fields as json_fields

    class MetaInformationForm(BaseForm):
        topic = forms.ChoiceField(choices=[])
        interviewer = forms.ModelChoiceField(queryset=User.objects.all(), empty_label=None)
        translator = json_fields.JsonCharField(label=_('Translator'))
        interview_date = forms.DateField(widget=DatepickerWidget)
        interview_location = forms.PointField(
            widget=MapWidget(attrs={'default_lat': 46.94798, 'default_lon': 7.44743})
        )


Model
-----
The only required filed called 'data', which must be able to store JSON-data.

.. code-block:: python

    class Actor(TopicBase):
        interviewer = models.ForeignKey(User)
        interview_date = models.DateField(null=True, blank=True)
        interview_location = models.PointField(null=True, blank=True, srid=4326)
        created = models.DateTimeField(auto_now_add=True, editable=False)
        data = JSONField(null=True, blank=True)


Views
-----
Based on the formtools-wizard, the structures can now be used in formviews. The
wizard steps through 'meta' and 'organization', and can be used to add/edit
data. Data is stored to the ORM after each step. Other mixins for DetailView,
ListView or SearchView are provided as well.

.. code-block:: python

    from flexiform import views as core_views

    class ActorEditView(core_views.BaseFormMixin):
        model = Actor


URLs
----
A helper to provide url patterns for all views included in flexiform is available.
