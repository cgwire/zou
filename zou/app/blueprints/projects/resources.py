from flask import abort
from flask.views import MethodView
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
from zou.app.utils import permissions, validation
from zou.app.blueprints.projects.schemas import (
    ProjectTeamSchema,
    ProjectTeamRoleSchema,
    ProjectAssetTypeSchema,
    ProjectTaskTypeSchema,
    ProjectTaskStatusSchema,
    ProjectSettingsBatchSchema,
    ProjectStatusAutomationSchema,
    ProjectPreviewBackgroundSchema,
    MetadataDescriptorSchema,
    MetadataDescriptorUpdateSchema,
    MetadataDescriptorOrderSchema,
    AllProjectsMetadataDescriptorUpdateSchema,
    AllProjectsMetadataDescriptorOrderSchema,
    BudgetSchema,
    BudgetUpdateSchema,
    BudgetEntrySchema,
    BudgetEntryUpdateSchema,
    ScheduleVersionCopySchema,
)
from zou.app.services.exception import (
    BudgetNotFoundException,
    TaskTypeNotFoundException,
    WrongDateFormatException,
    WrongParameterException,
)
from zou.app.models.metadata_descriptor import METADATA_DESCRIPTOR_TYPES


class OpenProjectsResource(MethodView, ArgsMixin):
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


class AllProjectsResource(MethodView, ArgsMixin):
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


