from importlib import import_module

from django.conf.urls import include, url
from django.utils.module_loading import import_string
from django.views import View


class DefaultPatterns:
    """
    Create default URL patterns for given app_name. Assumes the views-file
    is located in from <app_name> import views.
    """

    def __init__(
            self, app_name: str, include_search: bool=False,
            include_charts: bool=False, include_download: bool=False):
        self.app_name = app_name
        self.include_search = include_search
        self.include_charts = include_charts
        self.include_download = include_download
        self.views = import_module(f'{app_name}.views')
        self.model = import_string(f'{app_name}.models.{app_name.title()}')
        if not self.views:
            raise ModuleNotFoundError(
                f'"from {app_name} import views" found no valid module'
            )

    def _get_view(self, view_name: str) -> View:
        return getattr(self.views, f'{self.app_name.title()}{view_name}')

    @property
    def detail_view(self):
        return self._get_view('DetailView').as_view()

    @property
    def edit_view(self):
        # Handle initial migration where model Actor is not yet available. In
        # this case, form_list is not available. Return detail_view to prevent
        # errors.
        try:
            form_list = self.model._meta.structure.form_list
        except AttributeError:
            return self._get_view('ListView').as_view()
        return self._get_view('EditView').as_view(
            url_name=f'{self.app_name}:edit', done_step_name='done',
            form_list=form_list
        )

    @property
    def list_view(self):
        return self._get_view('ListView').as_view()

    @property
    def delete_view(self):
        return self._get_view('DeleteView').as_view()

    @property
    def search_view(self):
        return self._get_view('SearchListView').as_view()

    @property
    def search_detail_view(self):
        return self._get_view('SearchDetailView').as_view()

    @property
    def charts_view(self):
        return self._get_view('ChartsView').as_view()

    @property
    def download_view(self):
        return self._get_view('DownloadView').as_view()

    @property
    def codes_download_view(self):
        return self._get_view('DownloadCodesView').as_view()

    def get_patterns(self) -> tuple:
        patterns = (
            url(r'^$', self.list_view, name='list'),
            url(r'^add/', include([
                url(r'^$', self.edit_view, name='add'),
                url(r'^(?P<step>.+)/$', self.edit_view, name='add')
            ])),
            url(r'^(?P<pk>\d+)/edit/(?P<step>.+)/$', self.edit_view, name='edit'),
            url(r'^(?P<pk>\d+)/view/$', self.detail_view, name='detail'),
            url(r'^(?P<pk>\d+)/delete/$', self.delete_view, name='delete'),
        )
        if self.include_search is True:
            patterns += (
                url(r'^search/$', self.search_view, name='search_list'),
                url(r'^search/(?P<pk>\d+)/$',
                    self.search_detail_view, name='search_detail'),
            )
        if self.include_charts is True:
            patterns += (
                url(r'^charts/$', self.charts_view, name='charts'),
            )
        if self.include_download is True:
            patterns += (
                url(r'^download/$', self.download_view, name='download'),
                url(r'^codes/$', self.codes_download_view,
                    name='download_codes'),
            )
        return patterns
