from flasgger import swag_from
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
    permissions_service,
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
from zou.app.exceptions import (
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
    @swag_from("openapi/OpenProjectsResource_get.yml")
    def get(self):
        """
        Get open projects
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
    @swag_from("openapi/AllProjectsResource_get.yml")
    def get(self):
        """
        Get all projects
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
    @swag_from("openapi/ProductionTeamResource_get.yml")
    def get(self, project_id):
        """
        Get production team
        """
        permissions_service.check_project_access(project_id)
        role_map = projects_service.get_team_roles(str(project_id))
        persons = []
        for person in projects_service.get_team_raw(project_id):
            if permissions.has_manager_permissions():
                data = person.serialize_safe(relations=True)
            else:
                data = person.present_minimal()
            data["project_role"] = role_map.get(str(person.id))
            persons.append(data)
        return persons

    @jwt_required()
    @swag_from("openapi/ProductionTeamResource_post.yml")
    def post(self, project_id):
        """
        Add person to production team
        """
        body = validation.validate_request_body(ProjectTeamSchema)

        permissions_service.check_manager_project_access(project_id)
        return (
            projects_service.add_team_member(
                project_id, body.person_id, role=body.role
            ),
            201,
        )


class ProductionTeamMemberResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ProductionTeamMemberResource_delete.yml")
    def delete(self, project_id, person_id):
        """
        Remove person from production team
        """
        permissions_service.check_manager_project_access(project_id)
        projects_service.remove_team_member(project_id, person_id)
        return "", 204

    @jwt_required()
    @swag_from("openapi/ProductionTeamMemberResource_put.yml")
    def put(self, project_id, person_id):
        """
        Set team member role
        """
        body = validation.validate_request_body(ProjectTeamRoleSchema)
        permissions_service.check_manager_project_access(project_id)
        return projects_service.update_team_member_role(
            project_id, person_id, body.role
        )


class ProductionAssetTypeResource(MethodView, ArgsMixin):
    """
    Allow to add an asset type linked to a production.
    """

    @jwt_required()
    @swag_from("openapi/ProductionAssetTypeResource_post.yml")
    def post(self, project_id):
        """
        Add asset type to production
        """
        body = validation.validate_request_body(ProjectAssetTypeSchema)

        permissions_service.check_manager_project_access(project_id)
        project = projects_service.add_asset_type_setting(
            project_id, body.asset_type_id
        )
        return project, 201


class ProductionAssetTypeRemoveResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ProductionAssetTypeRemoveResource_delete.yml")
    def delete(self, project_id, asset_type_id):
        """
        Remove asset type from production
        """
        permissions_service.check_manager_project_access(project_id)
        projects_service.remove_asset_type_setting(project_id, asset_type_id)
        return "", 204


class ProductionTaskTypesResource(MethodView, ArgsMixin):
    """
    Retrieve task types linked to the production
    """

    @jwt_required()
    @swag_from("openapi/ProductionTaskTypesResource_get.yml")
    def get(self, project_id):
        """
        Get production task types
        """
        permissions_service.check_project_access(project_id)
        return projects_service.get_project_task_types(project_id)


class ProductionTaskTypeResource(MethodView, ArgsMixin):
    """
    Allow to add a task type linked to a production.
    """

    @jwt_required()
    @swag_from("openapi/ProductionTaskTypeResource_post.yml")
    def post(self, project_id):
        """
        Add task type to production
        """
        body = validation.validate_request_body(ProjectTaskTypeSchema)

        permissions_service.check_manager_project_access(project_id)
        project = projects_service.add_task_type_setting(
            project_id,
            body.task_type_id,
            body.priority,
            bitrates=body.bitrates(),
        )
        return project, 201


class ProductionTaskTypeRemoveResource(MethodView):
    """
    Allow to remove a task type linked to a production.
    """

    @jwt_required()
    @swag_from("openapi/ProductionTaskTypeRemoveResource_delete.yml")
    def delete(self, project_id, task_type_id):
        """
        Remove task type from production
        """
        permissions_service.check_manager_project_access(project_id)
        projects_service.remove_task_type_setting(project_id, task_type_id)
        return "", 204


class ProductionTaskStatusResource(MethodView, ArgsMixin):
    """
    Allow to add a task type linked to a production.
    """

    @jwt_required()
    @swag_from("openapi/ProductionTaskStatusResource_get.yml")
    def get(self, project_id):
        """
        Get production task statuses
        """
        permissions_service.check_project_access(project_id)
        return projects_service.get_project_task_statuses(project_id)

    @jwt_required()
    @swag_from("openapi/ProductionTaskStatusResource_post.yml")
    def post(self, project_id):
        """
        Add task status to production
        """
        body = validation.validate_request_body(ProjectTaskStatusSchema)

        permissions_service.check_manager_project_access(project_id)
        project = projects_service.add_task_status_setting(
            project_id, body.task_status_id
        )
        return project, 201


class ProductionTaskStatusRemoveResource(MethodView):
    """
    Allow to remove a task status linked to a production.
    """

    @jwt_required()
    @swag_from("openapi/ProductionTaskStatusRemoveResource_delete.yml")
    def delete(self, project_id, task_status_id):
        """
        Remove task status from production
        """
        permissions_service.check_manager_project_access(project_id)
        projects_service.remove_task_status_setting(project_id, task_status_id)
        return "", 204


class ProductionSettingsBatchResource(MethodView):
    """
    Allow to add several task types, task statuses and asset types to a
    production in a single request.
    """

    @jwt_required()
    @swag_from("openapi/ProductionSettingsBatchResource_post.yml")
    def post(self, project_id):
        """
        Add settings to production batch
        """
        body = validation.validate_request_body(ProjectSettingsBatchSchema)
        permissions_service.check_manager_project_access(project_id)
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
    @swag_from("openapi/ProductionStatusAutomationResource_get.yml")
    def get(self, project_id):
        """
        Get production status automations
        """
        permissions_service.check_manager_project_access(project_id)
        return projects_service.get_project_status_automations(project_id)

    @jwt_required()
    @swag_from("openapi/ProductionStatusAutomationResource_post.yml")
    def post(self, project_id):
        """
        Add status automation to production
        """
        body = validation.validate_request_body(ProjectStatusAutomationSchema)

        permissions_service.check_manager_project_access(project_id)
        project = projects_service.add_status_automation_setting(
            project_id, body.status_automation_id
        )
        return project, 201


class ProductionStatusAutomationRemoveResource(MethodView):
    """
    Allow to remove a status automation linked to a production.
    """

    @jwt_required()
    @swag_from("openapi/ProductionStatusAutomationRemoveResource_delete.yml")
    def delete(self, project_id, status_automation_id):
        """
        Remove status automation from production
        """
        permissions_service.check_manager_project_access(project_id)
        projects_service.remove_status_automation_setting(
            project_id, status_automation_id
        )
        return "", 204


class ProductionPreviewBackgroundFileResource(MethodView, ArgsMixin):
    """
    Allow to add a preview background file linked to a production.
    """

    @jwt_required()
    @swag_from("openapi/ProductionPreviewBackgroundFileResource_get.yml")
    def get(self, project_id):
        """
        Get production preview background files
        """
        permissions_service.check_project_access(project_id)
        return projects_service.get_project_preview_background_files(
            project_id
        )

    @jwt_required()
    @swag_from("openapi/ProductionPreviewBackgroundFileResource_post.yml")
    def post(self, project_id):
        """
        Add preview background file to production
        """
        body = validation.validate_request_body(ProjectPreviewBackgroundSchema)

        permissions_service.check_manager_project_access(project_id)
        project = projects_service.add_preview_background_file_setting(
            project_id, body.preview_background_file_id
        )
        return project, 201


class ProductionPreviewBackgroundFileRemoveResource(MethodView):
    """
    Allow to remove a preview background file linked to a production.
    """

    @jwt_required()
    @swag_from(
        "openapi/ProductionPreviewBackgroundFileRemoveResource_delete.yml"
    )
    def delete(self, project_id, preview_background_file_id):
        """
        Remove preview background file from production
        """
        permissions_service.check_manager_project_access(project_id)
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
    @swag_from("openapi/ProductionMetadataDescriptorsResource_get.yml")
    def get(self, project_id):
        """
        Get metadata descriptors
        """
        permissions_service.check_project_access(project_id)
        for_client, vendor_departments = (
            user_service.get_descriptor_visibility(
                permissions.get_effective_role()
            )
        )
        return projects_service.get_metadata_descriptors(
            project_id, for_client, vendor_departments
        )

    @jwt_required()
    @swag_from("openapi/ProductionMetadataDescriptorsResource_post.yml")
    def post(self, project_id):
        """
        Create metadata descriptor
        """
        body = validation.validate_request_body(MetadataDescriptorSchema)

        permissions_service.check_all_departments_access(
            project_id, body.departments
        )

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
    @swag_from("openapi/ProductionMetadataDescriptorResource_get.yml")
    def get(self, project_id, metadata_descriptor_id):
        """
        Get metadata descriptor
        """
        permissions_service.check_project_access(project_id)
        descriptor = projects_service.get_project_metadata_descriptor(
            project_id, metadata_descriptor_id
        )
        permissions_service.check_metadata_descriptor_access(descriptor)
        return descriptor

    @jwt_required()
    @swag_from("openapi/ProductionMetadataDescriptorResource_put.yml")
    def put(self, project_id, metadata_descriptor_id):
        """
        Update metadata descriptor
        """
        body = validation.validate_request_body(MetadataDescriptorUpdateSchema)
        # The rights are checked on the project of the path: a descriptor of
        # another project must not be reachable through it.
        descriptor = projects_service.get_project_metadata_descriptor(
            project_id, metadata_descriptor_id
        )
        permissions_service.check_all_departments_access(
            project_id, descriptor["departments"] + body.departments
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
    @swag_from("openapi/ProductionMetadataDescriptorResource_delete.yml")
    def delete(self, project_id, metadata_descriptor_id):
        """
        Delete metadata descriptor
        """
        # The rights are checked on the project of the path: a descriptor of
        # another project must not be reachable through it.
        descriptor = projects_service.get_project_metadata_descriptor(
            project_id, metadata_descriptor_id
        )
        permissions_service.check_all_departments_access(
            project_id, descriptor["departments"]
        )
        projects_service.remove_metadata_descriptor(metadata_descriptor_id)
        return "", 204


class ProductionMetadataDescriptorsReorderResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProductionMetadataDescriptorsReorderResource_post.yml")
    def post(self, project_id):
        """
        Reorder metadata descriptors
        """
        body = validation.validate_request_body(MetadataDescriptorOrderSchema)

        permissions_service.check_manager_project_access(project_id)

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
    Open projects the current user may manage: every open project for an
    admin, otherwise the team ones where their effective role is manager.

    Membership alone is not enough. A role set on the team link replaces
    the global one, so someone holding manager globally and user on a
    production would otherwise reshape its metadata through these routes,
    which the per project ones refuse.
    """
    if permissions.has_admin_permissions():
        return projects_service.open_project_ids()
    global_role = persons_service.get_current_user()["role"]
    project_roles = user_service.get_project_roles()
    return [
        project["id"]
        for project in user_service.related_projects()
        if project_roles.get(project["id"], global_role) == "manager"
    ]


def _check_metadata_entity_type(entity_type):
    if entity_type not in VALID_METADATA_ENTITY_TYPES:
        raise WrongParameterException(
            "Wrong entity type. Please select Asset, Shot, Sequence, "
            "Episode, Edit, or Project."
        )


class AllProjectsMetadataDescriptorsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/AllProjectsMetadataDescriptorsResource_post.yml")
    def post(self):
        """
        Create a metadata descriptor on all accessible projects
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
    @swag_from("openapi/AllProjectsMetadataDescriptorResource_put.yml")
    def put(self, field_name):
        """
        Update a metadata descriptor on all accessible projects
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
    @swag_from("openapi/AllProjectsMetadataDescriptorResource_delete.yml")
    def delete(self, field_name):
        """
        Delete a metadata descriptor from all accessible projects
        """
        permissions.check_manager_permissions()
        entity_type = self.get_text_parameter("entity_type")
        _check_metadata_entity_type(entity_type)
        return projects_service.remove_metadata_descriptor_from_projects(
            _accessible_open_project_ids(), entity_type, field_name
        )


class AllProjectsMetadataDescriptorsReorderResource(MethodView):

    @jwt_required()
    @swag_from(
        "openapi/AllProjectsMetadataDescriptorsReorderResource_post.yml"
    )
    def post(self):
        """
        Reorder metadata descriptors on all accessible projects
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
    @swag_from("openapi/ProductionTimeSpentsResource_get.yml")
    def get(self, project_id):
        """
        Get production time spents
        """
        permissions_service.check_project_access(project_id)
        return tasks_service.get_time_spents_for_project(project_id)


class ProductionMilestonesResource(MethodView):
    """
    Resource to retrieve milestones for given production.
    """

    @jwt_required()
    @swag_from("openapi/ProductionMilestonesResource_get.yml")
    def get(self, project_id):
        """
        Get production milestones
        """
        permissions_service.check_project_access(project_id)
        return schedule_service.get_milestones_for_project(project_id)


class ProductionScheduleItemsResource(MethodView):
    """
    Resource to retrieve schedule items for given production.
    """

    @jwt_required()
    @swag_from("openapi/ProductionScheduleItemsResource_get.yml")
    def get(self, project_id):
        """
        Get production schedule items
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()
        return schedule_service.get_schedule_items(project_id)


class ProductionTaskTypeScheduleItemsResource(MethodView):
    """
    Resource to retrieve schedule items for given production.
    """

    @jwt_required()
    @swag_from("openapi/ProductionTaskTypeScheduleItemsResource_get.yml")
    def get(self, project_id):
        """
        Get production task type schedule items
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()
        return schedule_service.get_task_types_schedule_items(project_id)


class ProductionAssetTypesScheduleItemsResource(MethodView, ArgsMixin):
    """
    Resource to retrieve asset types schedule items for given task type.
    """

    @jwt_required()
    @swag_from("openapi/ProductionAssetTypesScheduleItemsResource_get.yml")
    def get(self, project_id, task_type_id):
        """
        Get asset types schedule items
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()
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
    @swag_from("openapi/ProductionEpisodesScheduleItemsResource_get.yml")
    def get(self, project_id, task_type_id):
        """
        Get episodes schedule items
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()
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
    @swag_from("openapi/ProductionSequencesScheduleItemsResource_get.yml")
    def get(self, project_id, task_type_id):
        """
        Get sequences schedule items
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()
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
    @swag_from("openapi/ProductionEditsScheduleItemsResource_get.yml")
    def get(self, project_id, task_type_id):
        """
        Get edits schedule items
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()
        self.check_id_parameter(project_id)
        self.check_id_parameter(task_type_id)
        episode_id = self.get_id_parameter("episode") or None
        return schedule_service.get_edits_schedule_items(
            project_id, task_type_id, episode_id
        )


class ProductionBudgetsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProductionBudgetsResource_get.yml")
    def get(self, project_id):
        """
        Get production budgets
        """
        permissions_service.check_manager_project_access(project_id)
        self.check_id_parameter(project_id)
        return budget_service.get_budgets(project_id)

    @jwt_required()
    @swag_from("openapi/ProductionBudgetsResource_post.yml")
    def post(self, project_id):
        """
        Create budget
        """
        self.check_id_parameter(project_id)
        permissions_service.check_manager_project_access(project_id)
        body = validation.validate_request_body(BudgetSchema)
        return budget_service.create_budget(
            project_id, body.name, body.currency
        )


class ProductionBudgetResource(MethodView, ArgsMixin):
    """
    Resource to retrieve a budget for given production.
    """

    @jwt_required()
    @swag_from("openapi/ProductionBudgetResource_get.yml")
    def get(self, project_id, budget_id):
        """
        Get budget
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        permissions_service.check_manager_project_access(project_id)
        budget = budget_service.get_budget(budget_id)
        if budget["project_id"] != project_id:
            raise BudgetNotFoundException
        return budget

    @jwt_required()
    @swag_from("openapi/ProductionBudgetResource_put.yml")
    def put(self, project_id, budget_id):
        """
        Update budget
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        permissions_service.check_manager_project_access(project_id)
        body = validation.validate_request_body(BudgetUpdateSchema)
        return budget_service.update_budget(
            budget_id, name=body.name, currency=body.currency
        )

    @jwt_required()
    @swag_from("openapi/ProductionBudgetResource_delete.yml")
    def delete(self, project_id, budget_id):
        """
        Delete budget
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        permissions_service.check_manager_project_access(project_id)
        budget_service.delete_budget(budget_id)
        return "", 204


class ProductionBudgetEntriesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProductionBudgetEntriesResource_get.yml")
    def get(self, project_id, budget_id):
        """
        Get budget entries
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        permissions_service.check_manager_project_access(project_id)
        return budget_service.get_budget_entries(budget_id)

    @jwt_required()
    @swag_from("openapi/ProductionBudgetEntriesResource_post.yml")
    def post(self, project_id, budget_id):
        """
        Create budget entry
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        permissions_service.check_manager_project_access(project_id)
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
    @swag_from("openapi/ProductionBudgetEntryResource_get.yml")
    def get(self, project_id, budget_id, entry_id):
        """
        Get budget entry
        """
        permissions_service.check_manager_project_access(project_id)
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        self.check_id_parameter(entry_id)
        budget = budget_service.get_budget(budget_id)
        if budget["project_id"] != project_id:
            raise BudgetNotFoundException
        return budget_service.get_budget_entry(entry_id)

    @jwt_required()
    @swag_from("openapi/ProductionBudgetEntryResource_put.yml")
    def put(self, project_id, budget_id, entry_id):
        """
        Update budget entry
        """
        permissions_service.check_manager_project_access(project_id)
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        self.check_id_parameter(entry_id)
        body = validation.validate_request_body(BudgetEntryUpdateSchema)
        return budget_service.update_budget_entry(entry_id, body.model_dump())

    @jwt_required()
    @swag_from("openapi/ProductionBudgetEntryResource_delete.yml")
    def delete(self, project_id, budget_id, entry_id):
        """
        Delete budget entry
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        self.check_id_parameter(entry_id)
        permissions_service.check_manager_project_access(project_id)
        budget_service.delete_budget_entry(entry_id)
        return "", 204


class ProductionMonthTimeSpentsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProductionMonthTimeSpentsResource_get.yml")
    def get(self, project_id):
        """
        Get production month time spents
        """
        permissions.check_admin_permissions()
        self.check_id_parameter(project_id)
        user = persons_service.get_current_user()
        return time_spents_service.get_project_month_time_spents(
            project_id, user["timezone"]
        )


class ProductionScheduleVersionTaskLinksResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProductionScheduleVersionTaskLinksResource_get.yml")
    def get(self, production_schedule_version_id):
        """
        Get production schedule version task links
        """
        production_schedule_version = (
            schedule_service.get_production_schedule_version(
                production_schedule_version_id
            )
        )
        permissions_service.check_project_access(
            production_schedule_version["project_id"]
        )
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied

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
    @swag_from(
        "openapi/ProductionScheduleVersionSetTaskLinksFromTasksResource_post.yml"
    )
    def post(self, production_schedule_version_id):
        """
        Set task links from tasks
        """
        production_schedule_version = (
            schedule_service.get_production_schedule_version(
                production_schedule_version_id
            )
        )
        permissions_service.check_manager_project_access(
            production_schedule_version["project_id"]
        )

        return schedule_service.set_production_schedule_version_task_links_from_production(
            production_schedule_version_id
        )


class ProductionScheduleVersionApplyToProductionResource(
    MethodView, ArgsMixin
):

    @jwt_required()
    @swag_from(
        "openapi/ProductionScheduleVersionApplyToProductionResource_post.yml"
    )
    def post(self, production_schedule_version_id):
        """
        Apply production schedule version
        """
        production_schedule_version = (
            schedule_service.get_production_schedule_version(
                production_schedule_version_id
            )
        )
        permissions_service.check_manager_project_access(
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
    @swag_from(
        "openapi/ProductionScheduleVersionSetTaskLinksFromProductionScheduleVersionResource_post.yml"
    )
    def post(self, production_schedule_version_id):
        """
        Set task links from production schedule version
        """
        production_schedule_version = (
            schedule_service.get_production_schedule_version(
                production_schedule_version_id
            )
        )
        permissions_service.check_manager_project_access(
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
            production_schedule_version["id"],
            other_production_schedule_version_id=other_production_schedule_version[
                "id"
            ],
        )


class ProductionTaskTypesTimeSpentsResource(MethodView, ArgsMixin):
    """
    Retrieve time spents for a task type in the production
    """

    @jwt_required()
    @swag_from("openapi/ProductionTaskTypesTimeSpentsResource_get.yml")
    def get(self, project_id, task_type_id):
        """
        Get production task type time spents
        """
        permissions_service.check_manager_project_access(project_id)
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
    @swag_from("openapi/ProductionDayOffsResource_get.yml")
    def get(self, project_id):
        """
        Get production day offs
        """
        permissions_service.check_project_access(project_id)
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
