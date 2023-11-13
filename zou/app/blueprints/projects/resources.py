from flask_restful import Resource
from flask_jwt_extended import jwt_required


from zou.app.mixin import ArgsMixin
from zou.app.services import (
    projects_service,
    schedule_service,
    tasks_service,
    user_service,
)
from zou.app.utils import permissions
from zou.app.services.exception import WrongParameterException


class OpenProjectsResource(Resource, ArgsMixin):
    """
    Return the list of projects currently running. Most of the time, past
    projects are not needed.
    """

    @jwt_required()
    def get(self):
        """
        Return the list of projects currently running.
        ---
        tags:
          - Projects
        description: Most of the time, past projects are not needed.
        responses:
            200:
              description: All running projects
        """
        name = self.get_text_parameter("name")
        if permissions.has_admin_permissions():
            return projects_service.open_projects(name)
        else:
            return user_service.get_open_projects(name)


class AllProjectsResource(Resource, ArgsMixin):
    """
    Return all projects listed in database. Ensure that user has at least
    the manager level before that.
    """

    @jwt_required()
    def get(self):
        """
        Return all projects listed in database.
        ---
        tags:
          - Projects
        description: Ensure that user has at least the manager level before that.
        responses:
            200:
              description: All projects listed in database
        """
        name = self.get_text_parameter("name")
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

    @jwt_required()
    def get(self, project_id):
        """
        Return the people listed in a production team.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: People listed in a production team
        """
        user_service.check_project_access(project_id)
        project = projects_service.get_project_raw(project_id)
        persons = []
        for person in project.team:
            if permissions.has_manager_permissions():
                persons.append(person.serialize_safe(relations=True))
            else:
                persons.append(person.present_minimal())
        return persons

    @jwt_required()
    def post(self, project_id):
        """
        Add a person to a production team.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: person_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Person added to the production team
        """
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

    @jwt_required()
    def delete(self, project_id, person_id):
        """
        Remove people listed in a production team.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: person_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Person removed from production team
        """
        user_service.check_manager_project_access(project_id)
        projects_service.remove_team_member(project_id, person_id)
        return "", 204


class ProductionAssetTypeResource(Resource, ArgsMixin):
    """
    Allow to add an asset type linked to a production.
    """

    @jwt_required()
    def post(self, project_id):
        """
        Add an asset type linked to a production.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: asset_type_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Asset type added to production
        """
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

    @jwt_required()
    def delete(self, project_id, asset_type_id):
        """
        Remove an asset type from a production.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: asset_type_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Asset type removed from production
        """
        user_service.check_manager_project_access(project_id)
        projects_service.remove_asset_type_setting(project_id, asset_type_id)
        return "", 204


class ProductionTaskTypesResource(Resource, ArgsMixin):
    """
    Retrieve task types linked to the production
    """

    @jwt_required()
    def get(self, project_id):
        """
        Retrieve task types linked to the production
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Task types linked to the production
        """
        user_service.check_project_access(project_id)
        return projects_service.get_project_task_types(project_id)


