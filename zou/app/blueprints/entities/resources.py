from flask_restful import Resource

from flask_jwt_extended import jwt_required

from zou.app.services import (
    entities_service,
    news_service,
    preview_files_service,
    time_spents_service,
    user_service,
)


class EntityNewsResource(Resource):
    @jwt_required()
    def get(self, entity_id):
        """
        Get entity news
        ---
        description: Retrieve all news entries that are linked to a specific
          entity.
        tags:
          - Entities
        parameters:
          - in: path
            name: entity_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the entity
        responses:
          200:
            description: List of entity news successfully retrieved
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
                        description: News unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      change:
                        type: boolean
                        description: Whether this news represents a change
                        example: true
                      author_id:
                        type: string
                        format: uuid
                        description: Author person identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      comment_id:
                        type: string
                        format: uuid
                        description: Comment identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      task_id:
                        type: string
                        format: uuid
                        description: Task identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      preview_file_id:
                        type: string
                        format: uuid
                        description: Preview file identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
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
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return news_service.get_news_for_entity(entity_id)


class EntityPreviewFilesResource(Resource):
    @jwt_required()
    def get(self, entity_id):
        """
        Get entity preview files
        ---
        description: Retrieve all preview files that are linked to a specific
          entity. This includes images, videos, and other preview media
          associated with the entity.
        tags:
          - Entities
        parameters:
          - in: path
            name: entity_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the entity
        responses:
          200:
            description: List of entity preview files successfully retrieved
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
                        description: Preview file unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Preview file name
                        example: "preview_001.jpg"
                      path:
                        type: string
                        description: File path
                        example: "/previews/entity/preview_001.jpg"
                      revision:
                        type: integer
                        description: File revision number
                        example: 1
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      entity_id:
                        type: string
                        format: uuid
                        description: Entity identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      task_id:
                        type: string
                        format: uuid
                        description: Task identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return preview_files_service.get_preview_files_for_entity(entity_id)


class EntityTimeSpentsResource(Resource):
    @jwt_required()
    def get(self, entity_id):
        """
        Get entity time spent
        ---
        description: Retrieve all time spent entries that are linked to a
          specific entity.
        tags:
          - Entities
        parameters:
          - in: path
            name: entity_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the entity
        responses:
          200:
            description: List of entity time spent entries successfully retrieved
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
                        description: Time spent unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      duration:
                        type: number
                        format: float
                        description: Time duration in hours
                        example: 2.5
                      date:
                        type: string
                        format: date
                        description: Date when time was spent
                        example: "2023-12-07"
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      person_id:
                        type: string
                        format: uuid
                        description: Person identifier who spent the time
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      entity_id:
                        type: string
                        format: uuid
                        description: Entity identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return time_spents_service.get_time_spents_for_entity(entity_id)


class EntitiesLinkedWithTasksResource(Resource):
    @jwt_required()
    def get(self, entity_id):
        """
        Get linked entities
        ---
        description: Retrieve all entities that are linked to a specific entity
          along with their associated tasks. This includes related entities,
          dependencies, and hierarchical relationships.
        tags:
          - Entities
        parameters:
          - in: path
            name: entity_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the entity
        responses:
          200:
            description: List of linked entities successfully retrieved
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
                        description: Entity unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Entity name
                        example: "Character Model"
                      entity_type_id:
                        type: string
                        format: uuid
                        description: Entity type identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      parent_id:
                        type: string
                        format: uuid
                        description: Parent entity identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      tasks:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: string
                              format: uuid
                              description: Task unique identifier
                              example: e68e0ie8-gi19-8009-e514-91897426g69
                            name:
                              type: string
                              description: Task name
                              example: "Modeling Task"
                            task_type_id:
                              type: string
                              format: uuid
                              description: Task type identifier
                              example: f79f1jf9-hj20-9010-f625-02998537h80
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity_id)
        return entities_service.get_linked_entities_with_tasks(entity_id)
