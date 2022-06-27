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
from zou.app import name_space_projects


@name_space_projects.route('/open')
class OpenProjectsResource(Resource):

    @jwt_required
    def get(self):
        """
        Return the list of projects currently running. Most of the time, past
        projects are not needed.
        """
        name = request.args.get("name", None)
        try:
            permissions.check_admin_permissions()
            for_client = permissions.has_client_permissions()
            return projects_service.open_projects(
                name=name, for_client=for_client
            )
        except permissions.PermissionDenied:
            return user_service.get_open_projects(name=name)


@name_space_projects.route('/all')
class AllProjectsResource(Resource):

    @jwt_required
    def get(self):
        """
        Return all projects listed in database. Ensure that user has at least
        the manager level before that.
        """
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


@name_space_projects.route('/<project_id>/team')
class ProductionTeamResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, project_id):
        """
        Allow to manage the people listed in a production team.
        """
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


@name_space_projects.route('/<project_id>/team/<person_id>')
class ProductionTeamRemoveResource(Resource):

    @jwt_required
    def delete(self, project_id, person_id):
        """
        Allow to remove people listed in a production team.
        """
        user_service.check_manager_project_access(project_id)
        projects_service.remove_team_member(project_id, person_id)
        return "", 204


@name_space_projects.route('/<project_id>/settings/asset-types')
class ProductionAssetTypeResource(Resource, ArgsMixin):

    @jwt_required
    def post(self, project_id):
        """
        Allow to add an asset type linked to a production.
        """
        args = self.get_args([("asset_type_id", "", True)])
        user_service.check_manager_project_access(project_id)
        project = projects_service.add_asset_type_setting(
            project_id, args["asset_type_id"]
        )
        return project, 201


@name_space_projects.route('/<project_id>/settings/asset-types/<asset_type_id>')
class ProductionAssetTypeRemoveResource(Resource):

    @jwt_required
    def delete(self, project_id, asset_type_id):
        """
        Allow to remove an asset type linked to a production.
        """
        user_service.check_manager_project_access(project_id)
        projects_service.remove_asset_type_setting(project_id, asset_type_id)
        return "", 204


@name_space_projects.route('/<project_id>/task-types')
class ProductionTaskTypesResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, project_id):
        """
        Retrieve task types linked to the production
        """
        user_service.check_manager_project_access(project_id)
        return projects_service.get_project_task_types(project_id)


@name_space_projects.route('/<project_id>/settings/task-types')
class ProductionTaskTypeResource(Resource, ArgsMixin):

    @jwt_required
    def post(self, project_id):
        """
        Allow to add a task type linked to a production.
        """
        args = self.get_args(
            [("task_type_id", "", True), ("priority", None, False)]
        )
        user_service.check_manager_project_access(project_id)
        project = projects_service.add_task_type_setting(
            project_id, args["task_type_id"], args["priority"]
        )
        return project, 201


@name_space_projects.route('/<project_id>/settings/task-types/<task_type_id>')
class ProductionTaskTypeRemoveResource(Resource):

    @jwt_required
    def delete(self, project_id, task_type_id):
        """
        Allow to remove an task type linked to a production.
        """
        user_service.check_manager_project_access(project_id)
        projects_service.remove_task_type_setting(project_id, task_type_id)
        return "", 204


@name_space_projects.route('/<project_id>/settings/task-status')
class ProductionTaskStatusResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, project_id):
        user_service.check_project_access(project_id)
        return projects_service.get_project_task_statuses(project_id)

    @jwt_required
    def post(self, project_id):
        """
        Allow to add a task type linked to a production.
        """
        args = self.get_args([("task_status_id", "", True)])
        user_service.check_manager_project_access(project_id)
        project = projects_service.add_task_status_setting(
            project_id, args["task_status_id"]
        )
        return project, 201


@name_space_projects.route('/<project_id>/settings/task-status/<task_status_id>')
class ProductionTaskStatusRemoveResource(Resource):

    @jwt_required
    def delete(self, project_id, task_status_id):
        """
        Allow to remove an task status linked to a production.
        """
        user_service.check_manager_project_access(project_id)
        projects_service.remove_task_status_setting(project_id, task_status_id)
        return "", 204


@name_space_projects.route('/<project_id>/settings/status-automations')
class ProductionStatusAutomationResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, project_id):
        user_service.check_manager_project_access(project_id)
        return projects_service.get_project_status_automations(project_id)

    @jwt_required
    def post(self, project_id):
        """
        Allow to add a status automation linked to a production.
        """
        args = self.get_args([("status_automation_id", "", True)])
        user_service.check_manager_project_access(project_id)
        project = projects_service.add_status_automation_setting(
            project_id, args["status_automation_id"]
        )
        return project, 201


@name_space_projects.route('/<project_id>/settings/status-automations/<status_automation_id>')
class ProductionStatusAutomationRemoveResource(Resource):

    @jwt_required
    def delete(self, project_id, status_automation_id):
        """
        Allow to remove an status automation linked to a production.
        """
        user_service.check_manager_project_access(project_id)
        projects_service.remove_status_automation_setting(
            project_id, status_automation_id
        )
        return "", 204


