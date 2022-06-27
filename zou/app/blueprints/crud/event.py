from zou.app.models.event import ApiEvent

from .base import BaseModelResource, BaseModelsResource
from zou.app import name_space_events


@name_space_events.route('/')
class EventsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ApiEvent)


@name_space_events.route('/<instance_id>')
class EventResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ApiEvent)
