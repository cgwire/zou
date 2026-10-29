from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.blueprints.untracked.schemas import (
    NewUntrackedSchema,
    UpdateUntrackedSchema,
)
from zou.app.services import (
    permissions_service,
    persons_service,
    projects_service,
    untracked_service,
)
from zou.app.utils import permissions, validation
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


def check_untracked_read_access(project_id):
    """
    Untracked items are planning data: everyone in the project reads them,
    except the vendors and the clients.
    """
    permissions_service.check_project_access(project_id)
    if (
        permissions.has_vendor_permissions()
        or permissions.has_client_permissions()
    ):
        raise permissions.PermissionDenied


class ProjectUntrackedResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["ProjectUntrackedResource_get"])
    def get(self, project_id):
        """
        Get project untracked items
        """
        projects_service.get_project(project_id)
        check_untracked_read_access(project_id)
        return untracked_service.get_untracked_for_project(project_id)

    @jwt_required()
    @swag_from(SPECS["ProjectUntrackedResource_post"])
    def post(self, project_id):
        """
        Create untracked item
        """
        body = validation.validate_request_body(NewUntrackedSchema)
        projects_service.get_project(project_id)
        permissions_service.check_manager_project_access(project_id)
        untracked = untracked_service.create_untracked(
            project_id,
            body.name,
            description=body.description,
            parent_id=str(body.parent_id) if body.parent_id else None,
            created_by=persons_service.get_current_user()["id"],
        )
        if body.create_task:
            untracked["tasks"] = untracked_service.create_untracked_task(
                untracked,
                str(body.department_id) if body.department_id else None,
                body.color,
            )
        return untracked, 201


class UntrackedResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["UntrackedResource_get"])
    def get(self, untracked_id):
        """
        Get untracked item
        """
        untracked = untracked_service.get_untracked(untracked_id)
        check_untracked_read_access(untracked["project_id"])
        return untracked

    @jwt_required()
    @swag_from(SPECS["UntrackedResource_put"])
    def put(self, untracked_id):
        """
        Update untracked item
        """
        body = validation.validate_request_body(UpdateUntrackedSchema)
        untracked = untracked_service.get_untracked(untracked_id)
        permissions_service.check_manager_project_access(
            untracked["project_id"]
        )
        data = body.model_dump(exclude_unset=True)
        for key in ("name", "description"):
            if key in data and data[key] is None:
                del data[key]
        if data.get("parent_id") is not None:
            data["parent_id"] = str(data["parent_id"])
        return untracked_service.update_untracked(untracked_id, data)