@name_space_projects.route('/<project_id>/metadata-descriptors')
class ProductionMetadataDescriptorsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, project_id):
        """
        Resource to get metadata descriptors. 
        It serves to describe extra fields listed in the data attribute of entities.
        """
        user_service.check_manager_project_access(project_id)
        for_client = permissions.has_client_permissions()
        return projects_service.get_metadata_descriptors(
            project_id, for_client
        )

    @jwt_required
    def post(self, project_id):
        """
        Resource to create metadata descriptors. 
        It serves to describe extra fields listed in the data attribute of entities.
        """
        args = self.get_args(
            [
                ("entity_type", "Asset", False),
                ("name", "", True),
                ("for_client", "False", False),
                ("choices", [], False, "append"),
                ("departments", [], False, "append"),
            ]
        )

        user_service.check_all_departments_access(
            project_id, args["departments"]
        )

        args["for_client"] = args["for_client"] == "True"

        if args["entity_type"] not in ["Asset", "Shot", "Edit"]:
            raise WrongParameterException(
                "Wrong entity type. Please select Asset, Shot or Edit."
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
                args["departments"],
            ),
            201,
        )


@name_space_projects.route('/<project_id>/metadata-descriptors/<descriptor_id>')
class ProductionMetadataDescriptorResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, project_id, descriptor_id):
        """
        Resource to get a metadata descriptor. 
        Descriptors serve to describe extra fields listed in the data attribute of entities.
        """
        user_service.check_project_access(project_id)
        return projects_service.get_metadata_descriptor(descriptor_id)

    @jwt_required
    def put(self, project_id, descriptor_id):
        """
        Resource to update a metadata descriptor. 
        Descriptors serve to describe extra fields listed in the data attribute of entities.
        """
        args = self.get_args(
            [
                ("name", "", False),
                ("for_client", "False", False),
                ("choices", [], False, "append"),
                ("departments", [], False, "append"),
            ]
        )
        user_service.check_all_departments_access(
            project_id,
            projects_service.get_metadata_descriptor(descriptor_id)[
                "departments"
            ]
            + args["departments"],
        )

        if len(args["name"]) == 0:
            raise WrongParameterException("Name cannot be empty.")

        args["for_client"] = args["for_client"] == "True"

        return projects_service.update_metadata_descriptor(descriptor_id, args)

    @jwt_required
    def delete(self, project_id, descriptor_id):
        """
        Resource to delete a metadata descriptor. 
        Descriptors serve to describe extra fields listed in the data attribute of entities.
        """
        user_service.check_all_departments_access(
            project_id,
            projects_service.get_metadata_descriptor(descriptor_id)[
                "departments"
            ],
        )
        projects_service.remove_metadata_descriptor(descriptor_id)
        return "", 204


@name_space_projects.route('/<project_id>/time-spents')
class ProductionTimeSpentsResource(Resource):

    @jwt_required
    def get(self, project_id):
        """
        Resource to retrieve time spents for given production.
        """
        user_service.check_project_access(project_id)
        return tasks_service.get_time_spents_for_project(project_id)


@name_space_projects.route('/<project_id>/milestones')
class ProductionMilestonesResource(Resource):

    @jwt_required
    def get(self, project_id):
        """
        Resource to retrieve milestones for given production.
        """
        user_service.check_project_access(project_id)
        return schedule_service.get_milestones_for_project(project_id)


@name_space_projects.route('/<project_id>/schedule-items')
class ProductionScheduleItemsResource(Resource):

    @jwt_required
    def get(self, project_id):
        """
        Resource to retrieve schedule items for given production.
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_schedule_items(project_id)


@name_space_projects.route('/<project_id>/schedule-items/task-types')
class ProductionTaskTypeScheduleItemsResource(Resource):

    @jwt_required
    def get(self, project_id):
        """
        Resource to retrieve schedule items for given production.
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_task_types_schedule_items(project_id)


@name_space_projects.route('/<project_id>/schedule-items/<task_type_id>/asset-types')
class ProductionAssetTypesScheduleItemsResource(Resource):

    @jwt_required
    def get(self, project_id, task_type_id):
        """
        Resource to retrieve asset types schedule items for given task type.
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_asset_types_schedule_items(
            project_id, task_type_id
        )


@name_space_projects.route('/<project_id>/schedule-items/<task_type_id>/episodes')
class ProductionEpisodesScheduleItemsResource(Resource):

    @jwt_required
    def get(self, project_id, task_type_id):
        """
        Resource to retrieve asset types schedule items for given task type.
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_episodes_schedule_items(
            project_id, task_type_id
        )


@name_space_projects.route('/<project_id>/schedule-items/<task_type_id>/sequences')
class ProductionSequencesScheduleItemsResource(Resource):

    @jwt_required
    def get(self, project_id, task_type_id):
        """
        Resource to retrieve asset types schedule items for given task type.
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_sequences_schedule_items(
            project_id, task_type_id
        )
