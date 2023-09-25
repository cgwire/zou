from zou.app.blueprints.source.csv.base import (
    BaseCsvProjectImportResource,
    RowException,
)
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task_type import TaskType

from zou.app.services import assets_service, projects_service, shots_service
from zou.app.models.entity import Entity
from zou.app.services import comments_service, index_service, tasks_service
from zou.app.services.persons_service import get_current_user
from zou.app.services.exception import WrongParameterException
from zou.app.utils import events, cache


class AssetsCsvImportResource(BaseCsvProjectImportResource):
    def post(self, project_id, **kwargs):
        """
        Import project assets via a .csv file.
        ---
        tags:
          - Import
        consumes:
          - multipart/form-data
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            type: file
            required: true
        responses:
            201:
                description: The lists of imported assets.
            400:
                description: The .csv file is not properly formatted.
        """
        return super().post(project_id, **kwargs)

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
        self.created_assets = []
        self.task_types_in_project_for_assets = (
            TaskType.query.join(ProjectTaskTypeLink)
            .filter(ProjectTaskTypeLink.project_id == project_id)
            .filter(TaskType.for_entity == "Asset")
        )
        self.task_statuses = {
            status["id"]: [status[n].lower() for n in ("name", "short_name")]
            for status in tasks_service.get_task_statuses()
        }
        self.current_user_id = get_current_user()["id"]
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
                        "Task status not found for %s" % task_status_name
                    )

            task_comment_text = row.get("%s comment" % task_type.name, None)

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

    def create_and_update_tasks(
        self, tasks_update, entity, asset_creation=False
    ):
        if tasks_update:
            tasks_map = {}
            if asset_creation:
                task_type_ids = self.get_task_types_for_asset_type(
                    entity.entity_type_id
                )
                for task_type_id in task_type_ids:
                    task = tasks_service.create_task(
                        {"id": task_type_id}, entity.serialize()
                    )
                    tasks_map[task_type_id] = task
            else:
                for task in tasks_service.get_tasks_for_asset(str(entity.id)):
                    tasks_map[task["task_type_id"]] = task

            for task_update in tasks_update:
                if task_update["task_type_id"] not in tasks_map:
                    task = tasks_service.create_task(
                        tasks_service.get_task_type(
                            task_update["task_type_id"]
                        ),
                        entity.serialize(),
                    )
                    tasks_map[task_update["task_type_id"]] = task
                task = tasks_map[task_update["task_type_id"]]
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
        elif asset_creation:
            self.created_assets.append(entity.serialize())

    def import_row(self, row, project_id):
        asset_name = row["Name"]
        entity_type_name = row["Type"]
        episode_name = row.get("Episode", None)
        episode_id = None

        if self.is_tv_show:
            if episode_name not in [None, "MP"] + list(self.episodes.keys()):
                self.episodes[
                    episode_name
                ] = shots_service.get_or_create_episode(
                    project_id, episode_name
                )[
                    "id"
                ]
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

        if entity is None or not entity.data:
            asset_new_values["data"] = {}
        else:
            asset_new_values["data"] = entity.data.copy()

        for name, field_name in self.descriptor_fields.items():
            if name in row:
                asset_new_values["data"][field_name] = row[name]

        ready_for = row.get("Ready for", None)
        if ready_for is not None:
            if ready_for == "":
                asset_new_values["ready_for"] = None
            else:
                try:
                    asset_new_values[
                        "ready_for"
                    ] = self.task_types_for_ready_for_map[ready_for]
                except KeyError:
                    raise RowException(
                        "Task type not found for %s" % ready_for
                    )

        tasks_update = self.get_tasks_update(row)

        if entity is None:
            entity = Entity.create(**{**asset_values, **asset_new_values})

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
        return entity.serialize()

    @cache.memoize_function(10)
    def get_task_types_for_asset_type(self, asset_type_id):
        task_type_ids = [
            str(task_type.id)
            for task_type in self.task_types_in_project_for_assets
        ]
        asset_type = assets_service.get_asset_type(asset_type_id)
        type_task_type_ids = asset_type["task_types"]
        type_task_types_map = {
            task_type_id: True for task_type_id in type_task_type_ids
        }
        if len(type_task_type_ids) > 0:
            task_type_ids = [
                task_type_id
                for task_type_id in task_type_ids
                if task_type_id in type_task_types_map
            ]
        return task_type_ids

    def run_import(self, project_id, file_path):
        entities = super().run_import(project_id, file_path)
        for asset in entities:
            task_type_ids = self.get_task_types_for_asset_type(
                asset["entity_type_id"]
            )
            for task_type_id in task_type_ids:
                tasks_service.create_tasks({"id": task_type_id}, [asset])
        return entities
