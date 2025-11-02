from flask import abort
from flask_restful import Resource
from flask_jwt_extended import jwt_required


from zou.app.services import budget_service
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    persons_service,
    projects_service,
    schedule_service,
    tasks_service,
    time_spents_service,
    user_service,
)
from zou.app.utils import permissions
from zou.app.services.exception import (
    WrongParameterException,
    WrongDateFormatException,
)
from zou.app.models.metadata_descriptor import METADATA_DESCRIPTOR_TYPES


class OpenProjectsResource(Resource, ArgsMixin):
    """
    Return the list of projects currently running. Most of the time, past
    projects are not needed.
    """

    @jwt_required()
    def get(self):
        """
        Get open projects
        ---
        description: Return the list of projects currently running. Most of the
          time, past projects are not needed.
        tags:
          - Projects
        parameters:
          - in: query
            name: name
            required: false
            schema:
              type: string
            description: Filter projects by name
            example: "My Project"
        responses:
          200:
            description: All running projects
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Project unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Project name
                        example: "My Project"
                      project_status_id:
                        type: string
                        format: uuid
                        description: Project status unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
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
        Get all projects
        ---
        description: Return all projects listed in database. Ensure that user has
          at least the manager level before that.
        tags:
          - Projects
        parameters:
          - in: query
            name: name
            required: false
            schema:
              type: string
            description: Filter projects by name
            example: "My Project"
        responses:
          200:
            description: All projects listed in database
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Project unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Project name
                        example: "My Project"
                      project_status_id:
                        type: string
                        format: uuid
                        description: Project status unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
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
        Get production team
        ---
        description: Return the people listed in a production team.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: People listed in a production team
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Person unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      first_name:
                        type: string
                        description: Person first name
                        example: "John"
                      last_name:
                        type: string
                        description: Person last name
                        example: "Doe"
                      email:
                        type: string
                        description: Person email address
                        example: "john.doe@example.com"
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
        Add person to production team
        ---
        description: Add a person to a production team.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - person_id
                properties:
                  person_id:
                    type: string
                    format: uuid
                    description: Person unique identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          201:
            description: Person added to the production team
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Project unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Project name
                      example: "My Project"
          400:
            description: Invalid parameters
        """
        args = self.get_args([("person_id", "", True)])

        user_service.check_manager_project_access(project_id)
        return (
            projects_service.add_team_member(project_id, args["person_id"]),
            201,
        )


class ProductionTeamRemoveResource(Resource):

    @jwt_required()
    def delete(self, project_id, person_id):
        """
        Remove person from production team
        ---
        description: Remove people listed in a production team.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: person_id
            required: true
            schema:
              type: string
              format: uuid
            description: Person unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
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
        Add asset type to production
        ---
        description: Add an asset type linked to a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - asset_type_id
                properties:
                  asset_type_id:
                    type: string
                    format: uuid
                    description: Asset type unique identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          201:
            description: Asset type added to production
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Project unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Project name
                      example: "My Project"
          400:
            description: Invalid parameters
        """
        args = self.get_args([("asset_type_id", "", True)])

        user_service.check_manager_project_access(project_id)
        project = projects_service.add_asset_type_setting(
            project_id, args["asset_type_id"]
        )
        return project, 201


