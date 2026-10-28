from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.milestone import Milestone
from zou.app.services import permissions_service, user_service
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/milestone.yml")


class MilestonesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Milestone)

    def check_create_permissions(self, milestone):
        permissions_service.check_manager_project_access(
            milestone["project_id"]
        )

    @jwt_required()
    @swag_from(SPECS["MilestonesResource_get"])
    def get(self):
        """
        Get milestones
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["MilestonesResource_post"])
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
    @swag_from(SPECS["MilestoneResource_get"])
    def get(self, instance_id):
        """
        Get milestone
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["MilestoneResource_put"])
    def put(self, instance_id):
        """
        Update milestone
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["MilestoneResource_delete"])
    def delete(self, instance_id):
        """
        Delete milestone
        """
        return super().delete(instance_id)

    def check_update_permissions(self, milestone, data):
        return permissions_service.check_manager_project_access(
            milestone["project_id"]
        )

    def check_delete_permissions(self, milestone):
        return permissions_service.check_manager_project_access(
            milestone["project_id"]
        )
