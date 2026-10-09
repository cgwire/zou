from flasgger import swag_from
from zou.app.blueprints.source.csv.base import (
    BaseCsvProjectImportResource,
    RowException,
)

from zou.app.services import (
    edits_service,
    entities_service,
    projects_service,
    shots_service,
    persons_service,
    entity_types_service,
)
from zou.app.services.tasks_service import (
    create_task,
    create_tasks,
    get_tasks_for_edit,
)
from zou.app.services.task_types_service import (
    get_task_statuses,
    get_task_type,
)
from zou.app.services.comments_service import create_comment
from zou.app.exceptions import WrongParameterException


class EditsCsvImportResource(BaseCsvProjectImportResource):
    @swag_from("openapi/EditsCsvImportResource_post.yml")
    def post(self, project_id):
        """
        Import edits csv
        """
        return super().post(project_id)

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
        self.task_types_in_project_for_edits = (
            projects_service.get_project_task_types_raw(project_id, "Edit")
        )
        self.task_statuses = {
            status["id"]: [status[n].lower() for n in ("name", "short_name")]
            for status in get_task_statuses()
        }
        self.current_user_id = persons_service.get_current_user()["id"]

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
        # An empty cell reads as "" with DictReader: it means no episode,
        # not an episode named "".
        episode_name = (row.get("Episode") or "").strip() or None
        episode_id = None

        if self.is_tv_show:
            if episode_name is not None and episode_name not in list(
                self.episodes.keys()
            ):
                self.episodes[episode_name] = shots_service.create_episode(
                    project_id, episode_name, created_by=self.current_user_id
                )["id"]
            episode_id = self.episodes.get(episode_name, None)
        elif episode_name is not None:
            raise RowException(
                "An episode column is present for a production that isn't a TV Show"
            )

        edit_type_id = entity_types_service.get_edit_type()["id"]

        edit_values = {
            "name": edit_name,
            "project_id": project_id,
            "entity_type_id": edit_type_id,
            "parent_id": episode_id,
        }

        entity = entities_service.find_entity_raw(**edit_values)

        edit_new_values = {}

        description = row.get("Description", None)
        if description is not None:
            edit_new_values["description"] = description

        edit_new_values["data"] = self.get_descriptor_values(
            row, {} if entity is None else entity.data
        )

        tasks_update = self.get_tasks_update(row)

        if entity is None:
            edit = edits_service.create_edit(
                project_id,
                edit_name,
                data=edit_new_values["data"],
                description=edit_new_values.get("description", ""),
                parent_id=episode_id,
                created_by=self.current_user_id,
            )
            entity = entities_service.get_entity_raw(edit["id"])

            self.create_and_update_tasks(
                tasks_update, entity, edit_creation=True
            )

        elif self.is_update:
            edits_service.update_edit(str(entity.id), edit_new_values)

            self.create_and_update_tasks(
                tasks_update, entity, edit_creation=False
            )

        return entity.serialize()

    def run_import(self, file_path, project_id):
        # Set before the import: prepare_import can fail before it does.
        self.created_edits = []
        self.task_types_in_project_for_edits = []
        try:
            return super().run_import(file_path, project_id)
        finally:
            # The edits created before a failing line stay imported, and a
            # new import would not create their tasks: they get them here.
            for task_type in self.task_types_in_project_for_edits:
                create_tasks(task_type.serialize(), self.created_edits)