class ProductionAssetTypeRemoveResource(Resource):

    @jwt_required()
    def delete(self, project_id, asset_type_id):
        """
        Remove asset type from production
        ---
        description: Remove an asset type from a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: asset_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Asset type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
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
        Get production task types
        ---
        description: Retrieve task types linked to the production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Task types linked to the production
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
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
        Add task type to production
        ---
        description: Add a task type linked to a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - task_type_id
                properties:
                  task_type_id:
                    type: string
                    format: uuid
                    description: Task type unique identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
                  priority:
                    type: string
                    description: Task type priority
                    example: "None"
        responses:
          201:
            description: Task type added to production
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Project unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Project name
                      example: "My Project"
          400:
            description: Invalid parameters
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
        Remove task type from production
        ---
        description: Remove a task type from a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
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
        Get production task statuses
        ---
        description: Return task statuses linked to a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Task statuses linked to production
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
        """
        user_service.check_project_access(project_id)
        return projects_service.get_project_task_statuses(project_id)

    @jwt_required()
    def post(self, project_id):
        """
        Add task status to production
        ---
        description: Add a task status linked to a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - task_status_id
                properties:
                  task_status_id:
                    type: string
                    format: uuid
                    description: Task status unique identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          201:
            description: Task status added to production
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Project unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Project name
                      example: "My Project"
          400:
            description: Invalid parameters
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
        Remove task status from production
        ---
        description: Remove a task status from a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_status_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task status unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
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
        Get production status automations
        ---
        description: Get status automations linked to a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Status automations linked to production
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
        """
        user_service.check_manager_project_access(project_id)
        return projects_service.get_project_status_automations(project_id)

    @jwt_required()
    def post(self, project_id):
        """
        Add status automation to production
        ---
        description: Add a status automation linked to a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - status_automation_id
                properties:
                  status_automation_id:
                    type: string
                    format: uuid
                    description: Status automation unique identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          201:
            description: Status automation added to production
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Project unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Project name
                      example: "My Project"
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
        Remove status automation from production
        ---
        description: Remove a status automation from a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: status_automation_id
            required: true
            schema:
              type: string
              format: uuid
            description: Status automation unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
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
        Get production preview background files
        ---
        description: Return preview background files linked to a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Preview background files linked to production
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
        """
        user_service.check_project_access(project_id)
        return projects_service.get_project_preview_background_files(
            project_id
        )

    @jwt_required()
    def post(self, project_id):
        """
        Add preview background file to production
        ---
        description: Add a preview background file linked to a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - preview_background_file_id
                properties:
                  preview_background_file_id:
                    type: string
                    format: uuid
                    description: Preview background file unique identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          201:
            description: Preview background file added to production
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Project unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Project name
                      example: "My Project"
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
        Remove preview background file from production
        ---
        description: Remove a preview background file from a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: preview_background_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview background file unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
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
        Get metadata descriptors
        ---
        description: Get all metadata descriptors. It serves to describe extra
          fields listed in the data attribute of entities.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: All metadata descriptors
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
        """
        user_service.check_project_access(project_id)
        for_client = permissions.has_client_permissions()
        return projects_service.get_metadata_descriptors(
            project_id, for_client
        )

    @jwt_required()
    def post(self, project_id):
        """
        Create metadata descriptor
        ---
        description: Create a new metadata descriptor. It serves to describe
          extra fields listed in the data attribute of entities.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - data_type
                properties:
                  entity_type:
                    type: string
                    description: Entity type for the metadata descriptor
                    enum: ["Asset", "Shot", "Edit", "Episode", "Sequence"]
                    default: "Asset"
                    example: "Asset"
                  name:
                    type: string
                    description: Name of the metadata descriptor
                    example: "Custom Field"
                  data_type:
                    type: string
                    description: Type of data (string, number, boolean, etc.)
                    example: "string"
                  for_client:
                    type: string
                    description: Whether the descriptor is for client
                    default: "False"
                    example: "True"
                  choices:
                    type: array
                    description: List of choices for the descriptor
                    items:
                      type: string
                    example: ["option1", "option2"]
                  departments:
                    type: array
                    description: List of departments for the descriptor
                    items:
                      type: string
                    example: ["department1", "department2"]
        responses:
          201:
            description: Metadata descriptor created
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Metadata descriptor unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Metadata descriptor name
                      example: "Custom Field"
                    data_type:
                      type: string
                      description: Metadata descriptor data type
                      example: "string"
          400:
            description: Invalid parameters
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

        types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
        if args["data_type"] not in types:
            raise WrongParameterException("Invalid data_type")

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
        Get metadata descriptor
        ---
        description: Get a metadata descriptor. Descriptors serve to describe
          extra fields listed in the data attribute of entities.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: descriptor_id
            required: true
            schema:
              type: string
              format: uuid
            description: Metadata descriptor unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: Metadata descriptor
            content:
              application/json:
                schema:
                  type: object
        """
        user_service.check_project_access(project_id)
        return projects_service.get_metadata_descriptor(descriptor_id)

    @jwt_required()
    def put(self, project_id, descriptor_id):
        """
        Update metadata descriptor
        ---
        description: Update a metadata descriptor. Descriptors serve to
          describe extra fields listed in the data attribute of entities.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: descriptor_id
            required: true
            schema:
              type: string
              format: uuid
            description: Metadata descriptor unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    description: Name of the metadata descriptor
                    example: "Custom Field"
                  for_client:
                    type: string
                    description: Whether the descriptor is for client
                    default: "False"
                    example: "True"
                  choices:
                    type: array
                    description: List of choices for the descriptor
                    items:
                      type: string
                    example: ["option1", "option2"]
                  departments:
                    type: array
                    description: List of departments for the descriptor
                    items:
                      type: string
                    example: ["department1", "department2"]
        responses:
          200:
            description: Metadata descriptor updated
            content:
              application/json:
                schema:
                  type: object
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

        types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
        if args["data_type"] not in types:
            raise WrongParameterException("Invalid data_type")

        args["for_client"] = args["for_client"] == "True"

        return projects_service.update_metadata_descriptor(descriptor_id, args)

    @jwt_required()
    def delete(self, project_id, descriptor_id):
        """
        Delete metadata descriptor
        ---
        description: Delete a metadata descriptor. Descriptors serve to describe
          extra fields listed in the data attribute of entities.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: descriptor_id
            required: true
            schema:
              type: string
              format: uuid
            description: Metadata descriptor unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
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


class ProductionMetadataDescriptorsReorderResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, project_id):
        """
        Reorder metadata descriptors
        ---
        description: Reorder metadata descriptors for a specific entity type
          and project. Descriptors are reordered based on the list of
          descriptor IDs provided in the request body. Position is set
          according to the order in the list.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - entity_type
                  - descriptor_ids
                properties:
                  entity_type:
                    type: string
                    description: Entity type for the metadata descriptors
                    enum: ["Asset", "Shot", "Edit", "Episode", "Sequence"]
                    example: "Asset"
                  descriptor_ids:
                    type: array
                    description: List of metadata descriptor IDs in the
                      desired order
                    items:
                      type: string
                      format: uuid
                    example: ["b35b7fb5-df86-5776-b181-68564193d36", "c46c8gc6-eg97-6887-c292-79675204e47"]
        responses:
          200:
            description: Metadata descriptors reordered successfully
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Metadata descriptor unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Metadata descriptor name
                        example: "Custom Field"
                      position:
                        type: integer
                        description: Position of the descriptor
                        example: 1
                      entity_type:
                        type: string
                        description: Entity type
                        example: "Asset"
          400:
            description: Invalid parameters or descriptor not found
        """
        args = self.get_args(
            [
                ("entity_type", "", True),
                ("descriptor_ids", [], True, str, "append"),
            ]
        )

        user_service.check_manager_project_access(project_id)

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

        if not args["descriptor_ids"]:
            raise WrongParameterException("descriptor_ids cannot be empty.")

        return projects_service.reorder_metadata_descriptors(
            project_id, args["entity_type"], args["descriptor_ids"]
        )


