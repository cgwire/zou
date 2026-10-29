from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.blueprints.concepts.schemas import (
    ConceptFolderSchema,
    MoveConceptsSchema,
    NewConceptSchema,
)
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    cascade_deletion_service,
    concepts_service,
    permissions_service,
    persons_service,
    playlists_service,
    projects_service,
    tasks_service,
)
from zou.app.utils import permissions, query, validation
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class ConceptResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from(SPECS["ConceptResource_get"])
    def get(self, concept_id):
        """
        Get concept
        """
        concept = concepts_service.get_full_concept(concept_id)
        permissions_service.check_project_access(concept["project_id"])
        permissions_service.check_entity_access(concept["id"])
        if permissions.has_client_permissions():
            raise permissions.PermissionDenied
        return concept

    @jwt_required()
    @swag_from(SPECS["ConceptResource_delete"])
    def delete(self, concept_id):
        """
        Delete concept
        """
        force = self.get_force()
        concept = concepts_service.get_concept(concept_id)
        permissions_service.check_entity_delete_access(concept, force=force)
        cascade_deletion_service.remove_concept(concept_id, force=force)
        return "", 204


class AllConceptsResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["AllConceptsResource_get"])
    def get(self):
        """
        Get all concepts
        """
        criterions = query.get_query_criterions_from_request(request)
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        return concepts_service.get_concepts(criterions)


class ConceptTaskTypesResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["ConceptTaskTypesResource_get"])
    def get(self, concept_id):
        """
        Get concept task types
        """
        concept = concepts_service.get_concept(concept_id)
        permissions_service.check_project_access(concept["project_id"])
        permissions_service.check_entity_access(concept["id"])
        if permissions.has_client_permissions():
            raise permissions.PermissionDenied
        return tasks_service.get_task_types_for_concept(concept_id)


class ConceptTasksResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from(SPECS["ConceptTasksResource_get"])
    def get(self, concept_id):
        """
        Get concept tasks
        """
        concept = concepts_service.get_concept(concept_id)
        permissions_service.check_project_access(concept["project_id"])
        permissions_service.check_entity_access(concept["id"])
        if permissions.has_client_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_tasks_for_concept(
            concept_id, relations=relations
        )


class ConceptPreviewsResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["ConceptPreviewsResource_get"])
    def get(self, concept_id):
        """
        Get concept previews
        """
        concept = concepts_service.get_concept(concept_id)
        permissions_service.check_project_access(concept["project_id"])
        permissions_service.check_entity_access(concept["id"])
        if permissions.has_client_permissions():
            raise permissions.PermissionDenied
        return playlists_service.get_entity_previews_by_task_type(concept_id)


class ConceptsAndTasksResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["ConceptsAndTasksResource_get"])
    def get(self):
        """
        Get concepts and tasks
        """
        criterions = query.get_query_criterions_from_request(request)
        query.check_criterion_id_format(criterions, ["id", "project_id"])
        permissions_service.check_project_access(
            criterions.get("project_id", None)
        )
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        return concepts_service.get_concepts_and_tasks(criterions)


class ProjectConceptsResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from(SPECS["ProjectConceptsResource_get"])
    def get(self, project_id):
        """
        Get project concepts
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        return concepts_service.get_concepts_for_project(project_id)

    @jwt_required()
    @swag_from(SPECS["ProjectConceptsResource_post"])
    def post(self, project_id):
        """
        Create concept
        """
        body = validation.validate_request_body(NewConceptSchema)
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied

        concept = concepts_service.create_concept(
            project_id,
            body.name,
            data=body.data,
            description=body.description,
            entity_concept_links=body.entity_concept_links,
            created_by=persons_service.get_current_user()["id"],
            parent_id=body.parent_id,
        )
        return concept, 201


class ProjectConceptFoldersResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["ProjectConceptFoldersResource_get"])
    def get(self, project_id):
        """
        Get project concept folders
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        return concepts_service.get_concept_folders_for_project(project_id)

    @jwt_required()
    @swag_from(SPECS["ProjectConceptFoldersResource_post"])
    def post(self, project_id):
        """
        Create concept folder
        """
        body = validation.validate_request_body(ConceptFolderSchema)
        projects_service.get_project(project_id)
        permissions_service.check_supervisor_project_access(project_id)
        concept_folder = concepts_service.create_concept_folder(
            project_id,
            body.name,
            created_by=persons_service.get_current_user()["id"],
        )
        return concept_folder, 201


class ConceptFolderResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["ConceptFolderResource_put"])
    def put(self, concept_folder_id):
        """
        Rename concept folder
        """
        body = validation.validate_request_body(ConceptFolderSchema)
        concept_folder = concepts_service.get_concept_folder(concept_folder_id)
        permissions_service.check_supervisor_project_access(
            concept_folder["project_id"]
        )
        return concepts_service.update_concept_folder(
            concept_folder_id, body.name
        )

    @jwt_required()
    @swag_from(SPECS["ConceptFolderResource_delete"])
    def delete(self, concept_folder_id):
        """
        Delete concept folder
        """
        concept_folder = concepts_service.get_concept_folder(concept_folder_id)
        permissions_service.check_supervisor_project_access(
            concept_folder["project_id"]
        )
        concepts_service.remove_concept_folder(concept_folder_id)
        return "", 204


class MoveConceptsResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["MoveConceptsResource_post"])
    def post(self, project_id):
        """
        Move concepts to a concept folder
        """
        body = validation.validate_request_body(MoveConceptsSchema)
        projects_service.get_project(project_id)
        permissions_service.check_supervisor_project_access(project_id)
        return concepts_service.move_concepts(
            project_id, body.concept_ids, body.concept_folder_id
        )
