import csv
import itertools
import json
import uuid
from collections import OrderedDict, defaultdict
from unittest.mock import Mock

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.gis.geos import Point
from django.core.exceptions import FieldDoesNotExist
from django.db.models import F, Model, Q, QuerySet
from django.forms import Media
from django.http import (Http404, HttpResponseRedirect, JsonResponse,
                         StreamingHttpResponse)
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, TemplateView
from django.views.generic.list import MultipleObjectMixin
from formtools.wizard.views import NamedUrlWizardView

from .fields import JsonChoiceField
from .formsets import BaseFlexiFormSet
from .forms import BaseForm, ChainDict
from .json_structures import JsonStructure

from .conf import settings


class RetrieveMixin:
    """
    Get the object based on the from current form.
    """
    # The 'pk' in the URL should always point to the same instance. Set this,
    # it defaults to the model of the first form
    routing_object_class = None

    def get_routing_object(self):
        return self.routing_object_class or self.get_first_form_model()

    def get_first_form_model(self) -> Model:
        """
        Get the first model
        """
        try:
            return list(self.form_list.values())[0].Meta.model
        except (IndexError, AttributeError):
            raise NotImplementedError('Please set a routing_object_class')

    def get_object(self, form):
        # the object used for routing
        if 'pk' not in self.kwargs:
            return None
        return get_object_or_404(
            klass=self.get_routing_object(),
            id=self.kwargs['pk']
        )

    def get_form_initial(self, step: str) -> dict:
        if hasattr(super(), 'get_form_initial'):
            initial = super().get_form_initial(step)
        else:
            initial = {}

        extra_method_name = f'get_{step}_initial'
        if hasattr(self, extra_method_name):
            return getattr(self, extra_method_name)()

        form = dict(self.form_list)[step]
        is_model_form = hasattr(form.Meta, 'model')
        is_routing_object_instance = self.object and is_model_form and issubclass(
            form.Meta.model, type(self.object)
        )
        if is_routing_object_instance:
            initial.update(form.from_model(instance=self.object))
        elif issubclass(form, BaseFlexiFormSet):
            # Assume BaseFlexiFormSet instance is related to self.object
            try:
                rel_field = self.object._meta.get_field(form.model._meta.model_name)
            except FieldDoesNotExist:
                pass  # NOTE: Silence exception when related field doesn't exist
            else:
                object_set = getattr(self.object, rel_field.get_accessor_name())
                initial = [form.form.from_model(instance=i) for i in object_set.all()]

        return initial

    @property
    def model_name(self):
        return self.get_routing_object().__name__.lower()


