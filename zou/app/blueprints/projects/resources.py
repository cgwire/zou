from flask import jsonify
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.blueprints.projects.schemas import (
    AllProjectsMetadataDescriptorOrderSchema,
    AllProjectsMetadataDescriptorUpdateSchema,
    BudgetEntrySchema,
    BudgetEntryUpdateSchema,
    BudgetSchema,
    BudgetUpdateSchema,
    MetadataDescriptorOrderSchema,
    MetadataDescriptorSchema,
    MetadataDescriptorUpdateSchema,
    PreviewAccountOpenSchema,
    ProjectAssetTypeSchema,
    ProjectAssetTypeWorkflowSchema,
    ProjectPreviewBackgroundSchema,
    ProjectSettingsBatchSchema,
    ProjectStatusAutomationSchema,
    ProjectTaskStatusClientAllowedSchema,
    ProjectTaskStatusSchema,
    ProjectTaskTypeSchema,
    ProjectTaskTypeSoftwareSchema,
    ProjectTeamRoleSchema,
    ProjectTeamSchema,
    ScheduleVersionCopySchema,
)
from zou.app.exceptions import (
    TaskTypeNotFoundException,
    WrongDateFormatException,
    WrongParameterException,
)
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    budget_service,
    metadata_descriptors_service,
    permissions_service,
    persons_service,
    preview_accounts_service,
    projects_service,
    schedule_service,
    task_types_service,
    time_spents_service,
    user_service,
)
from zou.app.utils import permissions, validation
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")

VALID_METADATA_ENTITY_TYPES = [
    "Asset",
    "Shot",
    "Edit",
    "Episode",
    "Sequence",
    "Project",
]


class OpenProjectsResource(MethodView, ArgsMixin):
    """
    Return the list of the open projects. Most of the time, users do not need
    the past projects. A non-admin gets only the open projects of their teams.
    """

    @jwt_required()
    @swag_from(SPECS["OpenProjectsResource_get"])
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
    Return all the projects of the database to an admin. The other users get
    only the projects of their teams.
    """

    @jwt_required()
    @swag_from(SPECS["AllProjectsResource_get"])
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
    Manage the people of a production team.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTeamResource_get"])
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
            elif permissions.has_client_permissions():
                data = person.present_client()
            else:
                data = person.present_minimal()
            data["project_role"] = role_map.get(str(person.id))
            persons.append(data)
        return persons

    @jwt_required()
    @swag_from(SPECS["ProductionTeamResource_post"])
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
    @swag_from(SPECS["ProductionTeamMemberResource_delete"])
    def delete(self, project_id, person_id):
        """
        Remove person from production team
        """
        permissions_service.check_manager_project_access(project_id)
        projects_service.remove_team_member(project_id, person_id)
        return "", 204

    @jwt_required()
    @swag_from(SPECS["ProductionTeamMemberResource_put"])
    def put(self, project_id, person_id):
        """
        Set team member role
        """
        body = validation.validate_request_body(ProjectTeamRoleSchema)
        permissions_service.check_manager_project_access(project_id)
        return projects_service.update_team_member_role(
            project_id, person_id, body.role
        )


class ProductionPreviewAccountResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["ProductionPreviewAccountResource_get"])
    def get(self, project_id):
        """
        Get the preview account of a production
        """
        permissions_service.check_manager_project_access(project_id)
        return jsonify(
            preview_accounts_service.get_preview_account(project_id)
        )

    @jwt_required()
    @swag_from(SPECS["ProductionPreviewAccountResource_post"])
    def post(self, project_id):
        """
        Create the preview account of a production or reset its password
        """
        permissions_service.check_manager_project_access(project_id)
        account, password = (
            preview_accounts_service.create_or_reset_preview_account(
                project_id
            )
        )
        return {**account, "password": password}, 201

    @jwt_required()
    @swag_from(SPECS["ProductionPreviewAccountResource_put"])
    def put(self, project_id):
        """
        Open or close the access window of the preview account
        """
        body = validation.validate_request_body(PreviewAccountOpenSchema)
        permissions_service.check_manager_project_access(project_id)
        return preview_accounts_service.set_preview_account_open(
            project_id, body.is_open
        )

    @jwt_required()
    @swag_from(SPECS["ProductionPreviewAccountResource_delete"])
    def delete(self, project_id):
        """
        Delete the preview account of a production
        """
        permissions_service.check_manager_project_access(project_id)
        preview_accounts_service.delete_preview_account(project_id)
        return "", 204


class ProductionAssetTypeResource(MethodView, ArgsMixin):
    """
    Add an asset type to a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionAssetTypeResource_post"])
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
    @swag_from(SPECS["ProductionAssetTypeRemoveResource_delete"])
    def delete(self, project_id, asset_type_id):
        """
        Remove asset type from production
        """
        permissions_service.check_manager_project_access(project_id)
        projects_service.remove_asset_type_setting(project_id, asset_type_id)
        return "", 204


class ProductionAssetTypeWorkflowResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["ProductionAssetTypeWorkflowResource_put"])
    def put(self, project_id, asset_type_id):
        """
        Set the workflow of an asset type for a production
        """
        body = validation.validate_request_body(ProjectAssetTypeWorkflowSchema)
        permissions_service.check_manager_project_access(project_id)
        return projects_service.set_asset_type_workflow(
            project_id, asset_type_id, body.task_type_ids
        )


class ProductionTaskTypesResource(MethodView, ArgsMixin):
    """
    Return the task types linked to the production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTaskTypesResource_get"])
    def get(self, project_id):
        """
        Get production task types
        """
        permissions_service.check_project_access(project_id)
        return projects_service.get_project_task_types(project_id)


class ProductionTaskTypeResource(MethodView, ArgsMixin):
    """
    Add a task type to a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTaskTypeResource_post"])
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
            is_client_visible=body.is_client_visible,
        )
        return project, 201


class ProductionTaskTypeRemoveResource(MethodView):
    """
    Remove a task type from a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTaskTypeRemoveResource_delete"])
    def delete(self, project_id, task_type_id):
        """
        Remove task type from production
        """
        permissions_service.check_manager_project_access(project_id)
        projects_service.remove_task_type_setting(project_id, task_type_id)
        return "", 204


class ProductionTaskTypeSoftwaresResource(MethodView):
    """
    List the softwares linked to the task types of a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTaskTypeSoftwaresResource_get"])
    def get(self, project_id):
        """
        Get production task type softwares
        """
        permissions_service.check_project_access(project_id)
        return projects_service.get_task_type_software_links(project_id)


class ProductionTaskTypeSoftwareResource(MethodView):
    """
    Link a software to a task type of a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTaskTypeSoftwareResource_post"])
    def post(self, project_id, task_type_id):
        """
        Add software to production task type
        """
        body = validation.validate_request_body(ProjectTaskTypeSoftwareSchema)
        permissions_service.check_supervisor_project_task_type_access(
            project_id, task_type_id
        )
        link = projects_service.add_task_type_software(
            project_id, task_type_id, body.software_id
        )
        return link, 201


class ProductionTaskTypeSoftwareRemoveResource(MethodView):
    """
    Unlink a software from a task type of a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTaskTypeSoftwareRemoveResource_delete"])
    def delete(self, project_id, task_type_id, software_id):
        """
        Remove software from production task type
        """
        permissions_service.check_supervisor_project_task_type_access(
            project_id, task_type_id
        )
        projects_service.remove_task_type_software(
            project_id, task_type_id, software_id
        )
        return "", 204