class ProductionTaskTypeResource(Resource, ArgsMixin):
    """
    Allow to add a task type linked to a production.
    """

    @jwt_required()
    def post(self, project_id):
        """
        Add a task type linked to a production.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: task_type_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: priority
            required: False
            type: string
            default: "None"
        responses:
            201:
              description: Asset type added to production
        """
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
    Allow to remove a task type linked to a production.
    """

    @jwt_required()
    def delete(self, project_id, task_type_id):
        """
        Remove a task type from a production.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Task type removed from production
        """
        user_service.check_manager_project_access(project_id)
        projects_service.remove_task_type_setting(project_id, task_type_id)
        return "", 204


class ProductionTaskStatusResource(Resource, ArgsMixin):
    """
    Allow to add a task type linked to a production.
    """

    @jwt_required()
    def get(self, project_id):
        """
        Return task statuses linked to a production
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Task statuses linked to production
        """
        user_service.check_project_access(project_id)
        return projects_service.get_project_task_statuses(project_id)

    @jwt_required()
    def post(self, project_id):
        """
        Add a task type linked to a production.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: task_status_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Task type added to production
        """
        args = self.get_args([("task_status_id", "", True)])

        user_service.check_manager_project_access(project_id)
        project = projects_service.add_task_status_setting(
            project_id, args["task_status_id"]
        )
        return project, 201


class ProductionTaskStatusRemoveResource(Resource):
    """
    Allow to remove a task status linked to a production.
    """

    @jwt_required()
    def delete(self, project_id, task_status_id):
        """
        Remove a task status from a production.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_status_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Task status removed from production
        """
        user_service.check_manager_project_access(project_id)
        projects_service.remove_task_status_setting(project_id, task_status_id)
        return "", 204


class ProductionStatusAutomationResource(Resource, ArgsMixin):
    """
    Allow to add a status automation linked to a production.
    """

    @jwt_required()
    def get(self, project_id):
        """
        Get a status automation linked to a production.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Status automation linked to production
        """
        user_service.check_manager_project_access(project_id)
        return projects_service.get_project_status_automations(project_id)

    @jwt_required()
    def post(self, project_id):
        """
        Add a status automation linked to a production.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: status_automation_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Status automation added to production
        """
        args = self.get_args([("status_automation_id", "", True)])

        user_service.check_manager_project_access(project_id)
        project = projects_service.add_status_automation_setting(
            project_id, args["status_automation_id"]
        )
        return project, 201


class ProductionStatusAutomationRemoveResource(Resource):
    """
    Allow to remove a status automation linked to a production.
    """

    @jwt_required()
    def delete(self, project_id, status_automation_id):
        """
        Remove a status automation from a production.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: status_automation_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Status automation removed from production
        """
        user_service.check_manager_project_access(project_id)
        projects_service.remove_status_automation_setting(
            project_id, status_automation_id
        )
        return "", 204


class ProductionPreviewBackgroundFileResource(Resource, ArgsMixin):
    """
    Allow to add a preview background file linked to a production.
    """

    @jwt_required()
    def get(self, project_id):
        """
        Return preview background files linked to a production
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Preview background files linked to production
        """
        user_service.check_project_access(project_id)
        return projects_service.get_project_preview_background_files(
            project_id
        )

    @jwt_required()
    def post(self, project_id):
        """
        Add a preview background file linked to a production.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: preview_background_file_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Preview background file added to production
        """
        args = self.get_args([("preview_background_file_id", "", True)])

        user_service.check_manager_project_access(project_id)
        project = projects_service.add_preview_background_file_setting(
            project_id, args["preview_background_file_id"]
        )
        return project, 201


class ProductionPreviewBackgroundFileRemoveResource(Resource):
    """
    Allow to remove a preview background file linked to a production.
    """

    @jwt_required()
    def delete(self, project_id, preview_background_file_id):
        """
        Remove a preview background file from a production.
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: preview_background_file_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Preview background file removed from production
        """
        user_service.check_manager_project_access(project_id)
        projects_service.remove_preview_background_file_setting(
            project_id, preview_background_file_id
        )
        return "", 204


class ProductionMetadataDescriptorsResource(Resource, ArgsMixin):
    """
    Resource to get and create metadata descriptors. It serves to describe
    extra fields listed in the data attribute of entities.
    """

    @jwt_required()
    def get(self, project_id):
        """
        Get all metadata descriptors
        ---
        description: It serves to describe extra fields listed in the data attribute of entities.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: All metadata descriptors
        """
        user_service.check_manager_project_access(project_id)
        for_client = permissions.has_client_permissions()
        return projects_service.get_metadata_descriptors(
            project_id, for_client
        )

    @jwt_required()
    def post(self, project_id):
        """
        Create a new metadata descriptor
        ---
        description: It serves to describe extra fields listed in the data attribute of entities.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Create a new metadata descriptor
        """
        args = self.get_args(
            [
                ("entity_type", "Asset", False),
                ("name", "", True),
                ("data_type", "string", True),
                ("for_client", "False", False),
                ("choices", [], False, str, "append"),
                ("departments", [], False, str, "append"),
            ]
        )

        user_service.check_all_departments_access(
            project_id, args["departments"]
        )

        args["for_client"] = args["for_client"] == "True"

        if args["entity_type"] not in [
            "Asset",
            "Shot",
            "Edit",
            "Episode",
            "Sequence",
        ]:
            raise WrongParameterException(
                "Wrong entity type. Please select Asset, Shot, Sequence, Episode or Edit."
            )

        if len(args["name"]) == 0:
            raise WrongParameterException("Name cannot be empty.")

        return (
            projects_service.add_metadata_descriptor(
                project_id,
                args["entity_type"],
                args["name"],
                args["data_type"],
                args["choices"],
                args["for_client"],
                args["departments"],
            ),
            201,
        )


class ProductionMetadataDescriptorResource(Resource, ArgsMixin):
    """
    Resource to get, update or delete a metadata descriptor. Descriptors serve
    to describe extra fields listed in the data attribute of entities.
    """

    @jwt_required()
    def get(self, project_id, descriptor_id):
        """
        Get a metadata descriptor.
        ---
        description: Descriptors serve to describe extra fields listed in the data attribute of entities.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: descriptor_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Metadata descriptor
        """
        user_service.check_project_access(project_id)
        return projects_service.get_metadata_descriptor(descriptor_id)

    @jwt_required()
    def put(self, project_id, descriptor_id):
        """
        Update a metadata descriptor.
        ---
        description: Descriptors serve to describe extra fields listed in the data attribute of entities.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: descriptor_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: name
            required: True
            type: string
            required: False
          - in: formData
            name: for_client
            required: True
            type: boolean
            default: False
            required: False
          - in: formData
            name: choices
            required: True
            type: array
            required: False
          - in: formData
            name: departments
            type: array
            required: False
        responses:
            200:
              description: Metadata descriptor updated
        """
        args = self.get_args(
            [
                ("name", "", False),
                ("for_client", "False", False),
                ("data_type", "string", True),
                ("choices", [], False, str, "append"),
                ("departments", [], False, str, "append"),
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

    @jwt_required()
    def delete(self, project_id, descriptor_id):
        """
        Delete a metadata descriptor.
        ---
        description: Descriptors serve to describe extra fields listed in the data attribute of entities.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: descriptor_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Metadata descriptor deleted
        """
        user_service.check_all_departments_access(
            project_id,
            projects_service.get_metadata_descriptor(descriptor_id)[
                "departments"
            ],
        )
        projects_service.remove_metadata_descriptor(descriptor_id)
        return "", 204


class ProductionTimeSpentsResource(Resource):
    """
    Resource to retrieve time spents for given production.
    """

    @jwt_required()
    def get(self, project_id):
        """
        Retrieve time spents for given production
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: All time spents of given production
        """
        user_service.check_project_access(project_id)
        return tasks_service.get_time_spents_for_project(project_id)


class ProductionMilestonesResource(Resource):
    """
    Resource to retrieve milestones for given production.
    """

    @jwt_required()
    def get(self, project_id):
        """
        Retrieve milestones for given production
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: All milestones of given production
        """
        user_service.check_project_access(project_id)
        return schedule_service.get_milestones_for_project(project_id)


class ProductionScheduleItemsResource(Resource):
    """
    Resource to retrieve schedule items for given production.
    """

    @jwt_required()
    def get(self, project_id):
        """
        Retrieve schedule items for given production
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: All schedule items of given production
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_schedule_items(project_id)


