from flask_restful import Resource
from flask_jwt_extended import jwt_required

from flask import request

from zou.app.mixin import ArgsMixin
from zou.app.services import (
    projects_service,
    schedule_service,
    tasks_service,
    user_service,
)
from zou.app.utils import permissions
from zou.app.services.exception import WrongParameterException


class OpenProjectsResource(Resource):
    """
    Return the list of projects currently running. Most of the time, past
    projects are not needed.
    """

    @jwt_required
    def get(self):
        name = request.args.get("name", None)
        try:
            permissions.check_admin_permissions()
            for_client = permissions.has_client_permissions()
            return projects_service.open_projects(
                name=name, for_client=for_client
            )
        except permissions.PermissionDenied:
            return user_service.get_open_projects(name=name)


class AllProjectsResource(Resource):
    """
    Return all projects listed in database. Ensure that user has at least
    the manager level before that.
    """

    @jwt_required
    def get(self):
        name = request.args.get("name", None)
        try:
            permissions.check_admin_permissions()

            if name is None:
                return projects_service.get_projects()
            else:
                return [projects_service.get_project_by_name(name)]
        except permissions.PermissionDenied:
            if name is None:
                return user_service.get_projects()
            else:
                return [user_service.get_project_by_name(name)]


class ProductionTeamResource(Resource, ArgsMixin):
    """
    Allow to manage the people listed in a production team.
    """

    @jwt_required
    def get(self, project_id):
        user_service.check_project_access(project_id)
        project = projects_service.get_project_raw(project_id)
        persons = []
        for person in project.team:
            if permissions.has_manager_permissions:
                persons.append(person.serialize_safe())
            else:
                persons.append(person.present_minimal())
        return persons

    @jwt_required
    def post(self, project_id):
        args = self.get_args([("person_id", "", True)])
        user_service.check_manager_project_access(project_id)
        return (
            projects_service.add_team_member(project_id, args["person_id"]),
            201,
        )


class ProductionTeamRemoveResource(Resource):
    """
    Allow to remove people listed in a production team.
    """

    @jwt_required
    def delete(self, project_id, person_id):
        user_service.check_manager_project_access(project_id)
        projects_service.remove_team_member(project_id, person_id)
        return "", 204


class ProductionAssetTypeResource(Resource, ArgsMixin):
    """
    Allow to add an asset type linked to a production.
    """

    @jwt_required
    def post(self, project_id):
        args = self.get_args([("asset_type_id", "", True)])
        user_service.check_manager_project_access(project_id)
        project = projects_service.add_asset_type_setting(
            project_id, args["asset_type_id"]
        )
        return project, 201


class ProductionAssetTypeRemoveResource(Resource):
    """
    Allow to remove an asset type linked to a production.
    """

    @jwt_required
    def delete(self, project_id, asset_type_id):
        user_service.check_manager_project_access(project_id)
        projects_service.remove_asset_type_setting(project_id, asset_type_id)
        return "", 204


class ProductionTaskTypesResource(Resource, ArgsMixin):
    """
    Retrieve task types linked to the production
    """

    @jwt_required
    def get(self, project_id):
        user_service.check_manager_project_access(project_id)
        return projects_service.get_project_task_types(project_id)


class ProductionTaskTypeResource(Resource, ArgsMixin):
    """
    Allow to add a task type linked to a production.
    """

    @jwt_required
    def post(self, project_id):
        args = self.get_args(
            [("task_type_id", "", True), ("priority", None, False)]
        )
        user_service.check_manager_project_access(project_id)
        project = projects_service.add_task_type_setting(
            project_id, args["task_type_id"], args["priority"]
        )
        return project, 201


class ProductionTaskTypeRemoveResource(Resource):
    """
    Allow to remove an task type linked to a production.
    """

    @jwt_required
    def delete(self, project_id, task_type_id):
        user_service.check_manager_project_access(project_id)
        projects_service.remove_task_type_setting(project_id, task_type_id)
        return "", 204


class ProductionTaskStatusResource(Resource, ArgsMixin):
    """
    Allow to add an task type linked to a production.
    """

    @jwt_required
    def post(self, project_id):
        args = self.get_args([("task_status_id", "", True)])
        project = projects_service.add_task_status_setting(
            project_id, args["task_status_id"]
        )
        return project, 201


