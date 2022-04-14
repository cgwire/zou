from zou.app.blueprints.source.csv.base import BaseCsvProjectImportResource
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task_type import TaskType

from zou.app.services import edits_service, projects_service, shots_service
from zou.app.models.entity import Entity
from zou.app.services.tasks_service import create_tasks
from zou.app.utils import events


class EditsCsvImportResource(BaseCsvProjectImportResource):
    def prepare_import(self, project_id):
        self.episodes = {}
        self.entity_types = {}
        self.descriptor_fields = self.get_descriptor_field_map(
            project_id, "Edit"
        )
        project = projects_service.get_project(project_id)
        self.is_tv_show = projects_service.is_tv_show(project)
        if self.is_tv_show:
            episodes = shots_service.get_episodes_for_project(project_id)
            self.episodes = {
                episode["name"]: episode["id"] for episode in episodes
            }
        self.created_edits = []

    def import_row(self, row, project_id):
        asset_name = row["Name"]
        description = row.get("Description", "")
        episode_name = row.get("Episode", None)
        episode_id = None
        if episode_name is not None:
            if episode_name not in self.episodes:
                self.episodes[
                    episode_name
                ] = shots_service.get_or_create_episode(
                    project_id, episode_name
                )[
                    "id"
                ]
            episode_id = self.episodes.get(episode_name, None)

        edit_type_id = edits_service.get_edit_type()["id"]
        entity = Entity.get_by(
            name=asset_name,
            project_id=project_id,
            entity_type_id=edit_type_id,
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
                entity_type_id=edit_type_id,
                source_id=episode_id,
                data=data,
            )
            self.created_edits.append(entity.serialize())
            events.emit(
                "edit:new",
                {"edit_id": str(entity.id), "episode_id": episode_id},
                project_id=project_id,
            )

        elif self.is_update:
            entity.update({"description": description, "data": data})
            events.emit(
                "edit:update",
                {"edit_id": str(entity.id), "episode_id": episode_id},
                project_id=project_id,
            )

        return entity.serialize()

    def run_import(self, project_id, file_path):
        entities = super().run_import(project_id, file_path)
        task_types_in_project_for_edits = (
            TaskType.query.join(ProjectTaskTypeLink)
            .filter(ProjectTaskTypeLink.project_id == project_id)
            .filter(TaskType.for_entity == "Edit")
        )
        for task_type in task_types_in_project_for_edits:
            create_tasks(task_type.serialize(), self.created_edits)
        return entities
