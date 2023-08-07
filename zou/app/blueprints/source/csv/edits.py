from zou.app.blueprints.source.csv.base import (
    BaseCsvProjectImportResource,
    RowException,
)
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task_type import TaskType

from zou.app.services import edits_service, projects_service, shots_service
from zou.app.models.entity import Entity
from zou.app.services.tasks_service import (
    create_task,
    create_tasks,
    get_tasks_for_edit,
    get_task_statuses,
    get_task_type,
)
from zou.app.services.comments_service import create_comment
from zou.app.services.persons_service import get_current_user
from zou.app.services.exception import WrongParameterException
from zou.app.utils import events


class EditsCsvImportResource(BaseCsvProjectImportResource):
    def post(self, project_id, **kwargs):
        """
        Import project edits.
        ---
        tags:
          - Import
        consumes:
          - multipart/form-data
        parameters:
          - in: formData
            name: file
            type: file
            required: true
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Edits imported
            400:
                description: Format error
        """
        return super().post(project_id, **kwargs)

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
        self.task_types_in_project_for_edits = (
            TaskType.query.join(ProjectTaskTypeLink)
            .filter(ProjectTaskTypeLink.project_id == project_id)
            .filter(TaskType.for_entity == "Edit")
        )
        self.task_statuses = {
            status["id"]: [status[n].lower() for n in ("name", "short_name")]
            for status in get_task_statuses()
        }
        self.current_user_id = get_current_user()["id"]

    def get_tasks_update(self, row):
        tasks_update = []
        for task_type in self.task_types_in_project_for_edits:
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
        self, tasks_update, entity, edit_creation=False
    ):
        if tasks_update:
            if edit_creation:
                tasks_map = {
                    str(task_type.id): create_task(
                        task_type.serialize(), entity.serialize()
                    )
                    for task_type in self.task_types_in_project_for_edits
                }
            else:
                tasks_map = {
                    task["task_type_id"]: task
                    for task in get_tasks_for_edit(str(entity.id))
                }

            for task_update in tasks_update:
                if task_update["task_type_id"] not in tasks_map:
                    tasks_map[task_update["task_type_id"]] = create_task(
                        get_task_type(task_update["task_type_id"]),
                        entity.serialize(),
                    )
                task = tasks_map[task_update["task_type_id"]]
                if (
                    task_update["comment"] is not None
                    or task_update["task_status_id"] != task["task_status_id"]
                ):
                    try:
                        create_comment(
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
        elif edit_creation:
            self.created_edits.append(entity.serialize())

    def import_row(self, row, project_id):
        edit_name = row["Name"]
        episode_name = row.get("Episode", None)
        episode_id = None

        if self.is_tv_show:
            if episode_name is not None and episode_name not in list(
                self.episodes.keys()
            ):
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

        edit_type_id = edits_service.get_edit_type()["id"]

        edit_values = {
            "name": edit_name,
            "project_id": project_id,
            "entity_type_id": edit_type_id,
            "parent_id": episode_id,
        }

        entity = Entity.get_by(**edit_values)

        edit_new_values = {}

        description = row.get("Description", None)
        if description is not None:
            edit_new_values["description"] = description

        if entity is None or not entity.data:
            edit_new_values["data"] = {}
        else:
            edit_new_values["data"] = entity.data.copy()

        for name, field_name in self.descriptor_fields.items():
            if name in row:
                edit_new_values["data"][field_name] = row[name]

        tasks_update = self.get_tasks_update(row)

        if entity is None:
            entity = Entity.create(**{**edit_values, **edit_new_values})
            events.emit(
                "edit:new",
                {"edit_id": str(entity.id), "episode_id": episode_id},
                project_id=project_id,
            )

            self.create_and_update_tasks(
                tasks_update, entity, edit_creation=True
            )

        elif self.is_update:
            entity.update(edit_new_values)
            events.emit(
                "edit:update",
                {"edit_id": str(entity.id), "episode_id": episode_id},
                project_id=project_id,
            )

            self.create_and_update_tasks(
                tasks_update, entity, edit_creation=False
            )

        return entity.serialize()

    def run_import(self, project_id, file_path):
        entities = super().run_import(project_id, file_path)
        for task_type in self.task_types_in_project_for_edits:
            create_tasks(task_type.serialize(), self.created_edits)
        return entities
