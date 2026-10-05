from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.event import ApiEvent

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class EventsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ApiEvent)

    @jwt_required()
    @swag_from("openapi/EventsResource_get.yml")
    def get(self):
        """
        Get events
        """
        self.is_paginated = self.get_page() > -1
        return super().get()

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        # The cap only applies to the unpaginated listing: paginated_entries
        # has already set the page limit and a second .limit() would
        # replace it, returning up to 1000 rows for a page of 50.
        if not getattr(self, "is_paginated", False):
            query = query.limit(1000)
        return self.serialize_list(query.all(), relations=relations)


class EventResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ApiEvent)

    @jwt_required()
    @swag_from("openapi/EventResource_get.yml")
    def get(self, instance_id):
        """
        Get event
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/EventResource_put.yml")
    def put(self, instance_id):
        """
        Update event
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/EventResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete event
        """
        return super().delete(instance_id)
