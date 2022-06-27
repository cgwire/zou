from zou.app.models.news import News

from .base import BaseModelResource, BaseModelsResource
from zou.app import name_space_news


@name_space_news.route('/')
class NewssResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, News)


@name_space_news.route('/<instance_id>')
class NewsResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, News)
