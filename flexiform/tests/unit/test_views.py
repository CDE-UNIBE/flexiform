from unittest.mock import Mock, MagicMock, sentinel, call

import pytest

from ...forms import BaseForm
from ...views import DownloadMixin, BaseFormMixin


class TestDownloadMixin:

    def test_from_data_single(self):
        DownloadView = DownloadMixin()
        DownloadView.queryset = [Mock(data={'foo': 'bar', 'faz': 'taz'})]
        data = DownloadView.from_data()
        assert data == [['faz', 'foo'], ['taz', 'bar']]

    def test_from_data_none(self):
        DownloadView = DownloadMixin()
        DownloadView.queryset = [Mock(data={'foo': 'bar', 'faz': ''})]
        data = DownloadView.from_data()
        assert data == [['faz', 'foo'], [None, 'bar']]

    def test_from_data_section(self):
        DownloadView = DownloadMixin()
        DownloadView.queryset = [Mock(data={
            'section1': {'foo': 'bar', 'faz': 'taz'}})]
        data = DownloadView.from_data()
        assert data == [['section1_faz', 'section1_foo'], ['taz', 'bar']]

    def test_from_data_repeating(self):
        DownloadView = DownloadMixin()
        DownloadView.queryset = [Mock(data={
            'section1': {'section1a': [
                {'foo': 'bar1', 'faz': 'taz1'},
                {'foo': 'bar2', 'faz': 'taz2'}]}})]
        data = DownloadView.from_data()
        assert data == [
            [
                'section1_section1a_faz_0', 'section1_section1a_faz_1',
                'section1_section1a_foo_0', 'section1_section1a_foo_1'],
            ['taz1', 'taz2', 'bar1', 'bar2']]

    def test_from_data_repeating_2(self):
        DownloadView = DownloadMixin()
        DownloadView.queryset = [
            Mock(data={
                'section1': {'section1a': [
                    {'foo': 'bar1', 'faz': 'taz1'},
                    {'foo': 'bar2', 'faz': 'taz2'}]}}),
            Mock(data={
                'section1': {'section1a': [
                    {'foo': 'barA', 'faz': 'tazA'},
                    {'foo': 'barB', 'faz': 'tazB'}]}}),
            Mock(data={
                'section1': {'section1a': [
                    {'foo': 'bar', 'faz': 'taz'}]}})]
        data = DownloadView.from_data()
        assert data == [
            [
                'section1_section1a_faz_0', 'section1_section1a_faz_1',
                'section1_section1a_foo_0', 'section1_section1a_foo_1'],
            ['taz1', 'taz2', 'bar1', 'bar2'],
            ['tazA', 'tazB', 'barA', 'barB'],
            ['taz', None, 'bar', None]]

    def test_from_data_empty_rows(self):
        DownloadView = DownloadMixin()
        DownloadView.queryset = [
            Mock(data={}),
            Mock(data={
                'section1': {'section1a': [
                    {'foo': 'barA', 'faz': 'tazA'}]}}),
            Mock(data={})]
        data = DownloadView.from_data()
        assert data == [
            [
                'section1_section1a_faz',
                'section1_section1a_foo'],
            [None, None],
            ['tazA', 'barA'],
            [None, None]]

    def test_from_data_model_fields(self):
        DownloadView = DownloadMixin()
        DownloadView.model_fields = ['field1', 'field2']
        DownloadView.queryset = [
            Mock(data={}, field1='field 1', field2='field 2'),
            Mock(data={
                'section1': {'section1a': [
                    {'foo': 'barA', 'faz': 'tazA'}]}}, field1=None, field2=None),
            Mock(data={}, field1=None, field2=None)]
        data = DownloadView.from_data()
        assert data == [
            [
                'field1', 'field2',
                'section1_section1a_faz',
                'section1_section1a_foo'],
            ['field 1', 'field 2', None, None],
            [None, None, 'tazA', 'barA'],
            [None, None, None, None]]


class TestBaseFormMixin:

    """
    @pytest.fixture
    def rf_authenticated(self, request, rf):
        # 'request' is used only for 'params'.
        method_name, path = request.param
        request = getattr(rf, method_name)(path)
        request.user = MagicMock()
        request.session = MagicMock()
        request.storage = MagicMock()
        return request

    @pytest.fixture()
    def setup_view(self, request, rf):
        # 'request' is used only for 'params'.
        view_klass, view_args, view_kwargs = request.param
        view = view_klass()
        view.request = rf
        view.args = view_args
        view.kwargs = view_kwargs
        return view

    @pytest.mark.parametrize('setup_view', [(
        BaseFormMixin,
        [],
        {'pk': 1},
    )], indirect=True)
    @pytest.fixture
    def base_view(self, setup_view):
        return setup_view

    @pytest.mark.foo
    @pytest.mark.parametrize('rf_authenticated', [(
        'get', '/1/'
    )], indirect=True)
    def test_dispatch(self, base_view, rf_authenticated):
        base_view.get = MagicMock()
        base_view.model = sentinel.model
        with mock.patch('apps.flexiform.views.get_object_or_404') as mock_get_object:
            base_view.dispatch(rf_authenticated)
            mock_get_object.assert_called_once_with(id=1, klass=sentinel.model)
    """

    @pytest.fixture()
    def setup_view(self):
        def _setup_view(view, request, *args, **kwargs):
            view.request = request
            view.args = args
            view.kwargs = kwargs
            return view
        return _setup_view

    @pytest.fixture
    def rf_authenticated(self, rf):
        def _rf_authenticated(method_name, path):
            request = getattr(rf, method_name)(path)
            request.user = MagicMock()
            request.session = MagicMock()
            request.storage = MagicMock()
            return request
        return _rf_authenticated

    def test_dispatch(self, setup_view, rf_authenticated, rf, monkeypatch):
        view = setup_view(BaseFormMixin(), rf, [], pk=1)
        request = rf_authenticated('get', '/1/')
        view.get = MagicMock()
        view.model = sentinel.model

        mock_get_object = MagicMock()
        monkeypatch.setattr('apps.flexiform.views.get_object_or_404', mock_get_object)

        view.dispatch(request=request)
        mock_get_object.assert_called_once_with(id=1, klass=sentinel.model)

    def test_get_form_initial_extra(self, setup_view, rf):
        view = setup_view(BaseFormMixin(), rf, [], pk=1)
        view.get_test_initial = MagicMock()
        view.initial_dict = {}
        view.object = None
        view.get_form_initial('test')
        view.get_test_initial.assert_called_once()

    def test_get_form_initial_form_step(self, setup_view, rf):
        view = setup_view(BaseFormMixin(), rf, [], pk=1)
        view.object = sentinel.object
        view.initial_dict = {}

        form = MagicMock(spec=BaseForm)
        view.model = MagicMock()
        view.model._meta.structure.form_list = (('test', form), )
        view.get_form_initial(step='test')

        assert call.from_model(instance=sentinel.object) in form.method_calls
