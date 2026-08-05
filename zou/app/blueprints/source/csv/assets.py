from zou.app.blueprints.source.csv.base import (
    BaseCsvProjectImportResource,
    RowException,
)
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task_type import TaskType

from zou.app.services import (
    assets_service,
    projects_service,
    shots_service,
    persons_service,
    comments_service,
    index_service,
    tasks_service,
)
from zou.app.models.entity import Entity
from zou.app.services.exception import WrongParameterException
from zou.app.utils import events


class AssetsCsvImportResource(BaseCsvProjectImportResource):
    def post(self, project_id):
        """
        Import assets csv
        ---
        tags:
          - Import
        description: Import project assets from a CSV file. Creates or updates
          assets based on CSV rows. Supports metadata descriptors and task
          status updates.
        consumes:
          - multipart/form-data
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: update
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Whether to update existing assets
          - in: formData
            name: file
            type: file
            required: true
            description: CSV file with asset data
        responses:
            201:
              description: Assets imported successfully
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
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: Character A
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        entity_type_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        description:
                          type: string
                          example: Main character asset
            400:
              description: Invalid CSV format or missing required columns
        """
        return super().post(project_id)

    def prepare_import(self, project_id):
        self.episodes = {}
        self.entity_types = {}
        self.descriptor_fields = self.get_descriptor_field_map(
            project_id, "Asset"
        )
        project = projects_service.get_project(project_id)
        self.is_tv_show = projects_service.is_tv_show(project)
        if self.is_tv_show:
            episodes = shots_service.get_episodes_for_project(project_id)
            self.episodes = {
                episode["name"]: episode["id"] for episode in episodes
            }
        self.task_types_in_project_for_assets = (
            TaskType.query.join(ProjectTaskTypeLink)
            .filter(ProjectTaskTypeLink.project_id == project_id)
            .filter(TaskType.for_entity == "Asset")
            .all()
        )
        self.task_type_ids_in_project_for_assets = [
            str(task_type.id)
            for task_type in self.task_types_in_project_for_assets
        ]
        self.task_types_for_asset_type = {}
        self.task_statuses = {
            status["id"]: [status[n].lower() for n in ("name", "short_name")]
            for status in tasks_service.get_task_statuses()
        }
        self.current_user_id = persons_service.get_current_user()["id"]
        self.task_types_for_ready_for_map = {
            task_type.name: str(task_type.id)
            for task_type in TaskType.query.join(ProjectTaskTypeLink)
            .filter(ProjectTaskTypeLink.project_id == project_id)
            .filter(TaskType.for_entity == "Shot")
            .all()
        }

    def get_tasks_update(self, row):
        tasks_update = []
        for task_type in self.task_types_in_project_for_assets:
            task_status_name = row.get(task_type.name, None)
            task_status_id = None
            if task_status_name not in [None, ""]:
                for status_id, status_names in self.task_statuses.items():
                    if task_status_name.lower() in status_names:
                        task_status_id = status_id
                        break
                if task_status_id is None:
                    raise RowException(
                        f"Task status not found for {task_status_name}"
                    )

            task_comment_text = row.get(f"{task_type.name} comment", None)

            if task_status_id is not None or task_comment_text not in [
                None,
                "",
            ]:
                tasks_update.append(
                    {
                        "task_type_id": str(task_type.id),
                        "task_status_id": task_status_id,
                        "comment": task_comment_text,
                    }
                )

        return tasks_update

    def create_missing_tasks(self, entity, tasks_map=None):
        """
        Create the workflow tasks the entity does not have yet, each at the
        default status, and return the map of task type id to task. This
        runs for every row, including the ones whose task columns are all
        empty: those are exactly the tasks the import must initialize.
        """
        if tasks_map is None:
            tasks_map = {
                task["task_type_id"]: task
                for task in tasks_service.get_tasks_for_asset(str(entity.id))
            }
        entity_dict = entity.serialize()
        for task_type_id in self.get_task_types_for_asset_type(
            entity.entity_type_id
        ):
            if task_type_id not in tasks_map:
                task = tasks_service.create_task(
                    {"id": task_type_id}, entity_dict
                )
                if task is not None:
                    tasks_map[task_type_id] = task
        return tasks_map

    def create_and_update_tasks(
        self, tasks_update, entity, asset_creation=False
    ):
        """
        Create the workflow tasks of the entity, then apply the statuses and
        comments read from the row.
        """
        tasks_map = self.create_missing_tasks(
            entity, {} if asset_creation else None
        )

        for task_update in tasks_update:
            task_type_id = task_update["task_type_id"]
            if task_type_id not in tasks_map:
                # The column names a task type outside the asset type
                # workflow: the explicit status still creates its task.
                task = tasks_service.create_task(
                    tasks_service.get_task_type(task_type_id),
                    entity.serialize(),
                )
                if task is None:
                    continue
                tasks_map[task_type_id] = task
            task = tasks_map[task_type_id]
            if (
                task_update["comment"] is not None
                or task_update["task_status_id"] != task["task_status_id"]
            ):
                try:
                    comments_service.create_comment(
                        self.current_user_id,
                        task["id"],
                        task_update["task_status_id"]
                        or task["task_status_id"],
                        task_update["comment"] or "",
                        [],
                        {},
                        "",
                    )
                except WrongParameterException:
                    pass

    def import_row(self, row, project_id):
        asset_name = row["Name"]
        entity_type_name = row["Type"]
        if entity_type_name is None or not entity_type_name.strip():
            # get_or_create_asset_type matches names exactly, so an empty
            # cell used to create an asset type named "" that every later
            # empty row then reused.
            raise RowException("An asset type is required in the Type column")
        episode_name = row.get("Episode", None)
        episode_id = None

        if self.is_tv_show:
            if episode_name not in [None, "MP"] + list(self.episodes.keys()):
                self.episodes[episode_name] = shots_service.create_episode(
                    project_id, episode_name, created_by=self.current_user_id
                )["id"]
            episode_id = self.episodes.get(episode_name, None)
        elif episode_name is not None:
            raise RowException(
                "An episode column is present for a production that isn't a TV Show"
            )

        self.add_to_cache_if_absent(
            self.entity_types,
            assets_service.get_or_create_asset_type,
            entity_type_name,
        )
        entity_type_id = self.get_id_from_cache(
            self.entity_types, entity_type_name
        )

        asset_values = {
            "name": asset_name,
            "project_id": project_id,
            "entity_type_id": entity_type_id,
            "source_id": episode_id,
        }

        entity = Entity.get_by(
            **{
                "name": asset_values["name"],
                "project_id": asset_values["project_id"],
            }
        )

        asset_new_values = {}

        description = row.get("Description", None)
        if description is not None:
            asset_new_values["description"] = description

        data = {} if entity is None else entity.data

        resolution = row.get("Resolution", None)
        if resolution is not None:
            data = {**(data or {}), "resolution": resolution}

        asset_new_values["data"] = self.get_descriptor_values(row, data)

        ready_for = row.get("Ready for", None)
        if ready_for is not None:
            if ready_for == "":
                asset_new_values["ready_for"] = None
            else:
                try:
                    asset_new_values["ready_for"] = (
                        self.task_types_for_ready_for_map[ready_for]
                    )
                except KeyError:
                    raise RowException(f"Task type not found for {ready_for}")

        tasks_update = self.get_tasks_update(row)

        if entity is None:
            entity = Entity.create(
                **{**asset_values, **asset_new_values},
                created_by=self.current_user_id,
            )

            index_service.index_asset(entity)
            events.emit(
                "asset:new",
                {"asset_id": str(entity.id), "episode_id": episode_id},
                project_id=project_id,
            )

            self.create_and_update_tasks(
                tasks_update, entity, asset_creation=True
            )

        elif self.is_update:
            entity.update({**asset_values, **asset_new_values})

            index_service.remove_asset_index(entity.id)
            index_service.index_asset(entity)
            events.emit(
                "asset:update",
                {"asset_id": str(entity.id), "episode_id": episode_id},
                project_id=project_id,
            )

            self.create_and_update_tasks(
                tasks_update, entity, asset_creation=False
            )

        else:
            # The asset is left untouched, but a re-import is the documented
            # way to repair a production whose assets miss their tasks.
            self.create_missing_tasks(entity)

        return entity.serialize()

    def get_task_types_for_asset_type(self, asset_type_id):
        """
        Return the ids of the task types to create for a given asset type:
        the ones enabled on the project, narrowed by the asset type workflow
        when it defines one. Memoized on the resource instance only: the
        result depends on the project being imported, which a cache key
        built from the arguments alone cannot express.
        """
        asset_type_id = str(asset_type_id)
        if asset_type_id not in self.task_types_for_asset_type:
            task_type_ids = self.task_type_ids_in_project_for_assets
            asset_type = assets_service.get_asset_type(asset_type_id)
            type_task_type_ids = asset_type["task_types"]
            if len(type_task_type_ids) > 0:
                type_task_types_map = {
                    task_type_id: True for task_type_id in type_task_type_ids
                }
                task_type_ids = [
                    task_type_id
                    for task_type_id in task_type_ids
                    if task_type_id in type_task_types_map
                ]
            self.task_types_for_asset_type[asset_type_id] = task_type_ids
        return self.task_types_for_asset_type[asset_type_id]
