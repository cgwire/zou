from zou.app.models.event import ApiEvent

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class EventsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ApiEvent)

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        return self.model.serialize_list(
            query.limit(1000).all(), relations=relations
        )


class EventResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ApiEvent)
