from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.services import (
    projects_service,
    playlists_service,
    concepts_service,
    tasks_service,
    user_service,
    persons_service,
)

from zou.app.mixin import ArgsMixin
from zou.app.utils import query, permissions


class ConceptResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, concept_id):
        """
        Retrieve given concept.
        ---
        tags:
        - Concepts
        parameters:
          - in: path
            name: concept_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given concept
        """
        concept = concepts_service.get_full_concept(concept_id)
        if concept is None:
            concepts_service.clear_concept_cache(concept_id)
            concept = concepts_service.get_full_concept(concept_id)
        user_service.check_project_access(concept["project_id"])
        user_service.check_entity_access(concept["id"])
        if permissions.has_client_permissions():
            raise permissions.PermissionDenied
        return concept

    @jwt_required()
    def delete(self, concept_id):
        """
        Delete given concept.
        ---
        tags:
        - Concepts
        parameters:
          - in: path
            name: concept_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Given concept deleted
        """
        force = self.get_force()
        concept = concepts_service.get_concept(concept_id)
        if concept["created_by"] == persons_service.get_current_user()["id"]:
            user_service.check_belong_to_project(concept["project_id"])
        else:
            user_service.check_manager_project_access(concept["project_id"])
        concepts_service.remove_concept(concept_id, force=force)
        return "", 204


class AllConceptsResource(Resource):
    @jwt_required()
    def get(self):
        """
        Retrieve all concept entries.
        ---
        tags:
        - Concepts
        description: Filters can be specified in the query string.
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: parent_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All concept entries
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        return concepts_service.get_concepts(criterions)


class ConceptTaskTypesResource(Resource):
    @jwt_required()
    def get(self, concept_id):
        """
        Retrieve all task types related to a given concept.
        ---
        tags:
        - Concepts
        parameters:
          - in: path
            name: concept_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All task types related to given concept
        """
        concept = concepts_service.get_concept(concept_id)
        user_service.check_project_access(concept["project_id"])
        user_service.check_entity_access(concept["id"])
        if permissions.has_client_permissions():
            raise permissions.PermissionDenied
        return tasks_service.get_task_types_for_concept(concept_id)


class ConceptTasksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, concept_id):
        """
        Retrieve all tasks related to a given concept.
        ---
        tags:
        - Concepts
        parameters:
          - in: path
            name: concept_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given concept
        """
        concept = concepts_service.get_concept(concept_id)
        user_service.check_project_access(concept["project_id"])
        user_service.check_entity_access(concept["id"])
        if permissions.has_client_permissions():
            raise permissions.PermissionDenied
        relations = self.get_relations()
        return tasks_service.get_tasks_for_concept(
            concept_id, relations=relations
        )


class ConceptPreviewsResource(Resource):
    @jwt_required()
    def get(self, concept_id):
        """
        Retrieve all previews related to a given concept.
        ---
        tags:
        - Concepts
        description: It sends them as a dict.
                     Keys are related task type ids and values are arrays of preview for this task type.
        parameters:
          - in: path
            name: concept_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All previews related to given episode
        """
        concept = concepts_service.get_concept(concept_id)
        user_service.check_project_access(concept["project_id"])
        user_service.check_entity_access(concept["id"])
        if permissions.has_client_permissions():
            raise permissions.PermissionDenied
        return playlists_service.get_preview_files_for_entity(concept_id)


class ConceptsAndTasksResource(Resource):
    @jwt_required()
    def get(self):
        """
        Retrieve all concepts, adds project name and asset type name and all related tasks.
        ---
        tags:
        - Concepts
        parameters:
          - in: query
            name: project_id
            required: False
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All concepts
        """
        criterions = query.get_query_criterions_from_request(request)
        user_service.check_project_access(criterions.get("project_id", None))
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        return concepts_service.get_concepts_and_tasks(criterions)


class ProjectConceptsResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, project_id):
        """
        Retrieve all concepts related to a given project.
        ---
        tags:
        - Concepts
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All concepts related to given project
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        return concepts_service.get_concepts_for_project(
            project_id, only_assigned=permissions.has_vendor_permissions()
        )

    @jwt_required()
    def post(self, project_id):
        """
        Create a concept for given project.
        ---
        tags:
        - Concepts
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: name
            required: True
            type: string
            x-example: Name of concept
          - in: formData
            name: description
            type: string
            x-example: Description of concept
          - in: formData
            name: entity_concept_links
            type: list of UUIDs
            x-example: ["a24a6ea4-ce75-4665-a070-57453082c25"]
        responses:
            201:
                description: Concept created for given project
        """
        (name, data, description, entity_concept_links) = self.get_arguments()
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied

        concept = concepts_service.create_concept(
            project_id,
            name,
            data=data,
            description=description,
            entity_concept_links=entity_concept_links,
            created_by=persons_service.get_current_user()["id"],
        )
        return concept, 201

    def get_arguments(self):
        args = self.get_args(
            [
                {"name": "name", "required": True},
                {"name": "data", "type": dict},
                "description",
                (
                    "entity_concept_links",
                    [],
                    False,
                    str,
                    "append",
                ),
            ]
        )

        return (
            args["name"],
            args["data"],
            args["description"],
            args["entity_concept_links"],
        )
