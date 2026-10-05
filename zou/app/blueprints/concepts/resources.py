from flasgger import swag_from
from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.services import (
    projects_service,
    playlists_service,
    concepts_service,
    tasks_service,
    permissions_service,
    user_service,
    persons_service,
)

from zou.app.mixin import ArgsMixin
from zou.app.utils import query, permissions, validation
from zou.app.blueprints.concepts.schemas import (
    ConceptFolderSchema,
    MoveConceptsSchema,
    NewConceptSchema,
)


class ConceptResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ConceptResource_get.yml")
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
    @swag_from("openapi/ConceptResource_delete.yml")
    def delete(self, concept_id):
        """
        Delete concept
        """
        force = self.get_force()
        concept = concepts_service.get_concept(concept_id)
        if concept["created_by"] == persons_service.get_current_user()["id"]:
            permissions_service.check_belong_to_project(concept["project_id"])
        else:
            permissions_service.check_manager_project_access(
                concept["project_id"]
            )
        concepts_service.remove_concept(concept_id, force=force)
        return "", 204


class AllConceptsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/AllConceptsResource_get.yml")
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
    @swag_from("openapi/ConceptTaskTypesResource_get.yml")
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
    @swag_from("openapi/ConceptTasksResource_get.yml")
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
    @swag_from("openapi/ConceptPreviewsResource_get.yml")
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
    @swag_from("openapi/ConceptsAndTasksResource_get.yml")
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
    @swag_from("openapi/ProjectConceptsResource_get.yml")
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
    @swag_from("openapi/ProjectConceptsResource_post.yml")
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
    @swag_from("openapi/ProjectConceptFoldersResource_get.yml")
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
    @swag_from("openapi/ProjectConceptFoldersResource_post.yml")
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
    @swag_from("openapi/ConceptFolderResource_put.yml")
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
    @swag_from("openapi/ConceptFolderResource_delete.yml")
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
    @swag_from("openapi/MoveConceptsResource_post.yml")
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
