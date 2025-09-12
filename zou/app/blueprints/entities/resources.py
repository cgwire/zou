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
        Retrieve all news linked to a given entity.
        ---
        tags:
          - Entities
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: All news linked to given entity
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
                      title:
                        type: string
                      content:
                        type: string
                      created_at:
                        type: string
                        format: date-time
                      author_id:
                        type: string
                        format: uuid
                      entity_id:
                        type: string
                        format: uuid
          '404':
            description: Entity not found
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return news_service.get_news_for_entity(entity_id)


class EntityPreviewFilesResource(Resource):
    @jwt_required()
    def get(self, entity_id):
        """
        Retrieve all preview files linked to a given entity.
        ---
        tags:
          - Entities
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: All preview files linked to given entity
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
                      name:
                        type: string
                      path:
                        type: string
                      revision:
                        type: integer
                      created_at:
                        type: string
                        format: date-time
                      entity_id:
                        type: string
                        format: uuid
                      task_id:
                        type: string
                        format: uuid
          '404':
            description: Entity not found
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return preview_files_service.get_preview_files_for_entity(entity_id)


class EntityTimeSpentsResource(Resource):
    @jwt_required()
    def get(self, entity_id):
        """
        Retrieve all time spents linked to a given entity.
        ---
        tags:
          - Entities
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: All time spents linked to given entity
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
                      duration:
                        type: number
                        format: float
                        example: 2.5
                      date:
                        type: string
                        format: date
                        example: "2023-12-07"
                      created_at:
                        type: string
                        format: date-time
                      person_id:
                        type: string
                        format: uuid
                      entity_id:
                        type: string
                        format: uuid
          '404':
            description: Entity not found
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return time_spents_service.get_time_spents_for_entity(entity_id)


class EntitiesLinkedWithTasksResource(Resource):
    @jwt_required()
    def get(self, entity_id):
        """
        Resource to retrieve the entities linked on a given entity.
        ---
        tags:
          - Entities
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: Entities linked on given entity
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
                      name:
                        type: string
                      entity_type_id:
                        type: string
                        format: uuid
                      project_id:
                        type: string
                        format: uuid
                      parent_id:
                        type: string
                        format: uuid
                      tasks:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: string
                              format: uuid
                            name:
                              type: string
                            task_type_id:
                              type: string
                              format: uuid
          '404':
            description: Entity not found
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity_id)
        return entities_service.get_linked_entities_with_tasks(entity_id)