class ProductionTimeSpentsResource(Resource):
    """
    Resource to retrieve time spents for given production.
    """

    @jwt_required()
    def get(self, project_id):
        """
        Get production time spents
        ---
        description: Retrieve time spents for given production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: All time spents of given production
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
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
        Get production milestones
        ---
        description: Retrieve milestones for given production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: All milestones of given production
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
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
        Get production schedule items
        ---
        description: Retrieve schedule items for given production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: All schedule items of given production
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
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
        Get production task type schedule items
        ---
        description: Retrieve task type schedule items for given production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: All task types schedule items of given production
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
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
        Get asset types schedule items
        ---
        description: Retrieve asset types schedule items for given task type.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: All asset types schedule items for given task type
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
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
        Get episodes schedule items
        ---
        description: Retrieve episodes schedule items for given task type.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: All episodes schedule items for given task type
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
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
        Get sequences schedule items
        ---
        description: Retrieve sequences schedule items for given task type.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: All sequences schedule items for given task type
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        return schedule_service.get_sequences_schedule_items(
            project_id, task_type_id
        )


class ProductionBudgetsResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id):
        """
        Get production budgets
        ---
        description: Retrieve budgets for given production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: All budgets of given production
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
        """
        user_service.check_manager_project_access(project_id)
        self.check_id_parameter(project_id)
        return budget_service.get_budgets(project_id)

    @jwt_required()
    def post(self, project_id):
        """
        Create budget
        ---
        description: Create a budget for given production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                properties:
                  name:
                    type: string
                    description: Budget name
                    example: "New Budget"
                  currency:
                    type: string
                    description: Budget currency code
                    default: "USD"
                    example: "USD"
        responses:
          201:
            description: Budget created
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Budget unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Budget name
                      example: "New Budget"
                    currency:
                      type: string
                      description: Budget currency code
                      example: "USD"
          400:
            description: Invalid parameters
        """
        self.check_id_parameter(project_id)
        user_service.check_manager_project_access(project_id)
        data = self.get_args([("name", None, True), ("currency", None, False)])
        if data["currency"] is None:
            data["currency"] = "USD"
        return budget_service.create_budget(
            project_id, data["name"], data["currency"]
        )


class ProductionBudgetResource(Resource, ArgsMixin):
    """
    Resource to retrieve a budget for given production.
    """

    @jwt_required()
    def get(self, project_id, budget_id):
        """
        Get budget
        ---
        description: Retrieve a budget for given production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: budget_id
            required: true
            schema:
              type: string
              format: uuid
            description: Budget unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: Budget retrieved
            content:
              application/json:
                schema:
                  type: object
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        user_service.check_manager_project_access(project_id)
        return budget_service.get_budget(budget_id)

    @jwt_required()
    def put(self, project_id, budget_id):
        """
        Update budget
        ---
        description: Update a budget for given production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: budget_id
            required: true
            schema:
              type: string
              format: uuid
            description: Budget unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    description: Budget name
                    example: "New Budget"
                  currency:
                    type: string
                    description: Budget currency code
                    example: "USD"
        responses:
          200:
            description: Budget updated
            content:
              application/json:
                schema:
                  type: object
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        user_service.check_manager_project_access(project_id)
        data = self.get_args(
            [("name", None, False), ("currency", None, False)]
        )
        return budget_service.update_budget(
            budget_id, name=data["name"], currency=data["currency"]
        )

    @jwt_required()
    def delete(self, project_id, budget_id):
        """
        Delete budget
        ---
        description: Delete a budget for given production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: budget_id
            required: true
            schema:
              type: string
              format: uuid
            description: Budget unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          204:
            description: Budget deleted
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        user_service.check_manager_project_access(project_id)
        budget_service.delete_budget(budget_id)
        return "", 204


class ProductionBudgetEntriesResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id, budget_id):
        """
        Get budget entries
        ---
        description: Retrieve budget entries for given production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: budget_id
            required: true
            schema:
              type: string
              format: uuid
            description: Budget unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: All budget entries of given production and budget
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        user_service.check_manager_project_access(project_id)
        return budget_service.get_budget_entries(budget_id)

    @jwt_required()
    def post(self, project_id, budget_id):
        """
        Create budget entry
        ---
        description: Create a budget entry for given production and budget.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: budget_id
            required: true
            schema:
              type: string
              format: uuid
            description: Budget unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - department_id
                properties:
                  department_id:
                    type: string
                    format: uuid
                    description: Department unique identifier
                    example: c46c8gc6-eg97-6887-c292-79675204e47
                  person_id:
                    type: string
                    format: uuid
                    description: Person unique identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  start_date:
                    type: string
                    format: date
                    description: Budget entry start date
                    example: "2025-01-01"
                  months_duration:
                    type: integer
                    description: Budget entry duration in months
                    example: 12
                  daily_salary:
                    type: number
                    format: float
                    description: Daily salary amount
                    example: 100.00
                  position:
                    type: string
                    description: Position name
                    example: "Artist"
                  seniority:
                    type: string
                    description: Seniority level
                    example: "Mid"
        responses:
          201:
            description: Budget entry created
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Budget entry unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    department_id:
                      type: string
                      format: uuid
                      description: Department unique identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
          400:
            description: Invalid parameters
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        user_service.check_manager_project_access(project_id)
        data = self.get_args(
            [
                ("department_id", None, True),
                ("person_id", None, False),
                ("start_date", None, False),
                ("months_duration", None, False),
                ("daily_salary", None, False),
                ("position", None, False),
                ("seniority", None, False),
            ]
        )
        return budget_service.create_budget_entry(
            budget_id,
            data["department_id"],
            data["start_date"],
            data["months_duration"],
            data["daily_salary"],
            data["position"],
            data["seniority"],
            person_id=data["person_id"],
        )


class ProductionBudgetEntryResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id, budget_id, entry_id):
        """
        Get budget entry
        ---
        description: Retrieve a budget entry for given production and budget.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: budget_id
            required: true
            schema:
              type: string
              format: uuid
            description: Budget unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: path
            name: entry_id
            required: true
            schema:
              type: string
              format: uuid
            description: Budget entry unique identifier
            example: c46c8gc6-eg97-6887-c292-79675204e47
        responses:
          200:
            description: Budget entry retrieved
            content:
              application/json:
                schema:
                  type: object
        """
        user_service.check_manager_project_access(project_id)
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        self.check_id_parameter(entry_id)
        return budget_service.get_budget_entry(entry_id)

    @jwt_required()
    def put(self, project_id, budget_id, entry_id):
        """
        Update budget entry
        ---
        description: Update a budget entry for given production and budget.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: budget_id
            required: true
            schema:
              type: string
              format: uuid
            description: Budget unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: path
            name: entry_id
            required: true
            schema:
              type: string
              format: uuid
            description: Budget entry unique identifier
            example: c46c8gc6-eg97-6887-c292-79675204e47
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  department_id:
                    type: string
                    format: uuid
                    description: Department unique identifier
                    example: c46c8gc6-eg97-6887-c292-79675204e47
                  person_id:
                    type: string
                    format: uuid
                    description: Person unique identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  start_date:
                    type: string
                    format: date
                    description: Budget entry start date
                    example: "2025-01-01"
                  months_duration:
                    type: integer
                    description: Budget entry duration in months
                    example: 12
                  daily_salary:
                    type: number
                    format: float
                    description: Daily salary amount
                    example: 100.00
                  position:
                    type: string
                    description: Position name
                    example: "Artist"
                  seniority:
                    type: string
                    description: Seniority level
                    example: "Mid"
                  exceptions:
                    type: object
                    description: Map of amount exceptions. Key is the date and
                      value is the amount
                    example: {"2025-01-01": 1000, "2025-02-01": 2000}
        responses:
          200:
            description: Budget entry updated
            content:
              application/json:
                schema:
                  type: object
        """
        user_service.check_manager_project_access(project_id)
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        self.check_id_parameter(entry_id)
        data = self.get_args(
            [
                ("department_id", None, False),
                ("person_id", None, False),
                ("start_date", None, False),
                ("months_duration", None, False),
                ("daily_salary", None, False),
                ("position", None, False),
                ("seniority", None, False),
                {
                    "name": "exceptions",
                    "required": False,
                    "default": {},
                    "type": dict,
                    "help": "Map of amount exceptions. Key is the date and value is the amount. Example: {'2025-01-01': 1000, '2025-02-01': 2000}",
                },
            ]
        )
        return budget_service.update_budget_entry(entry_id, data)

    @jwt_required()
    def delete(self, project_id, budget_id, entry_id):
        """
        Delete budget entry
        ---
        description: Delete a budget entry for given production and budget.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: budget_id
            required: true
            schema:
              type: string
              format: uuid
            description: Budget unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: path
            name: entry_id
            required: true
            schema:
              type: string
              format: uuid
            description: Budget entry unique identifier
            example: c46c8gc6-eg97-6887-c292-79675204e47
        responses:
          204:
            description: Budget entry deleted
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        self.check_id_parameter(entry_id)
        user_service.check_manager_project_access(project_id)
        budget_service.delete_budget_entry(entry_id)
        return "", 204


class ProductionMonthTimeSpentsResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id):
        """
        Get production month time spents
        ---
        description: Get aggregated time spents by month for given project.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Aggregated time spents for given project and month
            content:
              application/json:
                schema:
                  type: object
          400:
            description: Wrong ID format
        """
        permissions.check_admin_permissions()
        self.check_id_parameter(project_id)
        user = persons_service.get_current_user()
        return time_spents_service.get_project_month_time_spents(
            project_id, user["timezone"]
        )


class ProductionScheduleVersionTaskLinksResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, production_schedule_version_id):
        """
        Get production schedule version task links
        ---
        description: Get task links for given production schedule version.
        tags:
          - Projects
        parameters:
          - in: path
            name: production_schedule_version_id
            required: true
            schema:
              type: string
              format: uuid
            description: Production schedule version unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Task type unique identifier for filtering
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: Task links for given production schedule version
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
          400:
            description: Wrong ID format
        """
        production_schedule_version = (
            schedule_service.get_production_schedule_version(
                production_schedule_version_id
            )
        )
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        user_service.check_project_access(
            production_schedule_version["project_id"]
        )

        args = self.get_args(
            [
                ("task_type_id", None, False),
            ]
        )

        relations = self.get_relations()

        return schedule_service.get_production_schedule_version_task_links(
            production_schedule_version_id,
            task_type_id=args["task_type_id"],
            relations=relations,
        )


class ProductionScheduleVersionSetTaskLinksFromTasksResource(
    Resource, ArgsMixin
):

    @jwt_required()
    def post(self, production_schedule_version_id):
        """
        Set task links from tasks
        ---
        description: Set task links for given production schedule version from
          tasks.
        tags:
          - Projects
        parameters:
          - in: path
            name: production_schedule_version_id
            required: true
            schema:
              type: string
              format: uuid
            description: Production schedule version unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Task links created
            content:
              application/json:
                schema:
                  type: object
          400:
            description: Wrong ID format
        """
        production_schedule_version = (
            schedule_service.get_production_schedule_version(
                production_schedule_version_id
            )
        )
        user_service.check_manager_project_access(
            production_schedule_version["project_id"]
        )

        return schedule_service.set_production_schedule_version_task_links_from_production(
            production_schedule_version_id
        )


class ProductionScheduleVersionApplyToProductionResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, production_schedule_version_id):
        """
        Apply production schedule version
        ---
        description: Apply production schedule version to production.
        tags:
          - Projects
        parameters:
          - in: path
            name: production_schedule_version_id
            required: true
            schema:
              type: string
              format: uuid
            description: Production schedule version unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Production schedule version applied
            content:
              application/json:
                schema:
                  type: object
          400:
            description: Wrong ID format
        """
        production_schedule_version = (
            schedule_service.get_production_schedule_version(
                production_schedule_version_id
            )
        )
        user_service.check_manager_project_access(
            production_schedule_version["project_id"]
        )

        return (
            schedule_service.apply_production_schedule_version_to_production(
                production_schedule_version_id,
            )
        )


class ProductionScheduleVersionSetTaskLinksFromProductionScheduleVersionResource(
    Resource, ArgsMixin
):

    @jwt_required()
    def post(self, production_schedule_version_id):
        """
        Set task links from production schedule version
        ---
        description: Set task links for given production schedule version from
          another production schedule version.
        tags:
          - Projects
        parameters:
          - in: path
            name: production_schedule_version_id
            required: true
            schema:
              type: string
              format: uuid
            description: Production schedule version unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - production_schedule_version_id
                properties:
                  production_schedule_version_id:
                    type: string
                    format: uuid
                    description: Source production schedule version unique
                      identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: Task links created
            content:
              application/json:
                schema:
                  type: object
          400:
            description: Wrong ID format
        """
        production_schedule_version = (
            schedule_service.get_production_schedule_version(
                production_schedule_version_id
            )
        )
        user_service.check_manager_project_access(
            production_schedule_version["project_id"]
        )

        args = self.get_args(
            [
                ("production_schedule_version_id", None, True),
            ]
        )

        other_production_schedule_version = (
            schedule_service.get_production_schedule_version(
                args["production_schedule_version_id"]
            )
        )

        if (
            production_schedule_version["project_id"]
            != other_production_schedule_version["project_id"]
        ):
            raise WrongParameterException(
                "Production schedule versions must belong to the same project."
            )

        return schedule_service.set_production_schedule_version_task_links_from_production_schedule_version(
            production_schedule_version_id,
            other_production_schedule_version_id=other_production_schedule_version[
                "id"
            ],
        )


class ProductionTaskTypesTimeSpentsResource(Resource, ArgsMixin):
    """
    Retrieve time spents for a task type in the production
    """

    @jwt_required()
    def get(self, project_id, task_type_id):
        """
        Get production task type time spents
        ---
        description: Retrieve time spents for a task type in the production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: query
            name: start_date
            required: false
            schema:
              type: string
              format: date
            description: Start date for filtering time spents
            example: "2022-07-01"
          - in: query
            name: end_date
            required: false
            schema:
              type: string
              format: date
            description: End date for filtering time spents
            example: "2022-07-31"
        responses:
          200:
            description: All time spents for given task type and project
            content:
              application/json:
                schema:
                  type: dict
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Time spent unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      person_id:
                        type: string
                        format: uuid
                        description: Person unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      duration:
                        type: number
                        format: float
                        description: Time spent duration in hours
                        example: 8.5
                      date:
                        type: string
                        format: date
                        description: Date of time spent entry
                        example: "2022-07-15"
          400:
            description: Invalid date range parameters
        """
        user_service.check_manager_project_access(project_id)
        arguments = self.get_args(["start_date", "end_date"])
        start_date, end_date = arguments["start_date"], arguments["end_date"]
        try:
            return time_spents_service.get_project_task_type_time_spents(
                project_id, task_type_id, start_date, end_date
            )
        except WrongDateFormatException:
            abort(
                400,
                f"Wrong date format for {start_date} and/or {end_date}",
            )


class ProductionDayOffsResource(Resource, ArgsMixin):
    """
    Retrieve all day offs for a production
    """

    @jwt_required()
    def get(self, project_id):
        """
        Get production day offs
        ---
        description: Retrieve all day offs for a production.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: start_date
            required: false
            schema:
              type: string
              format: date
            description: Start date for filtering day offs
            example: "2022-07-01"
          - in: query
            name: end_date
            required: false
            schema:
              type: string
              format: date
            description: End date for filtering day offs
            example: "2022-07-31"
        responses:
          200:
            description: All day offs for given project
            content:
              application/json:
                schema:
                  type: dict
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Day off unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      person_id:
                        type: string
                        format: uuid
                        description: Person unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      description:
                        type: string
                        description: Day off description
                        example: "Vacation"
                      date:
                        type: string
                        format: date
                        description: Day off start date
                        example: "2022-07-15"
                      end_date:
                        type: string
                        format: date
                        description: Day off end date
                        example: "2022-07-22"
          400:
            description: Invalid date range parameters
        """
        user_service.check_project_access(project_id)
        if (
            permissions.has_client_permissions()
            or permissions.has_vendor_permissions()
        ):
            raise permissions.PermissionDenied
        arguments = self.get_args(["start_date", "end_date"])
        start_date, end_date = arguments["start_date"], arguments["end_date"]
        try:
            return time_spents_service.get_day_offs_between_for_project(
                project_id,
                start_date,
                end_date,
                safe=permissions.has_manager_permissions(),
                current_user_id=persons_service.get_current_user()["id"],
            )
        except WrongDateFormatException:
            abort(
                400,
                f"Wrong date format for {start_date} and/or {end_date}",
            )