class ProductionTaskStatusRemoveResource(Resource):
    """
    Allow to remove an task status linked to a production.
    """

    @jwt_required
    def delete(self, project_id, task_status_id):
        user_service.check_manager_project_access(project_id)
        projects_service.remove_task_status_setting(project_id, task_status_id)
        return "", 204


class ProductionMetadataDescriptorsResource(Resource, ArgsMixin):
    """
    Resource to get and create metadata descriptors. It serves to describe
    extra fields listed in the data attribute of entities.
    """

    @jwt_required
    def get(self, project_id):
        user_service.check_manager_project_access(project_id)
        for_client = permissions.has_client_permissions()
        return projects_service.get_metadata_descriptors(
            project_id, for_client
        )

    @jwt_required
    def post(self, project_id):
        args = self.get_args(
            [
                ("entity_type", "Asset", False),
                ("name", "", True),
                ("for_client", "False", False),
                ("choices", [], False, "append"),
            ]
        )
        permissions.check_admin_permissions()

        args["for_client"] = args["for_client"] == "True"

        if args["entity_type"] not in ["Asset", "Shot"]:
            raise WrongParameterException(
                "Wrong entity type. Please select Asset or Shot."
            )

        if len(args["name"]) == 0:
            raise WrongParameterException("Name cannot be empty.")

        return (
            projects_service.add_metadata_descriptor(
                project_id,
                args["entity_type"],
                args["name"],
                args["choices"],
                args["for_client"],
            ),
            201,
        )


class ProductionMetadataDescriptorResource(Resource, ArgsMixin):
    """
    Resource to get, update or delete a metadata descriptor. Descriptors serve
    to describe extra fields listed in the data attribute of entities.
    """

    @jwt_required
    def get(self, project_id, descriptor_id):
        user_service.check_project_access(project_id)
        return projects_service.get_metadata_descriptor(descriptor_id)

    @jwt_required
    def put(self, project_id, descriptor_id):
        args = self.get_args(
            [
                ("name", "", False),
                ("for_client", "False", False),
                ("choices", [], False, "append"),
            ]
        )
        permissions.check_admin_permissions()

        if len(args["name"]) == 0:
            raise WrongParameterException("Name cannot be empty.")

        args["for_client"] = args["for_client"] == "True"

        return projects_service.update_metadata_descriptor(descriptor_id, args)

    @jwt_required
    def delete(self, project_id, descriptor_id):
        permissions.check_admin_permissions()
        projects_service.remove_metadata_descriptor(descriptor_id)
        return "", 204


class ProductionTimeSpentsResource(Resource):
    """
    Resource to retrieve time spents for given production.
    """

    @jwt_required
    def get(self, project_id):
        user_service.check_project_access(project_id)
        return tasks_service.get_time_spents_for_project(project_id)


class ProductionMilestonesResource(Resource):
    """
    Resource to retrieve milestones for given production.
    """

    @jwt_required
    def get(self, project_id):
        user_service.check_project_access(project_id)
        return schedule_service.get_milestones_for_project(project_id)


class ProductionScheduleItemsResource(Resource):
    """
    Resource to retrieve schedule items for given production.
    """

    @jwt_required
    def get(self, project_id):
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_schedule_items(project_id)


class ProductionTaskTypeScheduleItemsResource(Resource):
    """
    Resource to retrieve schedule items for given production.
    """

    @jwt_required
    def get(self, project_id):
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_task_types_schedule_items(project_id)


class ProductionAssetTypesScheduleItemsResource(Resource):
    """
    Resource to retrieve asset types schedule items for given task type.
    """

    @jwt_required
    def get(self, project_id, task_type_id):
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_asset_types_schedule_items(
            project_id, task_type_id
        )


class ProductionEpisodesScheduleItemsResource(Resource):
    """
    Resource to retrieve asset types schedule items for given task type.
    """

    @jwt_required
    def get(self, project_id, task_type_id):
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_episodes_schedule_items(
            project_id, task_type_id
        )


class ProductionSequencesScheduleItemsResource(Resource):
    """
    Resource to retrieve asset types schedule items for given task type.
    """

    @jwt_required
    def get(self, project_id, task_type_id):
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_sequences_schedule_items(
            project_id, task_type_id
        )