class ProductionTaskTypeScheduleItemsResource(Resource):
    """
    Resource to retrieve schedule items for given production.
    """

    @jwt_required()
    def get(self, project_id):
        """
        Retrieve task type schedule items for given production
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: All task types schedule items of given production
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_task_types_schedule_items(project_id)


class ProductionAssetTypesScheduleItemsResource(Resource):
    """
    Resource to retrieve asset types schedule items for given task type.
    """

    @jwt_required()
    def get(self, project_id, task_type_id):
        """
        Retrieve asset types schedule items for given task type
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: All asset types schedule items for given task type
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_asset_types_schedule_items(
            project_id, task_type_id
        )


class ProductionEpisodesScheduleItemsResource(Resource):
    """
    Resource to retrieve episodes schedule items for given task type.
    """

    @jwt_required()
    def get(self, project_id, task_type_id):
        """
        Retrieve episodes schedule items for given task type
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: All episodes schedule items for given task type
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_episodes_schedule_items(
            project_id, task_type_id
        )


class ProductionSequencesScheduleItemsResource(Resource):
    """
    Resource to retrieve sequences schedule items for given task type.
    """

    @jwt_required()
    def get(self, project_id, task_type_id):
        """
        Retrieve sequences schedule items for given task type
        ---
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: All sequences schedule items for given task type
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_sequences_schedule_items(
            project_id, task_type_id
        )
