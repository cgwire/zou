from zou.app.models.search_filter import SearchFilter

from .base import BaseModelResource, BaseModelsResource
from zou.app import name_space_search_filters


@name_space_search_filters.route('/')
class SearchFiltersResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, SearchFilter)


@name_space_search_filters.route('/<instance_id>')
class SearchFilterResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, SearchFilter)