class ProductionTaskStatusResource(MethodView, ArgsMixin):
    """
    List or add the task statuses linked to a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTaskStatusResource_get"])
    def get(self, project_id):
        """
        Get production task statuses
        """
        permissions_service.check_project_access(project_id)
        return projects_service.get_project_task_statuses(project_id)

    @jwt_required()
    @swag_from(SPECS["ProductionTaskStatusResource_post"])
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
    Update or remove a task status linked to a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTaskStatusRemoveResource_put"])
    def put(self, project_id, task_status_id):
        """
        Set production task status client permission
        """
        body = validation.validate_request_body(
            ProjectTaskStatusClientAllowedSchema
        )
        permissions_service.check_manager_project_access(project_id)
        return projects_service.set_task_status_client_allowed(
            project_id, task_status_id, body.is_client_allowed
        )

    @jwt_required()
    @swag_from(SPECS["ProductionTaskStatusRemoveResource_delete"])
    def delete(self, project_id, task_status_id):
        """
        Remove task status from production
        """
        permissions_service.check_manager_project_access(project_id)
        projects_service.remove_task_status_setting(project_id, task_status_id)
        return "", 204


class ProductionSettingsBatchResource(MethodView):
    """
    Add several task types, task statuses and asset types to a production in
    one request.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionSettingsBatchResource_post"])
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
    List or add the status automations linked to a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionStatusAutomationResource_get"])
    def get(self, project_id):
        """
        Get production status automations
        """
        permissions_service.check_manager_project_access(project_id)
        return projects_service.get_project_status_automations(project_id)

    @jwt_required()
    @swag_from(SPECS["ProductionStatusAutomationResource_post"])
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
    Remove a status automation linked to a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionStatusAutomationRemoveResource_delete"])
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
    List or add the preview background files linked to a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionPreviewBackgroundFileResource_get"])
    def get(self, project_id):
        """
        Get production preview background files
        """
        permissions_service.check_project_access(project_id)
        return projects_service.get_project_preview_background_files(
            project_id
        )

    @jwt_required()
    @swag_from(SPECS["ProductionPreviewBackgroundFileResource_post"])
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
    Remove a preview background file linked to a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionPreviewBackgroundFileRemoveResource_delete"])
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
    Get and create metadata descriptors. A descriptor describes an extra field
    of the data attribute of the entities.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionMetadataDescriptorsResource_get"])
    def get(self, project_id):
        """
        Get metadata descriptors
        """
        permissions_service.check_project_access(project_id)
        for_client, vendor_departments = (
            permissions_service.get_descriptor_visibility(
                permissions.get_effective_role()
            )
        )
        return metadata_descriptors_service.get_metadata_descriptors(
            project_id, for_client, vendor_departments
        )

    @jwt_required()
    @swag_from(SPECS["ProductionMetadataDescriptorsResource_post"])
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
                task_types_service.get_task_type(body.task_type_id)
            except TaskTypeNotFoundException:
                raise WrongParameterException("Task type not found.")
        elif body.task_type_id is not None:
            raise WrongParameterException(
                "task_type_id only applies to Task metadata descriptors."
            )

        metadata_descriptors_service.check_metadata_descriptor_data_type(
            body.data_type
        )

        return (
            metadata_descriptors_service.add_metadata_descriptor(
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
    Get, update or delete a metadata descriptor. A descriptor describes an
    extra field of the data attribute of the entities.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionMetadataDescriptorResource_get"])
    def get(self, project_id, metadata_descriptor_id):
        """
        Get metadata descriptor
        """
        permissions_service.check_project_access(project_id)
        descriptor = (
            metadata_descriptors_service.get_project_metadata_descriptor(
                project_id, metadata_descriptor_id
            )
        )
        permissions_service.check_metadata_descriptor_access(descriptor)
        return descriptor

    @jwt_required()
    @swag_from(SPECS["ProductionMetadataDescriptorResource_put"])
    def put(self, project_id, metadata_descriptor_id):
        """
        Update metadata descriptor
        """
        body = validation.validate_request_body(MetadataDescriptorUpdateSchema)
        # The route checks the rights on the project of the path: a descriptor
        # of another project must not be reachable through that path.
        descriptor = (
            metadata_descriptors_service.get_project_metadata_descriptor(
                project_id, metadata_descriptor_id
            )
        )
        permissions_service.check_all_departments_access(
            project_id, descriptor["departments"]
        )
        args = body.model_dump(exclude_unset=True)
        # An empty list makes the column visible to all departments: the
        # check refuses it to a supervisor.
        if "departments" in args:
            permissions_service.check_all_departments_access(
                project_id, body.departments
            )

        if body.name is not None and len(body.name) == 0:
            raise WrongParameterException("Name cannot be empty.")

        metadata_descriptors_service.check_metadata_descriptor_data_type(
            body.data_type
        )

        return metadata_descriptors_service.update_metadata_descriptor(
            metadata_descriptor_id, args
        )

    @jwt_required()
    @swag_from(SPECS["ProductionMetadataDescriptorResource_delete"])
    def delete(self, project_id, metadata_descriptor_id):
        """
        Delete metadata descriptor
        """
        # The route checks the rights on the project of the path: a descriptor
        # of another project must not be reachable through that path.
        descriptor = (
            metadata_descriptors_service.get_project_metadata_descriptor(
                project_id, metadata_descriptor_id
            )
        )
        permissions_service.check_all_departments_access(
            project_id, descriptor["departments"]
        )
        metadata_descriptors_service.remove_metadata_descriptor(
            metadata_descriptor_id
        )
        return "", 204


class ProductionMetadataDescriptorsReorderResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from(SPECS["ProductionMetadataDescriptorsReorderResource_post"])
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

        return metadata_descriptors_service.reorder_metadata_descriptors(
            project_id, body.entity_type, body.descriptor_ids
        )


def _accessible_open_project_ids():
    """
    Return the IDs of the open projects that the current user can manage. For
    an admin, return all the open projects. For the other users, return the
    team projects where their effective role is manager.

    Membership alone is not enough. A role on the team link replaces the global
    role. Without this check, a person who is manager globally and user on a
    production can change its metadata through these routes. The routes of one
    project refuse this.
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
    @swag_from(SPECS["AllProjectsMetadataDescriptorsResource_post"])
    def post(self):
        """
        Create a metadata descriptor on all accessible projects
        """
        permissions.check_manager_permissions()
        body = validation.validate_request_body(MetadataDescriptorSchema)
        _check_metadata_entity_type(body.entity_type)
        metadata_descriptors_service.check_metadata_descriptor_data_type(
            body.data_type
        )
        return (
            metadata_descriptors_service.add_metadata_descriptor_to_projects(
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
    @swag_from(SPECS["AllProjectsMetadataDescriptorResource_put"])
    def put(self, field_name):
        """
        Update a metadata descriptor on all accessible projects
        """
        permissions.check_manager_permissions()
        body = validation.validate_request_body(
            AllProjectsMetadataDescriptorUpdateSchema
        )
        _check_metadata_entity_type(body.entity_type)
        changes = body.model_dump(exclude_unset=True, exclude={"entity_type"})
        if "data_type" in changes:
            metadata_descriptors_service.check_metadata_descriptor_data_type(
                changes["data_type"]
            )
        return metadata_descriptors_service.update_metadata_descriptor_on_projects(
            _accessible_open_project_ids(),
            body.entity_type,
            field_name,
            changes,
        )

    @jwt_required()
    @swag_from(SPECS["AllProjectsMetadataDescriptorResource_delete"])
    def delete(self, field_name):
        """
        Delete a metadata descriptor from all accessible projects
        """
        permissions.check_manager_permissions()
        entity_type = self.get_text_parameter("entity_type")
        _check_metadata_entity_type(entity_type)
        return metadata_descriptors_service.remove_metadata_descriptor_from_projects(
            _accessible_open_project_ids(), entity_type, field_name
        )


class AllProjectsMetadataDescriptorsReorderResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["AllProjectsMetadataDescriptorsReorderResource_post"])
    def post(self):
        """
        Reorder metadata descriptors on all accessible projects
        """
        permissions.check_manager_permissions()
        body = validation.validate_request_body(
            AllProjectsMetadataDescriptorOrderSchema
        )
        _check_metadata_entity_type(body.entity_type)
        return metadata_descriptors_service.reorder_metadata_descriptors_on_projects(
            _accessible_open_project_ids(),
            body.entity_type,
            body.field_order,
        )


class ProductionTimeSpentsResource(MethodView, ArgsMixin):
    """
    Get the time spents of the given production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTimeSpentsResource_get"])
    def get(self, project_id):
        """
        Get production time spents
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_client()
        permissions_service.block_access_to_vendor()
        return time_spents_service.get_time_spents_for_project(
            project_id, **self.get_paging()
        )


class ProductionMilestonesResource(MethodView):
    """
    Get the milestones of the given production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionMilestonesResource_get"])
    def get(self, project_id):
        """
        Get production milestones
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_client()
        return schedule_service.get_milestones_for_project(project_id)


class ProductionScheduleItemsResource(MethodView):
    """
    Get the schedule items of the given production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionScheduleItemsResource_get"])
    def get(self, project_id):
        """
        Get production schedule items
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_client()
        permissions_service.block_access_to_vendor()
        return schedule_service.get_schedule_items(project_id)


class ProductionTaskTypeScheduleItemsResource(MethodView):
    """
    Get the schedule items of the task types of the given production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTaskTypeScheduleItemsResource_get"])
    def get(self, project_id):
        """
        Get production task type schedule items
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()
        return schedule_service.get_task_types_schedule_items(project_id)


class ProductionAssetTypesScheduleItemsResource(MethodView, ArgsMixin):
    """
    Get the schedule items of the asset types for the given task type.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionAssetTypesScheduleItemsResource_get"])
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
    Get the schedule items of the episodes for the given task type.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionEpisodesScheduleItemsResource_get"])
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
    Get the schedule items of the sequences for the given task type.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionSequencesScheduleItemsResource_get"])
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
    Get the schedule items of the edits for the given task type.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionEditsScheduleItemsResource_get"])
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
    @swag_from(SPECS["ProductionBudgetsResource_get"])
    def get(self, project_id):
        """
        Get production budgets
        """
        permissions_service.check_manager_project_access(project_id)
        self.check_id_parameter(project_id)
        return budget_service.get_budgets(project_id)

    @jwt_required()
    @swag_from(SPECS["ProductionBudgetsResource_post"])
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
    Get, update or delete a budget of the given production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionBudgetResource_get"])
    def get(self, project_id, budget_id):
        """
        Get budget
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        permissions_service.check_manager_project_access(project_id)
        return budget_service.get_budget(budget_id, project_id)

    @jwt_required()
    @swag_from(SPECS["ProductionBudgetResource_put"])
    def put(self, project_id, budget_id):
        """
        Update budget
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        permissions_service.check_manager_project_access(project_id)
        budget_service.get_budget(budget_id, project_id)
        body = validation.validate_request_body(BudgetUpdateSchema)
        return budget_service.update_budget(
            budget_id, name=body.name, currency=body.currency
        )

    @jwt_required()
    @swag_from(SPECS["ProductionBudgetResource_delete"])
    def delete(self, project_id, budget_id):
        """
        Delete budget
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        permissions_service.check_manager_project_access(project_id)
        budget_service.get_budget(budget_id, project_id)
        budget_service.delete_budget(budget_id)
        return "", 204


class ProductionBudgetEntriesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from(SPECS["ProductionBudgetEntriesResource_get"])
    def get(self, project_id, budget_id):
        """
        Get budget entries
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        permissions_service.check_manager_project_access(project_id)
        budget_service.get_budget(budget_id, project_id)
        return budget_service.get_budget_entries(budget_id)

    @jwt_required()
    @swag_from(SPECS["ProductionBudgetEntriesResource_post"])
    def post(self, project_id, budget_id):
        """
        Create budget entry
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        permissions_service.check_manager_project_access(project_id)
        budget_service.get_budget(budget_id, project_id)
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
    @swag_from(SPECS["ProductionBudgetEntryResource_get"])
    def get(self, project_id, budget_id, entry_id):
        """
        Get budget entry
        """
        permissions_service.check_manager_project_access(project_id)
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        self.check_id_parameter(entry_id)
        budget_service.get_budget(budget_id, project_id)
        return budget_service.get_budget_entry(entry_id, budget_id)

    @jwt_required()
    @swag_from(SPECS["ProductionBudgetEntryResource_put"])
    def put(self, project_id, budget_id, entry_id):
        """
        Update budget entry
        """
        permissions_service.check_manager_project_access(project_id)
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        self.check_id_parameter(entry_id)
        budget_service.get_budget(budget_id, project_id)
        budget_service.get_budget_entry(entry_id, budget_id)
        body = validation.validate_request_body(BudgetEntryUpdateSchema)
        return budget_service.update_budget_entry(
            entry_id, body.model_dump(exclude_unset=True)
        )

    @jwt_required()
    @swag_from(SPECS["ProductionBudgetEntryResource_delete"])
    def delete(self, project_id, budget_id, entry_id):
        """
        Delete budget entry
        """
        self.check_id_parameter(project_id)
        self.check_id_parameter(budget_id)
        self.check_id_parameter(entry_id)
        permissions_service.check_manager_project_access(project_id)
        budget_service.get_budget(budget_id, project_id)
        budget_service.get_budget_entry(entry_id, budget_id)
        budget_service.delete_budget_entry(entry_id)
        return "", 204


class ProductionMonthTimeSpentsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from(SPECS["ProductionMonthTimeSpentsResource_get"])
    def get(self, project_id):
        """
        Get production month time spents
        """
        permissions.check_admin_permissions()
        self.check_id_parameter(project_id)
        return time_spents_service.get_project_month_time_spents(project_id)


class ProductionScheduleVersionTaskLinksResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from(SPECS["ProductionScheduleVersionTaskLinksResource_get"])
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
        SPECS["ProductionScheduleVersionSetTaskLinksFromTasksResource_post"]
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
        SPECS["ProductionScheduleVersionApplyToProductionResource_post"]
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
        SPECS[
            "ProductionScheduleVersionSetTaskLinksFromProductionScheduleVersionResource_post"
        ]
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
    Get the time spents for a task type of the production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionTaskTypesTimeSpentsResource_get"])
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
    Get all the day offs of a production.
    """

    @jwt_required()
    @swag_from(SPECS["ProductionDayOffsResource_get"])
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
