import re

from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import WrongParameterException
from zou.app.models.milestone import (
    MILESTONE_STATUSES,
    MILESTONE_TYPES,
    Milestone,
)
from zou.app.services import permissions_service, user_service

HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
MILESTONE_TYPE_CODES = [code for code, _ in MILESTONE_TYPES]
MILESTONE_STATUS_CODES = [code for code, _ in MILESTONE_STATUSES]


def check_milestone_fields(data):
    """
    Reject a color that is not #RRGGBB and a type or status outside the
    allowed choices. ChoiceType would store an unknown code and fail only
    when the row is read back.
    """
    color = data.get("color")
    if color is not None and (
        not isinstance(color, str) or not HEX_COLOR_RE.fullmatch(color)
    ):
        raise WrongParameterException(
            "Color must be a hex string formatted as #RRGGBB."
        )
    if "milestone_type" in data and (
        data["milestone_type"] not in MILESTONE_TYPE_CODES
    ):
        raise WrongParameterException(
            "Milestone type must be one of: "
            f"{', '.join(MILESTONE_TYPE_CODES)}."
        )
    if "status" in data and data["status"] not in MILESTONE_STATUS_CODES:
        raise WrongParameterException(
            "Milestone status must be one of: "
            f"{', '.join(MILESTONE_STATUS_CODES)}."
        )
    return data


class MilestonesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Milestone)

    def check_create_permissions(self, milestone):
        permissions_service.check_manager_project_access(
            milestone["project_id"]
        )

    def check_creation_integrity(self, data):
        return check_milestone_fields(data)

    @jwt_required()
    @swag_from("openapi/MilestonesResource_get.yml")
    def get(self):
        """
        Get milestones
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/MilestonesResource_post.yml")
    def post(self):
        """
        Create milestone
        """
        return super().post()


class MilestoneResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Milestone)

    def check_read_permissions(self, milestone):
        permissions_service.check_project_access(milestone["project_id"])
        permissions_service.block_access_to_vendor()

    @jwt_required()
    @swag_from("openapi/MilestoneResource_get.yml")
    def get(self, instance_id):
        """
        Get milestone
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/MilestoneResource_put.yml")
    def put(self, instance_id):
        """
        Update milestone
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/MilestoneResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete milestone
        """
        return super().delete(instance_id)

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        return check_milestone_fields(data)

    def check_update_permissions(self, milestone, data):
        return permissions_service.check_manager_project_access(
            milestone["project_id"]
        )

    def check_delete_permissions(self, milestone):
        return permissions_service.check_manager_project_access(
            milestone["project_id"]
        )
