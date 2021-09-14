from zou.app.blueprints.source.csv.base import BaseCsvProjectImportResource
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType

from zou.app.services import assets_service, projects_service, shots_service
from zou.app.models.entity import Entity
from zou.app.services.tasks_service import create_tasks
from zou.app.utils import events


class AssetsCsvImportResource(BaseCsvProjectImportResource):
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

    def import_row(self, row, project_id):
        asset_name = row["Name"]
        entity_type_name = row["Type"]
        description = row.get("Description", "")
        episode_name = row.get("Episode", None)
        episode_id = None
        if episode_name is not None:
            if episode_name != "MP" and episode_name not in self.episodes:
                self.episodes[
                    episode_name
                ] = shots_service.get_or_create_episode(
                    project_id, episode_name
                )[
                    "id"
                ]
            episode_id = self.episodes.get(episode_name, None)

        self.add_to_cache_if_absent(
            self.entity_types,
            assets_service.get_or_create_asset_type,
            entity_type_name,
        )
        entity_type_id = self.get_id_from_cache(
            self.entity_types, entity_type_name
        )

        entity = Entity.get_by(
            name=asset_name,
            project_id=project_id,
            entity_type_id=entity_type_id,
            source_id=episode_id,
        )

        data = {}
        for name, field_name in self.descriptor_fields.items():
            if name in row:
                data[field_name] = row[name]
            elif (
                entity is not None
                and entity.data is not None
                and field_name in entity.data
            ):
                data[field_name] = entity.data[field_name]

        if entity is None:
            entity = Entity.create(
                name=asset_name,
                description=description,
                project_id=project_id,
                entity_type_id=entity_type_id,
                source_id=episode_id,
                data=data,
            )
            self.created_assets.append(entity.serialize())
            events.emit(
                "asset:new",
                {"asset_id": str(entity.id), "episode_id": episode_id},
                project_id=project_id,
            )

        elif self.is_update:
            entity.update({"description": description, "data": data})
            events.emit(
                "asset:update",
                {"asset_id": str(entity.id), "episode_id": episode_id},
                project_id=project_id,
            )

        return entity.serialize()

    def run_import(self, project_id, file_path):
        entities = super().run_import(project_id, file_path)
        task_types_in_project_for_assets = (
            TaskType.query.join(ProjectTaskTypeLink)
            .filter(ProjectTaskTypeLink.project_id == project_id)
            .filter(TaskType.for_shots == False)
        )
        for task_type in task_types_in_project_for_assets:
            create_tasks(task_type.serialize(), self.created_assets)
        return entities
