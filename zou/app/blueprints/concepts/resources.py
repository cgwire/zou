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
        Get concept
        ---
        description: Retrieve detailed information about a specific concept
          including metadata, project context, and related data.
        tags:
          - Concepts
        parameters:
          - in: path
            name: concept_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the concept
        responses:
          200:
            description: Concept information successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Concept unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Concept name
                      example: "Character Design"
                    description:
                      type: string
                      description: Concept description
                      example: "Main character concept art"
                    project_id:
                      type: string
                      format: uuid
                      description: Project identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:30:00Z"
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
        Delete concept
        ---
        description: Permanently remove a concept from the system. Only concept
          creators or project managers can delete concepts.
        tags:
          - Concepts
        parameters:
          - in: path
            name: concept_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the concept to delete
          - in: query
            name: force
            type: boolean
            required: false
            description: Force deletion bypassing validation checks
            example: false
        responses:
          204:
            description: Concept successfully deleted
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
        Get all concepts
        ---
        description: Retrieve all concept entries with filtering support.
          Filters can be specified in the query string to narrow down results by
          project or parent concept.
        tags:
          - Concepts
        parameters:
          - in: query
            name: project_id
            required: false
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter concepts by specific project
          - in: query
            name: parent_id
            required: false
            type: string
            format: uuid
            example: b35b7fb5-df86-5776-b181-68564193d36
            description: Filter concepts by parent concept
        responses:
          200:
            description: List of concepts successfully retrieved
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
                        description: Concept unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Concept name
                        example: "Character Design"
                      description:
                        type: string
                        description: Concept description
                        example: "Main character concept art"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      parent_id:
                        type: string
                        format: uuid
                        description: Parent concept identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
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
        Get concept task types
        ---
        description: Retrieve all task types that are related to a specific
          concept.
        tags:
          - Concepts
        parameters:
          - in: path
            name: concept_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the concept
        responses:
          200:
            description: List of concept task types successfully retrieved
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
                        description: Task type unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      name:
                        type: string
                        description: Task type name
                        example: "Concept Art"
                      short_name:
                        type: string
                        description: Task type short name
                        example: "CON"
                      color:
                        type: string
                        description: Task type color code
                        example: "#FF5733"
                      for_entity:
                        type: string
                        description: Entity type this task type is for
                        example: "Concept"
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
        Get concept tasks
        ---
        description: Retrieve all tasks that are related to a specific concept.
        tags:
          - Concepts
        parameters:
          - in: path
            name: concept_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the concept
          - in: query
            name: relations
            type: boolean
            required: false
            description: Include related entity information
            example: true
        responses:
          200:
            description: List of concept tasks successfully retrieved
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
                        description: Task unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      name:
                        type: string
                        description: Task name
                        example: "Character Design Task"
                      task_type_id:
                        type: string
                        format: uuid
                        description: Task type identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      task_status_id:
                        type: string
                        format: uuid
                        description: Task status identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      entity_id:
                        type: string
                        format: uuid
                        description: Entity identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      assigned_to:
                        type: string
                        format: uuid
                        description: Assigned person identifier
                        example: f79f1jf9-hj20-9010-f625-02998537h80
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
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
        Get concept previews
        ---
        description: Retrieve all preview files related to a specific concept.
          Returns them as a dictionary where keys are related task type IDs and
          values are arrays of previews for that task type.
        tags:
          - Concepts
        parameters:
          - in: path
            name: concept_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the concept
        responses:
          200:
            description: Concept previews successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  additionalProperties:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          description: Preview unique identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        name:
                          type: string
                          description: Preview name
                          example: "concept_preview_01"
                        original_name:
                          type: string
                          description: Original file name
                          example: "character_concept.jpg"
                        file_path:
                          type: string
                          description: File path
                          example: "/previews/concept/concept_preview_01.jpg"
                        task_type_id:
                          type: string
                          format: uuid
                          description: Task type identifier
                          example: c46c8gc6-eg97-6887-c292-79675204e47
                        created_at:
                          type: string
                          format: date-time
                          description: Creation timestamp
                          example: "2023-01-01T12:00:00Z"
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
        Get concepts and tasks
        ---
        description: Retrieve all concepts and all related tasks included in the
          response.
        tags:
          - Concepts
        parameters:
          - in: query
            name: project_id
            required: false
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter concepts by specific project
        responses:
          200:
            description: Concepts with tasks successfully retrieved
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
                        description: Concept unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Concept name
                        example: "Character Design"
                      description:
                        type: string
                        description: Concept description
                        example: "Main character concept art"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      project_name:
                        type: string
                        description: Project name
                        example: "My Animation Project"
                      asset_type_name:
                        type: string
                        description: Asset type name
                        example: "Character"
                      tasks:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: string
                              format: uuid
                              description: Task unique identifier
                              example: c46c8gc6-eg97-6887-c292-79675204e47
                            name:
                              type: string
                              description: Task name
                              example: "Character Design Task"
                            task_type_id:
                              type: string
                              format: uuid
                              description: Task type identifier
                              example: d57d9hd7-fh08-7998-d403-80786315f58
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
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
        Get project concepts
        ---
        description: Retrieve all concepts that are related to a specific
          project.
        tags:
          - Concepts
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
        responses:
          200:
            description: List of project concepts successfully retrieved
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
                        description: Concept unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Concept name
                        example: "Character Design"
                      description:
                        type: string
                        description: Concept description
                        example: "Main character concept art"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
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
        Create concept
        ---
        description: Create a new concept for a specific project with name,
          description, and optional entity concept links.
        tags:
          - Concepts
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
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
                    description: Concept name
                    example: "Character Design"
                  description:
                    type: string
                    description: Concept description
                    example: "Main character concept art"
                  data:
                    type: object
                    description: Additional concept data
                    example: {"style": "realistic", "mood": "heroic"}
                  entity_concept_links:
                    type: array
                    items:
                      type: string
                      format: uuid
                    description: List of entity concept link identifiers
                    example: ["b35b7fb5-df86-5776-b181-68564193d36", "c46c8gc6-eg97-6887-c292-79675204e47"]
        responses:
          201:
            description: Concept successfully created
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Concept unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Concept name
                      example: "Character Design"
                    description:
                      type: string
                      description: Concept description
                      example: "Main character concept art"
                    project_id:
                      type: string
                      format: uuid
                      description: Project identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    data:
                      type: object
                      description: Additional concept data
                      example: {"style": "realistic", "mood": "heroic"}
                    created_by:
                      type: string
                      format: uuid
                      description: Creator person identifier
                      example: d57d9hd7-fh08-7998-d403-80786315f58
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:00:00Z"
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