class BaseFormMixin(LoginRequiredMixin, RetrieveMixin, NamedUrlWizardView):
    """
    Shared functionality for add/edit wizard views.

    * Save data after each 'submit'
    """
    # Don't put data to session, it's written and read from the ORM
    storage_name = 'flexiform.wizard.storage.no_session.NoSession'
    template_name = 'flexiform/form.html'

    def dispatch(self, request, *args, **kwargs):
        """
        Redirect to fist step if no step is set; set object to 'self'. 
        """
        try:
            step = self.kwargs['step']
        except KeyError:
            first_step = list(self.form_list.keys())[0]
            first_step_model = self.form_list[first_step].Meta.model.__name__
            view_name = f'{first_step_model.lower()}:add'
            return HttpResponseRedirect(reverse(
                view_name, kwargs={'step': first_step})
            )

        self.object = self.get_object(form=self.form_list[step])
        return super().dispatch(request, *args, **kwargs)

    def get(self, *args, **kwargs):
        # It is necessary to reset the storage before rendering each step.
        # Otherwise data from the storage will still be used to populate the
        # form, even though explicitly session storage is used. Did not know
        # where else to put this line.
        self.storage.reset()
        return super().get(*args, **kwargs)

    def process_step(self, form: BaseForm) -> dict:
        # setting the object is important for the next step url.
        if hasattr(form, 'save'):
            model_instance = form.save(self.kwargs.get('pk', None))
            if not isinstance(form, BaseFlexiFormSet):
                self.object = model_instance
        return self.get_form_step_data(form)

    def get_context_data(self, form: BaseForm, **kwargs) -> dict:
        context = super().get_context_data(form, **kwargs)
        labelled_steps = list(self.get_labelled_steps())
        step_position = [
            s[0] for s in labelled_steps].index(self.kwargs['step']) + 1
        context.update({
            'object': self.object,
            'labelled_steps': labelled_steps,
            'labelled_step': dict(labelled_steps).get(self.kwargs['step']),
            'helptext': getattr(form.Meta, 'helptext', ''),
            'step_position': step_position,
            'step_percent': int(
                step_position / context['wizard']['steps'].count * 100),
            'app_name': self.model_name,
        })
        return context

    def get_step_url(self, step: str) -> str:
        if self.object:
            return reverse(f'{self.model_name}:edit', kwargs={
                'step': step,
                'pk': self.object.id
            })
        return reverse(f'{self.model_name}:add', kwargs={
            'step': step,
        })

    def get_next_step(self, step=None):
        """
        If "reload" is a key of the POST data return the same step again (e.g.
        after adding a new repeating form row). Otherwise get the next step as
        usual.
        """
        load_step = self.request.POST.get('load_step')
        if load_step:
            if load_step == '1':
                load_step = self.steps.current
            return load_step
        return super().get_next_step(step)

    def render_next_step(self, form, **kwargs):
        """
        Show a success message that the step was saved.
        """
        messages.success(self.request, 'The section was successfully saved.')
        return super().render_next_step(form, **kwargs)

    def render_done(self, form, **kwargs):
        """
        Simply redirect to the list view, as data is stored after each submit.
        Show a success message that the item was saved.
        """
        # If the same step is to be reloaded again, do this instead.
        if self.request.POST.get('load_step'):
            return self.render_next_step(form, **kwargs)

        item_url = reverse(
            f'{self.model_name}:detail',
            kwargs={'pk': self.kwargs['pk']})
        messages.success(
            self.request,
            f'<a href="{item_url}">entry</a> was successfully saved.')
        return HttpResponseRedirect(redirect_to=reverse(
            f'{self.model_name}:list'
        ))

    def get_labelled_steps(self):
        """
        Return a list of tuples with all the labels for the form steps. If a
        label is not defined in the step's Meta class, the keyword is used as
        label.

        :return: list. A list of tuples containing (1) the keyword and (2) the
            label of the step.
        """
        for keyword, form in self.form_list.items():
            try:
                label = form.Meta.label
            except AttributeError:
                label = keyword
            yield (keyword, label)


class AjaxSearchThroughMixin(MultipleObjectMixin):

    def json_mapping(self, obj) -> dict:
        raise NotImplemented

    def dispatch(self, request, *args, **kwargs):
        if not request.is_ajax():
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_object_list(self) -> list:
        if self.paginate_by:
            return self.get_queryset()[: self.paginate_by]
        else:
            return self.get_queryset()

    def get_json_data(self):
        for obj in self.get_object_list():
            yield self.json_mapping(obj)

    def get(self, request, *args, **kwargs):
        return JsonResponse(list(self.get_json_data()), safe=False)


class AjaxSearchListView(AjaxSearchThroughMixin, View):
    http_method_names = ['get']
    paginate_by = 10

    def get_queryset(self):
        """
        Use the model's search_lookup_paths to search in the JSON data of the
        model. Also search in PK if search term is an int.
        """
        queryset = super().get_queryset()

        search_term = self.request.GET.get('term', '')

        try:
            lookup_paths = self.model.search_lookup_paths
        except AttributeError:
            raise Exception(
                '"search_lookup_paths" need to be configured for the model')

        q_objects = Q()
        for path in lookup_paths:
            key = '__'.join(('data',) + path + ('icontains',))
            q_objects.add(Q(**{key: search_term}), Q.OR)

        try:
            pk = int(search_term)
            q_objects.add(Q(pk=pk), Q.OR)
        except ValueError:
            pass

        return queryset.filter(q_objects)


