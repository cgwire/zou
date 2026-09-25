from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.milestone import Milestone
from zou.app.services import permissions_service
from zou.app.services import user_service

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class MilestonesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Milestone)

    def check_create_permissions(self, milestone):
        permissions_service.check_manager_project_access(
            milestone["project_id"]
        )

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

    def check_update_permissions(self, milestone, data):
        return permissions_service.check_manager_project_access(
            milestone["project_id"]
        )

    def check_delete_permissions(self, milestone):
        return permissions_service.check_manager_project_access(
            milestone["project_id"]
        )
