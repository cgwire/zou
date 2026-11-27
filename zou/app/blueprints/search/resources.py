from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.blueprints.search.schemas import SearchSchema
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    index_service,
    permissions_service,
    projects_service,
    user_service,
)
from zou.app.utils import permissions, validation
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class SearchResource(MethodView, ArgsMixin):
    def scope_to_vendor(self, entity_type, entities):
        """
        Limit a search result to the data that a vendor can read. Keep the
        entities that they have a task on, and remove the metadata that
        only other departments can read.

        The listings apply these two rules already. The index does not know
        them, so it gives the whole production to all users who can access
        the project.
        """
        return permissions_service.mask_metadata_for_vendor(
            entity_type,
            permissions_service.keep_entities_a_vendor_reaches(entities),
        )

    @jwt_required()
    @swag_from(SPECS["SearchResource_post"])
    def post(self):
        """
        Search entities
        """
        body = validation.validate_request_body(SearchSchema)
        query = body.query
        limit = body.limit
        offset = body.offset
        project_id = str(body.project_id) if body.project_id else None
        index_names = body.index_names
        results = {}
        if len(query) < 3:
            return results

        if permissions.has_admin_permissions():
            project_ids = projects_service.open_project_ids()
        else:
            project_ids = user_service.get_open_project_ids()

        if project_id is not None and len(project_id) > 0:
            if project_id in project_ids:
                project_ids = [project_id]
            else:
                project_ids = []

        if "persons" in index_names:
            if permissions.has_client_permissions():
                # The index cannot limit the persons to the teams that a
                # client meets, and the context of the client already
                # holds those persons.
                results["persons"] = []
            else:
                results["persons"] = index_service.search_persons(
                    query,
                    limit=limit,
                    offset=offset,
                    minimal=not permissions.has_admin_permissions(),
                )
        if "assets" in index_names:
            if (
                len(project_ids) == 0
                and not permissions.has_admin_permissions()
            ):
                results["assets"] = []
            else:
                results["assets"] = self.scope_to_vendor(
                    "Asset",
                    index_service.search_assets(
                        query, project_ids, limit=limit, offset=offset
                    ),
                )
        if "shots" in index_names:
            if (
                len(project_ids) == 0
                and not permissions.has_admin_permissions()
            ):
                results["shots"] = []
            else:
                results["shots"] = self.scope_to_vendor(
                    "Shot",
                    index_service.search_shots(
                        query, project_ids, limit=limit, offset=offset
                    ),
                )

        return results
