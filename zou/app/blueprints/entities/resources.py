from flask.views import MethodView

from flask_jwt_extended import jwt_required

from zou.app.blueprints.entities.schemas import CreateEntityTasksSchema
from zou.app.services import (
    assets_service,
    concepts_service,
    edits_service,
    entities_service,
    news_service,
    persons_service,
    preview_files_service,
    projects_service,
    shots_service,
    tasks_service,
    time_spents_service,
    user_service,
)
from zou.app.services.exception import WrongParameterException
from zou.app.utils import permissions, validation


class EntityNewsResource(MethodView):
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
        user_service.check_entity_access(entity_id)
        return news_service.get_news_for_entity(entity_id)


class EntityPreviewFilesResource(MethodView):
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
        user_service.check_entity_access(entity_id)
        return preview_files_service.get_preview_files_for_entity(entity_id)


class EntityTimeSpentsResource(MethodView):
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
        user_service.check_entity_access(entity_id)
        return time_spents_service.get_time_spents_for_entity(entity_id)


class EntitiesLinkedWithTasksResource(MethodView):
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


class EntityTaskCreationResource(MethodView):
    @jwt_required()
    def post(self, entity_id):
        """
        Create tasks for an entity
        ---
        description: Create one task per provided task type for the given
          entity. Each task type is validated against the entity's project
          and (for assets) the entity's asset type workflow. When
          task_type_ids is omitted or empty, default to every task type
          valid for the entity (project workflow, asset-type workflow if
          asset, and matching for_entity). Existing tasks for the same
          (entity, task_type) pair are skipped.
        tags:
          - Entities
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Unique identifier of the entity
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: false
          content:
            application/json:
              schema:
                type: object
                properties:
                  task_type_ids:
                    type: array
                    items:
                      type: string
                      format: uuid
                    description: Optional list of task type IDs to create.
                      Omit or pass an empty list to default to every task
                      type valid for the entity.
                example:
                  task_type_ids:
                    - b24a6ea4-ce75-4665-a070-57453082c25
        responses:
          201:
            description: Created tasks
          400:
            description: A task type is not enabled in the project, not in
              the asset type workflow, or does not target this kind of
              entity
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity_id)
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        body = validation.validate_request_body(CreateEntityTasksSchema)
        task_types = [
            tasks_service.get_task_type(task_type_id)
            for task_type_id in body.task_type_ids
        ]
        tasks = tasks_service.create_tasks_for_entity(entity, task_types)
        return tasks, 201


class ProjectDeleteEntitiesResource(MethodView):
    @jwt_required()
    def post(self, project_id):
        """
        Delete entities batch
        ---
        description: Delete assets, shots, edits and concepts given by id
          list in a single request. Each entity follows the same rules as
          its single deletion route. Entities with tasks are marked as
          canceled on first deletion, then removed for real when already
          canceled; concepts are always removed. Only entity creators or
          project managers can delete entities.
        tags:
          - Entities
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Unique identifier of the project
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: array
                items:
                  type: string
                  format: uuid
                description: Entity unique identifiers to delete
        responses:
          200:
            description: Deleted entity ids
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: string
                    format: uuid
          400:
            description: An entity does not belong to the project or is
              not an asset, a shot, an edit or a concept
        """
        projects_service.get_project(project_id)
        entity_ids = validation.validate_id_list()
        current_user_id = persons_service.get_current_user()["id"]

        shot_type_id = shots_service.get_shot_type()["id"]
        edit_type_id = edits_service.get_edit_type()["id"]
        concept_type_id = concepts_service.get_concept_type()["id"]

        # Validate every entity before removing anything.
        to_remove = []
        for entity_id in entity_ids:
            entity = entities_service.get_entity(entity_id)
            if entity["project_id"] != project_id:
                raise WrongParameterException(
                    f"Entity {entity_id} does not belong to project "
                    f"{project_id}."
                )
            if entity["created_by"] == current_user_id:
                user_service.check_belong_to_project(project_id)
            else:
                user_service.check_manager_project_access(project_id)

            entity_type_id = entity["entity_type_id"]
            if entity_type_id == shot_type_id:
                remove = shots_service.remove_shot
                force = entity["canceled"]
            elif entity_type_id == edit_type_id:
                remove = edits_service.remove_edit
                force = entity["canceled"]
            elif entity_type_id == concept_type_id:
                remove = concepts_service.remove_concept
                force = True
            elif assets_service.is_asset_dict(entity):
                remove = assets_service.remove_asset
                force = entity["canceled"]
            else:
                raise WrongParameterException(
                    f"Entity {entity_id} is not an asset, a shot, an edit "
                    f"or a concept."
                )
            to_remove.append((entity_id, remove, force))

        for entity_id, remove, force in to_remove:
            remove(entity_id, force=force)
        return entity_ids, 200
