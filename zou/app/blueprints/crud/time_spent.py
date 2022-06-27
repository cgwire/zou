from zou.app.models.time_spent import TimeSpent

from .base import BaseModelsResource, BaseModelResource
from zou.app import name_space_time_spents


@name_space_time_spents.route('/')
class TimeSpentsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TimeSpent)


@name_space_time_spents.route('/<instance_id>')
class TimeSpentResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, TimeSpent)