class AjaxSearchDetailView(AjaxSearchThroughMixin, View):
    http_method_names = ['get']
    paginate_by = None

    def get_queryset(self):
        obj = get_object_or_404(self.model, pk=self.kwargs['pk'])
        return [obj]


class ChartsView(TemplateView):

    model = None
    template_name = 'flexiform/charts.html'

    section_keyword = ''
    question_keyword = ''
    question = None

    topics = []
    chart_fields = {}

    def set_attributes(self):
        self.set_chart_fields()
        self.set_section_question()
        self.set_question()

    def set_chart_fields(self):
        """
        Set chart_fields as a dict with sections and questions. This contains
        all questions which can be used as charts.
        """
        fields = {}
        for section_keyword, form in self.model._meta.structure.form_list:
            if not hasattr(form.Meta, 'chart_fields'):
                continue
            form_obj = form()
            for field_name in form.Meta.chart_fields:
                fields.setdefault(
                    section_keyword,
                    {'label': getattr(form.Meta, 'label', section_keyword)})
                fields[section_keyword].setdefault(
                    'fields', {})[field_name] = form_obj.fields.get(field_name)
        self.chart_fields = fields

    def set_section_question(self):
        """
        Set section_keyword and question_keyword based on GET parameters. If
        these are not provided, use the first entry of chart_fields.
        """
        key_params = self.request.GET.get('key', '').split('__')
        if len(key_params) == 2:
            self.section_keyword = key_params[0]
            self.question_keyword = key_params[1]
        else:
            try:
                self.section_keyword = list(self.chart_fields.keys())[0]
                self.question_keyword = list(
                    self.chart_fields[self.section_keyword]['fields'].keys())[0]
            except (IndexError, KeyError):
                pass

    def set_question(self):
        """
        Set question with the current chart question. If the question is not
        found (e.g. keywords are invalid), raise 404.
        """
        try:
            self.question = self.chart_fields[
                self.section_keyword]['fields'][self.question_keyword]
        except KeyError:
            raise Http404

    def get_queryset(self) -> QuerySet:
        """
        Return the queryset needed for the aggregated charts.
        :return: A queryset, each entry containing two values: topic and
        extra_field
        """
        queryset = self.model.objects

        self.topics = self.request.user.profile.topics
        if self.topics and settings.CORE_ALL not in self.topics:
            queryset = queryset.filter(topic__in=self.topics)

        if isinstance(self.question, JsonChoiceField):
            # Add JSON values to extra_field
            queryset = queryset.extra(select={
                'extra_field':
                    f"data->'{self.section_keyword}'->'{self.question_keyword}'"
            })
        else:
            # Get DB column and rename it to extra_field
            queryset = queryset.annotate(extra_field=F(self.question_keyword))

        return queryset.values('topic', 'extra_field')

    def get_aggregated_data(self) -> dict:
        """
        Manually aggregate the query result (was not able to aggregate JSON
        values correctly), which is not efficient. Either come up with a query
        to do this in the DB or cache the aggregated results?
        :return: A dict with data (count of entries) aggregated by profile, then
        by value
        """
        res = {}
        for item in self.get_queryset():
            if item['extra_field'] in ['', None]:
                continue
            try:
                res[item['topic']][item['extra_field']] += 1
            except KeyError:
                res = ChainDict(res)
                res.set_key_chain([item['topic'], item['extra_field']], 1)

        return res

    def get_chart_data(self) -> dict:
        """
        Return the template values needed to create the chart.
        """
        choices = dict(self.question.choices)
        # Remove the first empty placeholder
        choices.pop(None, None)

        data = self.get_aggregated_data()

        # factor out
        topics = settings.CORE_TOPICS
        if self.topics and self.topics != ['']:
            topics = [t for t in topics if t[0] in self.topics]

        colors = dict(settings.CORE_TOPIC_COLORS)

        values = []
        for topic_key, topic_label in topics:
            values.append({
                'label': topic_label,
                'data': [data.get(topic_key, {}).get(k, 0) for k in
                         choices.keys()],
                'backgroundColor': colors[topic_key],
            })

        return {
            'values': values,
            'labels': [str(c) for c in choices.values()],
            'title': self.question.label,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        self.set_attributes()
        context.update({
            'chart_fields': self.chart_fields,
            **self.get_chart_data(),
        })

        return context


class NetworkGraphMixin:
    """
    Show a network graph. Links connected to a given object are queried, along
    with the nodes on the other end. This step is repeated for the new nodes
    until max_depth is reached.

    This is not optimized for performance but should suffice for small networks
    (and low max_depth).
    """
    model = None
    object = None
    template_name = 'flexiform/network_graph.html'

    link_model = None
    link_from = ''
    link_to = ''
    foreign_keys = []
    max_depth = 2

    nodes = []
    links = []

    ego_color = '#e41a1c'

    def get_node_color(self, node: Model, link: Model=None) -> str:
        """
        Get the color of the node as defined in settings.NETWORK_GRAPH_COLOR
        (in app's conf.py)
        """
        if node == self.object:
            return self.ego_color
        return getattr(
            settings, f'{node.__class__.__name__.upper()}_NETWORK_GRAPH_COLOR',
            'silver')

    def get_node_radius(self, node: Model, link: Model=None) -> int:
        return 8

    def get_node_stroke_width(self, node: Model, link: Model=None) -> float:
        return 1.5

    def get_node_is_ego(self, node: Model, link: Model=None) -> bool:
        return node == self.object

    def get_link_distance(self, link: Model) -> int or None:
        return None

    def get_link_stroke_width(self, link: Model) -> float:
        return 2.5

    def get_link_stroke_dasharray(self, link: Model) -> str:
        return '0, 0'

    @staticmethod
    def _get_node_id(node: Model) -> str:
        """Get a unique ID for the node (prefixing node's class name to ID)"""
        return f'{node.__class__.__name__}_{node.id}'

    def get_node_ids(self) -> list:
        return [n['id'] for n in self.nodes]

    def get_link_ids(self) -> list:
        return [l['id'] for l in self.links]

    def get_link_attributes(
            self, link: Model, source_node: Model, target_node: Model) -> dict:
        """Return the attributes needed to draw a link in the graph."""
        source_node, target_node = self.get_source_target_nodes(
            link, source_node, target_node)
        return {
            'source': self._get_node_id(source_node),
            'target': self._get_node_id(target_node),
            'id': link.id,
            'tooltip': self.get_link_tooltip(link),
            'value': 5,
            'stroke': '#333',
            'stroke_width': self.get_link_stroke_width(link),
            'stroke_opacity': 1,
            'stroke_dasharray': self.get_link_stroke_dasharray(link),
            'distance': self.get_link_distance(link),
        }

    def get_node_attributes(self, node: Model, link: Model=None) -> dict:
        """Return the attributes needed to draw a node in the graph."""
        return {
            'id': self._get_node_id(node),
            'tooltip': self.get_node_tooltip(node, link),
            'radius': self.get_node_radius(node, link),
            'stroke': '#333',
            'stroke_width': self.get_node_stroke_width(node, link),
            'fill': self.get_node_color(node, link),
            'is_ego': self.get_node_is_ego(node, link),
        }

    def get_source_target_nodes(
            self, link: Model, source_node: Model, target_node: Model) -> tuple:
        """
        Overwrite this function if the link is directed and it therefore matters
        which node is source and which is target.
        """
        return source_node, target_node

    def get_node_tooltip(self, node: Model, link: Model=None) -> str:
        """Return the content rendered in the tooltip of the node."""
        try:
            return node.get_network_graph_tooltip(link)
        except AttributeError:
            return str(node)

    def get_link_tooltip(self, link: Model) -> str:
        """Return the content rendered for the tooltip for the link"""
        try:
            return link.get_network_graph_tooltip()
        except AttributeError:
            return ''

    def _set_node_links_by_node(self, node: Model, current_depth: int):
        """
        Get all links and nodes at the end of the link connected to the current
        node.

        Example: [A] -- [F] -- [A] / link_from: 'a' / link_to: 'f'
        In the second iteration ([F] -- [A]), link_from and link_to need to be
        switched (reverse_link=True) for the generic query to work.
        """
        reverse_link = current_depth % 2 == 0

        if not reverse_link:
            link_start = self.link_from
            link_end = self.link_to
        else:
            link_start = self.link_to
            link_end = self.link_from

        # Loop through all links attached to the current node.
        for link in self.link_model.objects.filter(**{link_start: node}):

            # Add the node at the end of the link if not collected already.
            end_node = getattr(link, link_end)
            if self._get_node_id(end_node) not in self.get_node_ids():
                self.nodes.append(self.get_node_attributes(end_node, link))

            if link.id in self.get_link_ids():
                continue

            # source and target should always be in the same order. This is
            # important for directed links (e.g. Actor -> Flow).
            if not reverse_link:
                source_node = node
                target_node = end_node
            else:
                source_node = end_node
                target_node = node

            self.links.append(
                self.get_link_attributes(link, source_node, target_node))

            # If max_depth is not yet reached, travel further down the nodes.
            if current_depth < self.max_depth:
                self._set_node_links_by_node(end_node, current_depth + 1)

    def _set_node_links_from_2_foreign_keys(
            self, node: Model, current_depth: int):
        """
        Starting from a node, get the links (where the object is linked as a
        foreign key) and the other node linked there as well.

        Example:
            [F]
                has FK 'giving_actor' pointing to [A1]
                has FK 'receiving_actor' pointing to [A2]

            If this function is called with 'node' [A1], the link added is [F]
            not the other node added is [A2].
        """
        # Create an OR filter based on the foreign keys
        or_filter = Q()
        or_filter_dict = {key: node for key in self.foreign_keys}
        for key, value in or_filter_dict.items():
            or_filter |= Q(**{key: value})

        # Loop through all link objects where the current node is linked as a
        # foreign key
        for link in self.link_model.objects.filter(or_filter):

            # Determine which node is the other end.
            reverse_direction = True
            other_node = getattr(link, self.foreign_keys[0])
            if other_node == node:
                reverse_direction = False
                other_node = getattr(link, self.foreign_keys[1])

            if other_node is None:
                continue

            # Add the other node if not collected already
            if self._get_node_id(other_node) not in self.get_node_ids():
                self.nodes.append(self.get_node_attributes(other_node))

            if link.id in self.get_link_ids():
                continue

            # Determine which node is source and which is target
            if reverse_direction is False:
                source_node = node
                target_node = other_node
            else:
                source_node = other_node
                target_node = node

            self.links.append(self.get_link_attributes(
                link, source_node, target_node))

            # If max_depth is not yet reached, travel further down the nodes
            if current_depth < self.max_depth:
                self._set_node_links_from_2_foreign_keys(
                    other_node, current_depth + 1)

    def set_nodes_links(self):
        """Return all collected nodes and lists."""
        self.nodes = [self.get_node_attributes(self.object)]
        self.links = []
        self._set_node_links_by_node(self.object, current_depth=1)

    def get_graph_options(self) -> dict:
        return {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.set_nodes_links()
        
        # Number links going from and to the same nodes. This is used for
        # multiple arrows to be drawn subsequentially instead of overlapping
        # themselves.
        for link in self.links:

            # Continue if the link is already numbered
            if 'link_num' in link:
                continue

            # Find all links with identical source and target nodes
            conditions = {'source': link['source'], 'target': link['target']}
            matches = [l for l in self.links if all(
                [c in set(l.items()) for c in set(conditions.items())])]

            # Give each link a number
            for i, match in enumerate(matches):
                match['link_num'] = i + 1

        # Unique <div> ID is needed if multiple graphs are on the same page.
        # D3 cannot handle IDs starting with a number, therefore adding a letter
        context.update({
            'div_id': 'x' + str(uuid.uuid4()).replace('-', ''),
            'nodes': json.dumps(self.nodes),
            'links': json.dumps(self.links),
            'graph_options': json.dumps(self.get_graph_options()),
        })
        return context


class BaseFormViewMixin(RetrieveMixin, TemplateView):

    # As multiple forms are rendered on a single page, it is necessary to
    # collect the unique media assets instead of letting each form render its
    # own (possibly duplicate) assets
    form_media = Media()
    steps = Mock()

    def get(self, request, *args, **kwargs):
        self.forms = self.get_readonly_forms()
        return super().get(request=request, *args, **kwargs)

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context.update({
            'forms': self.forms,
            'form_media': self.form_media,
        })
        return context

    def get_readonly_forms(self) -> list:
        """
        Return a list of tuples containing all readonly forms (populated with
        initial values) of the current structure.

        :return: list. A list of tuples containing (1) the keyword of the form
            and (2) the form itself.
        """
        ret = []
        for keyword, form in self.form_list:
            self.object = self.get_object(form=form)
            # Mock the 'current step' of the session wizard for the
            # 'get_foo_initial' methods.
            self.steps.current = keyword
            initial = self.get_form_initial(keyword)

            if issubclass(form, BaseFlexiFormSet):
                form_instance = form(prefix=keyword, initial=initial, form_kwargs={'readonly': True})
            else:
                form_instance = form(prefix=keyword, initial=initial, readonly=True)

            # Add form media
            self.form_media.add_js(form_instance.media._js)
            self.form_media.add_css(form_instance.media._css)

            ret.append((keyword, form_instance))
        return ret


class Echo:
    """
    https://docs.djangoproject.com/en/1.11/howto/outputting-csv/#streaming-large-csv-files

    An object that implements just the write method of the file-like interface.
    """
    def write(self, value):
        """Write the value by returning it, instead of storing in a buffer."""
        return value


class DownloadCodesView(TemplateView):
    """
    A view to export the codes (the keywords of the choices) of selection
    fields. Returns a CSV file.
    """
    model = None
    paginate_by = None
    filename = 'export_codes.csv'

    def get(self, request, *args, **kwargs):

        rows = [('Section', 'Question', 'Option', 'Code')]
        rows.extend(self.get_rows())

        pseudo_buffer = Echo()
        writer = csv.writer(pseudo_buffer)
        response = StreamingHttpResponse(
            (writer.writerow(row) for row in rows), content_type='text/csv')
        response[
            'Content-Disposition'] = f'attachment; filename="{self.filename}"'
        return response

    def get_rows(self):
        structure = self.model._meta.structure
        for __, form in structure.forms.items():
            section_label = form.Meta.label
            for __, field in form().fields.items():
                if hasattr(field, '_choices'):
                    for choice in field._choices:
                        # Do not include empty (placeholder) options
                        if not choice[0]:
                            continue
                        yield section_label, field.label, choice[1], choice[0]



class DownloadMixin(ListView):

    model_fields = []
    filename = 'export.csv'

    def set_model_fields(self):
        self.model_fields = []
        for field in self.model._meta.get_fields():
            if field.many_to_many or field.one_to_many:
                continue
            if field.name != 'data':
                self.model_fields.append(field.attname)

    def get_values_by_path(self, data: dict, path: list) -> list:
        """
        Return a list of values found at the given path of a data dict. Always
        returns a list.
        """
        data_part = data.get(path[0])
        if not data_part:
            return [None]

        if len(path) == 1:
            # Last element
            if not isinstance(data_part, list):
                # Turn into list if it is not already
                return [str(data_part)]
            else:
                return data_part

        if isinstance(data_part, dict):
            # Drill down further along the path
            return self.get_values_by_path(data_part, path[1:])

        if isinstance(data_part, list):
            # Repeating question
            repeating_data = []
            for repeating in data_part:
                question_data = self.get_values_by_path(repeating, path[1:])
                repeating_data.extend(question_data)
            return repeating_data

        else:
            raise Exception(
                f'data_part should be either list or dict: {data_part}')

    @staticmethod
    def get_attribute(obj: Model, field_name: str) -> str:
        """
        Return an attribute of the object, possibly transform the value before
        returning it.
        """
        attr = getattr(obj, field_name)
        if isinstance(attr, Point):
            # For Points, return value as well known text
            return attr.wkt
        return attr

    def from_structure(self, structure: JsonStructure) -> list:
        """
        Return rows of data based on the properties as defined in the provided
        structure. Model fields are added at the beginning of each row. Only data
        rows are returned, without header.
        """
        for obj in self.get_queryset():
            row = []
            for field in self.model_fields:
                row.append(self.get_attribute(obj, field))
            for prop in structure.properties:
                row.append(getattr(obj, prop))
            yield row

    def from_data(self) -> list:
        """
        Return rows of data based on the data itself (as in the object's "data"
        field). Model fields are added at the beginning of each row. The first
        returned row serves as table header.
        """
        obj_list = self.get_queryset()

        # First, collect all keys available in all objects along with their
        # paths
        key_paths = {}
        for obj in obj_list:

            for section, section_data in obj.data.items():
                if not isinstance(section_data, dict):
                    # Already single question
                    key = section
                    key_paths[key] = [section]
                    continue

                for question, question_data in section_data.items():
                    if isinstance(question_data, list):
                        # Repeating group of questions, get all unique keys
                        # within list of dicts
                        keys = []
                        for question_dict in question_data:
                            keys.extend(question_dict.keys())
                            keys = list(set(keys))

                        for k in keys:
                            key = f'{section}_{question}_{k}'
                            key_paths[key] = [section, question, k]

                    else:
                        key = f'{section}_{question}'
                        key_paths[key] = [section, question]

        # Sort keys
        key_paths = OrderedDict(sorted(key_paths.items()))

        # Now get the values at the collected paths for each object
        key_values = defaultdict(list)
        for obj in obj_list:
            for field in self.model_fields:
                key_values[field].append([self.get_attribute(obj, field)])

            for key, path in key_paths.items():
                values = self.get_values_by_path(obj.data, path)
                key_values[key].append(values)

        # Put them together in a flat table
        rows = defaultdict(list)
        headers = []
        for key, value_rows in key_values.items():

            num_cols = len(max(value_rows, key=len))
            if num_cols > 1:
                for i in range(num_cols):
                    headers.append(f'{key}_{i}')
            else:
                headers.append(key)

            for obj_index, value_row in enumerate(value_rows):
                values = [None] * num_cols
                for i, v in enumerate(value_row):
                    values[i] = v
                rows[obj_index].extend(values)

        return [headers] + list(rows.values())

    def get(self, request, *args, **kwargs):

        self.set_model_fields()

        if hasattr(self.model, '_meta') and hasattr(self.model._meta, 'structure'):
            # structure available
            structure = self.model._meta.structure
            rows = list(itertools.chain(
                [self.model_fields + structure.properties],
                self.from_structure(structure)))
        else:
            # No structure available
            rows = self.from_data()
            
        pseudo_buffer = Echo()
        writer = csv.writer(pseudo_buffer)
        response = StreamingHttpResponse(
            (writer.writerow(row) for row in rows), content_type='text/csv')
        response[
            'Content-Disposition'] = f'attachment; filename="{self.filename}"'
        return response


class PaginationMixin:
    """
    Add a sliced pagination to a list. Only a range of pages below and above the
    current page (adjacent_pages) is shown, along with the first and last
    available page.

    Use together with template "core/snippets/pagination.html" (to be included
    in the list template)
    """
    adjacent_pages = 3

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not context.get('is_paginated', False):
            return context

        current_page = context.get('page_obj').number
        num_pages = context.get('paginator').num_pages

        start_page = max(current_page - self.adjacent_pages, 1)
        if start_page < self.adjacent_pages:
            start_page = 1
        end_page = current_page + self.adjacent_pages + 1
        if end_page >= num_pages - 1:
            end_page = num_pages + 1
        page_numbers = [
            n for n in range(start_page, end_page) if 0 < n <= num_pages]

        context.update({
            'page_numbers': page_numbers,
            'show_first': 1 not in page_numbers,
            'show_last': num_pages not in page_numbers,
        })

        return context


class BaseDeleteMixin:
    template_name = 'flexiform/crud/object_confirm_delete.html'

    def get_success_url(self):
        return reverse(f'{self.model.__name__.lower()}:list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'The object was successfully deleted.')
        return super().delete(request, *args, **kwargs)