class ProductionTeamResource(MethodView, ArgsMixin):
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
                      project_role:
                        type: string
                        nullable: true
                        description: Person role on this project only. Null
                          means the person's global role applies.
                        example: "supervisor"
        """
        user_service.check_project_access(project_id)
        project = projects_service.get_project_raw(project_id)
        role_map = projects_service.get_team_roles(project_id)
        persons = []
        for person in project.team:
            if permissions.has_manager_permissions():
                data = person.serialize_safe(relations=True)
            else:
                data = person.present_minimal()
            data["project_role"] = role_map.get(str(person.id))
            persons.append(data)
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
                  role:
                    type: string
                    nullable: true
                    description: Role of the person on this project only.
                      Null means the person's global role applies.
                    enum: [user, supervisor, manager, client, vendor, null]
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
        body = validation.validate_request_body(ProjectTeamSchema)

        user_service.check_manager_project_access(project_id)
        return (
            projects_service.add_team_member(
                project_id, body.person_id, role=body.role
            ),
            201,
        )


class ProductionTeamMemberResource(MethodView):

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

    @jwt_required()
    def put(self, project_id, person_id):
        """
        Set team member role
        ---
        description: Set the role of a person on this production only.
                     A null role restores the person's global role.
        tags:
          - Projects
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
          - in: path
            name: person_id
            required: true
            schema:
              type: string
              format: uuid
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  role:
                    type: string
                    nullable: true
                    enum: [user, supervisor, manager, client, vendor, null]
        responses:
          200:
            description: Role updated
          400:
            description: Person is not a member of the project team
        """
        body = validation.validate_request_body(ProjectTeamRoleSchema)
        user_service.check_manager_project_access(project_id)
        return projects_service.update_team_member_role(
            project_id, person_id, body.role
        )


class ProductionAssetTypeResource(MethodView, ArgsMixin):
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
        body = validation.validate_request_body(ProjectAssetTypeSchema)

        user_service.check_manager_project_access(project_id)
        project = projects_service.add_asset_type_setting(
            project_id, body.asset_type_id
        )
        return project, 201


class ProductionAssetTypeRemoveResource(MethodView):

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


class ProductionTaskTypesResource(MethodView, ArgsMixin):
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


class ProductionTaskTypeResource(MethodView, ArgsMixin):
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
        body = validation.validate_request_body(ProjectTaskTypeSchema)

        user_service.check_manager_project_access(project_id)
        project = projects_service.add_task_type_setting(
            project_id, body.task_type_id, body.priority
        )
        return project, 201


class ProductionTaskTypeRemoveResource(MethodView):
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


class ProductionTaskStatusResource(MethodView, ArgsMixin):
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
        body = validation.validate_request_body(ProjectTaskStatusSchema)

        user_service.check_manager_project_access(project_id)
        project = projects_service.add_task_status_setting(
            project_id, body.task_status_id
        )
        return project, 201


class ProductionTaskStatusRemoveResource(MethodView):
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


class ProductionSettingsBatchResource(MethodView):
    """
    Allow to add several task types, task statuses and asset types to a
    production in a single request.
    """

    @jwt_required()
    def post(self, project_id):
        """
        Add settings to production batch
        ---
        description: Add several task types (with their priority), task
          statuses and asset types to a production in a single request,
          replacing one link request per item. Unknown ids are skipped.
          When replace_task_types is set, the task type list is the full
          wanted set and existing links absent from it are removed.
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
                properties:
                  task_types:
                    type: array
                    items:
                      type: object
                      properties:
                        task_type_id:
                          type: string
                          format: uuid
                        priority:
                          type: integer
                  task_status_ids:
                    type: array
                    items:
                      type: string
                      format: uuid
                  asset_type_ids:
                    type: array
                    items:
                      type: string
                      format: uuid
                  replace_task_types:
                    type: boolean
                    default: false
        responses:
          200:
            description: Updated project
        """
        body = validation.validate_request_body(ProjectSettingsBatchSchema)
        user_service.check_manager_project_access(project_id)
        return projects_service.update_project_settings(
            project_id,
            task_types=[entry.model_dump() for entry in body.task_types],
            task_status_ids=body.task_status_ids,
            asset_type_ids=body.asset_type_ids,
            replace_task_types=body.replace_task_types,
        )


class ProductionStatusAutomationResource(MethodView, ArgsMixin):
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
        body = validation.validate_request_body(ProjectStatusAutomationSchema)

        user_service.check_manager_project_access(project_id)
        project = projects_service.add_status_automation_setting(
            project_id, body.status_automation_id
        )
        return project, 201


class ProductionStatusAutomationRemoveResource(MethodView):
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


class ProductionPreviewBackgroundFileResource(MethodView, ArgsMixin):
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
        body = validation.validate_request_body(ProjectPreviewBackgroundSchema)

        user_service.check_manager_project_access(project_id)
        project = projects_service.add_preview_background_file_setting(
            project_id, body.preview_background_file_id
        )
        return project, 201


class ProductionPreviewBackgroundFileRemoveResource(MethodView):
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


class ProductionMetadataDescriptorsResource(MethodView, ArgsMixin):
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
                    enum:
                      - Asset
                      - Shot
                      - Edit
                      - Episode
                      - Sequence
                      - Project
                      - Task
                    default: "Asset"
                    example: "Asset"
                  task_type_id:
                    type: string
                    format: uuid
                    description: Task type the descriptor is scoped to.
                      Required for Task descriptors, forbidden otherwise.
                    example: a24a6ea4-ce75-4665-a070-57453082c25
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
        body = validation.validate_request_body(MetadataDescriptorSchema)

        user_service.check_all_departments_access(project_id, body.departments)

        if body.entity_type not in [
            "Asset",
            "Shot",
            "Edit",
            "Episode",
            "Sequence",
            "Project",
            "Task",
        ]:
            raise WrongParameterException(
                "Wrong entity type. Please select Asset, Shot, Sequence, "
                "Episode, Edit, Project, or Task."
            )

        if body.entity_type == "Task":
            if body.task_type_id is None:
                raise WrongParameterException(
                    "Task metadata descriptors require a task_type_id."
                )
            try:
                tasks_service.get_task_type(body.task_type_id)
            except TaskTypeNotFoundException:
                raise WrongParameterException("Task type not found.")
        elif body.task_type_id is not None:
            raise WrongParameterException(
                "task_type_id only applies to Task metadata descriptors."
            )

        types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
        if body.data_type not in types:
            raise WrongParameterException("Invalid data_type")

        return (
            projects_service.add_metadata_descriptor(
                project_id,
                body.entity_type,
                body.name,
                body.data_type,
                body.choices,
                body.for_client,
                body.departments,
                task_type_id=body.task_type_id,
            ),
            201,
        )


class ProductionMetadataDescriptorResource(MethodView, ArgsMixin):
    """
    Resource to get, update or delete a metadata descriptor. Descriptors serve
    to describe extra fields listed in the data attribute of entities.
    """

    @jwt_required()
    def get(self, project_id, metadata_descriptor_id):
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
            name: metadata_descriptor_id
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
        return projects_service.get_metadata_descriptor(metadata_descriptor_id)

    @jwt_required()
    def put(self, project_id, metadata_descriptor_id):
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
            name: metadata_descriptor_id
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
        body = validation.validate_request_body(MetadataDescriptorUpdateSchema)
        user_service.check_all_departments_access(
            project_id,
            projects_service.get_metadata_descriptor(metadata_descriptor_id)[
                "departments"
            ]
            + body.departments,
        )

        if body.name is not None and len(body.name) == 0:
            raise WrongParameterException("Name cannot be empty.")

        types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
        if body.data_type not in types:
            raise WrongParameterException("Invalid data_type")

        args = body.model_dump()
        return projects_service.update_metadata_descriptor(
            metadata_descriptor_id, args
        )

    @jwt_required()
    def delete(self, project_id, metadata_descriptor_id):
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
            name: metadata_descriptor_id
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
            projects_service.get_metadata_descriptor(metadata_descriptor_id)[
                "departments"
            ],
        )
        projects_service.remove_metadata_descriptor(metadata_descriptor_id)
        return "", 204


class ProductionMetadataDescriptorsReorderResource(MethodView, ArgsMixin):

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
                    enum:
                      - Asset
                      - Shot
                      - Edit
                      - Episode
                      - Sequence
                      - Project
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
        body = validation.validate_request_body(MetadataDescriptorOrderSchema)

        user_service.check_manager_project_access(project_id)

        if body.entity_type not in [
            "Asset",
            "Shot",
            "Edit",
            "Episode",
            "Sequence",
            "Project",
            "Task",
        ]:
            raise WrongParameterException(
                "Wrong entity type. Please select Asset, Shot, Sequence, "
                "Episode, Edit, Project, or Task."
            )

        return projects_service.reorder_metadata_descriptors(
            project_id, body.entity_type, body.descriptor_ids
        )


VALID_METADATA_ENTITY_TYPES = [
    "Asset",
    "Shot",
    "Edit",
    "Episode",
    "Sequence",
    "Project",
]


def _accessible_open_project_ids():
    """
    Open projects the current user can act on: every open project for an
    admin, only the user's team open projects otherwise. Keeps the
    all-projects metadata routes from touching projects a manager has no
    access to.
    """
    if permissions.has_admin_permissions():
        return projects_service.open_project_ids()
    return [project["id"] for project in user_service.related_projects()]


def _check_metadata_entity_type(entity_type):
    if entity_type not in VALID_METADATA_ENTITY_TYPES:
        raise WrongParameterException(
            "Wrong entity type. Please select Asset, Shot, Sequence, "
            "Episode, Edit, or Project."
        )


class AllProjectsMetadataDescriptorsResource(MethodView):

    @jwt_required()
    def post(self):
        """
        Create a metadata descriptor on all accessible projects
        ---
        description: Create the same metadata descriptor in every open
          project the user can access that does not already own one with the
          same field name. Replaces one create request per project.
        tags:
          - Projects
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
                    default: "Project"
                  name:
                    type: string
                  data_type:
                    type: string
        responses:
          201:
            description: Created descriptors
          400:
            description: Invalid parameters
        """
        permissions.check_manager_permissions()
        body = validation.validate_request_body(MetadataDescriptorSchema)
        _check_metadata_entity_type(body.entity_type)
        types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
        if body.data_type not in types:
            raise WrongParameterException("Invalid data_type")
        return (
            projects_service.add_metadata_descriptor_to_projects(
                _accessible_open_project_ids(),
                body.entity_type,
                body.name,
                body.data_type,
                body.choices,
                body.for_client,
                body.departments,
            ),
            201,
        )


class AllProjectsMetadataDescriptorResource(MethodView, ArgsMixin):

    @jwt_required()
    def put(self, field_name):
        """
        Update a metadata descriptor on all accessible projects
        ---
        description: Update every metadata descriptor sharing the given field
          name across the open projects the user can access. Replaces one
          update request per project.
        tags:
          - Projects
        parameters:
          - in: path
            name: field_name
            required: true
            schema:
              type: string
        responses:
          200:
            description: Updated descriptors
          400:
            description: Invalid parameters
        """
        permissions.check_manager_permissions()
        body = validation.validate_request_body(
            AllProjectsMetadataDescriptorUpdateSchema
        )
        _check_metadata_entity_type(body.entity_type)
        types = [type_name for type_name, _ in METADATA_DESCRIPTOR_TYPES]
        if body.data_type not in types:
            raise WrongParameterException("Invalid data_type")
        changes = {
            "for_client": body.for_client,
            "data_type": body.data_type,
            "choices": body.choices,
            "departments": body.departments,
        }
        # Keep the field name untouched when the name is not being changed.
        if body.name:
            changes["name"] = body.name
        return projects_service.update_metadata_descriptor_on_projects(
            _accessible_open_project_ids(),
            body.entity_type,
            field_name,
            changes,
        )

    @jwt_required()
    def delete(self, field_name):
        """
        Delete a metadata descriptor from all accessible projects
        ---
        description: Remove every metadata descriptor sharing the given field
          name across the open projects the user can access. Replaces one
          delete request per project.
        tags:
          - Projects
        parameters:
          - in: path
            name: field_name
            required: true
            schema:
              type: string
          - in: query
            name: entity_type
            required: true
            schema:
              type: string
        responses:
          200:
            description: Removed descriptor ids
          400:
            description: Invalid parameters
        """
        permissions.check_manager_permissions()
        entity_type = self.get_text_parameter("entity_type")
        _check_metadata_entity_type(entity_type)
        return projects_service.remove_metadata_descriptor_from_projects(
            _accessible_open_project_ids(), entity_type, field_name
        )


class AllProjectsMetadataDescriptorsReorderResource(MethodView):

    @jwt_required()
    def post(self):
        """
        Reorder metadata descriptors on all accessible projects
        ---
        description: Apply the same column order, given as a list of field
          names, on every open project the user can access. Replaces one
          reorder request per project.
        tags:
          - Projects
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - entity_type
                  - field_order
                properties:
                  entity_type:
                    type: string
                  field_order:
                    type: array
                    items:
                      type: string
        responses:
          200:
            description: Updated descriptors
          400:
            description: Invalid parameters
        """
        permissions.check_manager_permissions()
        body = validation.validate_request_body(
            AllProjectsMetadataDescriptorOrderSchema
        )
        _check_metadata_entity_type(body.entity_type)
        return projects_service.reorder_metadata_descriptors_on_projects(
            _accessible_open_project_ids(),
            body.entity_type,
            body.field_order,
        )


class ProductionTimeSpentsResource(MethodView):
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


class ProductionMilestonesResource(MethodView):
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


class ProductionScheduleItemsResource(MethodView):
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


class ProductionTaskTypeScheduleItemsResource(MethodView):
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


class ProductionAssetTypesScheduleItemsResource(MethodView, ArgsMixin):
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
          - in: query
            name: episode_id
            required: false
            schema:
              type: string
              format: uuid
            description: Restrict results to asset types of the given episode
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
        self.check_id_parameter(project_id)
        self.check_id_parameter(task_type_id)
        episode_id = self.get_id_parameter("episode") or None
        return schedule_service.get_asset_types_schedule_items(
            project_id, task_type_id, episode_id
        )


class ProductionEpisodesScheduleItemsResource(MethodView, ArgsMixin):
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
          - in: query
            name: episode_id
            required: false
            schema:
              type: string
              format: uuid
            description: Restrict results to the given episode
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
        self.check_id_parameter(project_id)
        self.check_id_parameter(task_type_id)
        episode_id = self.get_id_parameter("episode") or None
        return schedule_service.get_episodes_schedule_items(
            project_id, task_type_id, episode_id
        )


class ProductionSequencesScheduleItemsResource(MethodView, ArgsMixin):
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
          - in: query
            name: episode_id
            required: false
            schema:
              type: string
              format: uuid
            description: Restrict results to sequences of the given episode
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
        self.check_id_parameter(project_id)
        self.check_id_parameter(task_type_id)
        episode_id = self.get_id_parameter("episode") or None
        return schedule_service.get_sequences_schedule_items(
            project_id, task_type_id, episode_id
        )


class ProductionEditsScheduleItemsResource(MethodView, ArgsMixin):
    """
    Resource to retrieve edits schedule items for given task type.
    """

    @jwt_required()
    def get(self, project_id, task_type_id):
        """
        Get edits schedule items
        ---
        description: Retrieve edits schedule items for given task type.
        tags:
          - Projects
        parameters:
          - in: query
            name: episode_id
            required: false
            schema:
              type: string
              format: uuid
            description: Restrict results to edits of the given episode
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
            description: All edits schedule items for given task type
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
        """
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        self.check_id_parameter(project_id)
        self.check_id_parameter(task_type_id)
        episode_id = self.get_id_parameter("episode") or None
        return schedule_service.get_edits_schedule_items(
            project_id, task_type_id, episode_id
        )


class ProductionBudgetsResource(MethodView, ArgsMixin):

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
        body = validation.validate_request_body(BudgetSchema)
        return budget_service.create_budget(
            project_id, body.name, body.currency
        )


class ProductionBudgetResource(MethodView, ArgsMixin):
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
        budget = budget_service.get_budget(budget_id)
        if budget["project_id"] != project_id:
            raise BudgetNotFoundException
        return budget

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
        body = validation.validate_request_body(BudgetUpdateSchema)
        return budget_service.update_budget(
            budget_id, name=body.name, currency=body.currency
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


class ProductionBudgetEntriesResource(MethodView, ArgsMixin):

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
        body = validation.validate_request_body(BudgetEntrySchema)
        return budget_service.create_budget_entry(
            budget_id,
            body.department_id,
            body.start_date,
            body.months_duration,
            body.daily_salary,
            body.position,
            body.seniority,
            person_id=body.person_id,
        )


class ProductionBudgetEntryResource(MethodView, ArgsMixin):

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
        budget = budget_service.get_budget(budget_id)
        if budget["project_id"] != project_id:
            raise BudgetNotFoundException
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
        body = validation.validate_request_body(BudgetEntryUpdateSchema)
        return budget_service.update_budget_entry(entry_id, body.model_dump())

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


class ProductionMonthTimeSpentsResource(MethodView, ArgsMixin):

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


class ProductionScheduleVersionTaskLinksResource(MethodView, ArgsMixin):

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
    MethodView, ArgsMixin
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


class ProductionScheduleVersionApplyToProductionResource(
    MethodView, ArgsMixin
):

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
    MethodView, ArgsMixin
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

        body = validation.validate_request_body(ScheduleVersionCopySchema)

        other_production_schedule_version = (
            schedule_service.get_production_schedule_version(
                body.production_schedule_version_id
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


class ProductionTaskTypesTimeSpentsResource(MethodView, ArgsMixin):
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
        self.check_id_parameter(task_type_id)
        arguments = self.get_args(["start_date", "end_date"])
        start_date, end_date = arguments["start_date"], arguments["end_date"]
        try:
            return time_spents_service.get_project_task_type_time_spents(
                project_id, task_type_id, start_date, end_date
            )
        except WrongDateFormatException:
            raise WrongParameterException(
                f"Wrong date format for {start_date} and/or {end_date}"
            )


class ProductionDayOffsResource(MethodView, ArgsMixin):
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
            raise WrongParameterException(
                f"Wrong date format for {start_date} and/or {end_date}"
            )
