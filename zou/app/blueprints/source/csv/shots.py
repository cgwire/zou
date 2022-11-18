from zou.app.blueprints.source.csv.base import (
    BaseCsvProjectImportResource,
    RowException,
)

from zou.app.models.entity import Entity
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task_type import TaskType
from zou.app.services import shots_service, projects_service
from zou.app.services.tasks_service import (
    create_task,
    create_tasks,
    get_tasks_for_shot,
    get_task_statuses,
    get_task_type,
)
from zou.app.services.comments_service import create_comment
from zou.app.services.persons_service import get_current_user
from zou.app.services.exception import WrongParameterException
from zou.app.utils import events


class ShotsCsvImportResource(BaseCsvProjectImportResource):
    def post(self, project_id, **kwargs):
        """
        Import project shots via a .csv file.
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
        self.sequences = {}
        self.descriptor_fields = self.get_descriptor_field_map(
            project_id, "Shot"
        )
        project = projects_service.get_project(project_id)
        self.is_tv_show = projects_service.is_tv_show(project)
        self.created_shots = []
        self.task_types_in_project_for_shots = (
            TaskType.query.join(ProjectTaskTypeLink)
            .filter(ProjectTaskTypeLink.project_id == project_id)
            .filter(TaskType.for_entity == "Shot")
        )
        self.task_statuses = {
            status["id"]: [status[n] for n in ("name", "short_name")]
            for status in get_task_statuses()
        }
        self.current_user_id = get_current_user()["id"]

    def get_tasks_update(self, row):
        tasks_update = []
        for task_type in self.task_types_in_project_for_shots:
            task_status_name = row.get(task_type.name, None)
            task_status_id = None
            if task_status_name not in [None, ""]:
                for status_id, status_names in self.task_statuses.items():
                    if task_status_name in status_names:
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
        self, tasks_update, entity, shot_creation=False
    ):
        if tasks_update:
            if shot_creation:
                tasks_map = {
                    str(task_type.id): create_task(
                        task_type.serialize(), entity.serialize()
                    )
                    for task_type in self.task_types_in_project_for_shots
                }
            else:
                tasks_map = {
                    task["task_type_id"]: task
                    for task in get_tasks_for_shot(str(entity.id))
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
        elif shot_creation:
            self.created_shots.append(entity.serialize())

    def import_row(self, row, project_id):
        if self.is_tv_show:
            episode_name = row["Episode"]
        sequence_name = row["Sequence"]
        shot_name = row["Name"]

        if self.is_tv_show:
            episode_key = "%s-%s" % (project_id, episode_name)
            if episode_key not in self.episodes:
                self.episodes[
                    episode_key
                ] = shots_service.get_or_create_episode(
                    project_id, episode_name
                )

            sequence_key = "%s-%s-%s" % (
                project_id,
                episode_name,
                sequence_name,
            )
        else:
            sequence_key = "%s-%s" % (project_id, sequence_name)

        if sequence_key not in self.sequences:
            if self.is_tv_show:
                episode = self.episodes[episode_key]
                self.sequences[
                    sequence_key
                ] = shots_service.get_or_create_sequence(
                    project_id, episode["id"], sequence_name
                )
            else:
                self.sequences[
                    sequence_key
                ] = shots_service.get_or_create_sequence(
                    project_id, None, sequence_name
                )
        sequence_id = self.get_id_from_cache(self.sequences, sequence_key)

        shot_type = shots_service.get_shot_type()

        shot_values = {
            "name": shot_name,
            "project_id": project_id,
            "parent_id": sequence_id,
            "entity_type_id": shot_type["id"],
        }

        entity = Entity.get_by(**shot_values)

        shot_new_values = {}

        description = row.get("Description", None)
        if description is not None:
            shot_new_values["description"] = description

        nb_frames = row.get("Nb Frames", None) or row.get("Frames", None)
        if nb_frames is not None:
            shot_new_values["nb_frames"] = (
                nb_frames if nb_frames != "" else None
            )

        if entity is None or not entity.data:
            shot_new_values["data"] = {}
        else:
            shot_new_values["data"] = entity.data.copy()

        frame_in = row.get("Frame In", None) or row.get("In", None)
        if frame_in is not None:
            shot_new_values["data"]["frame_in"] = frame_in

        frame_out = row.get("Frame Out", None) or row.get("Out", None)
        if frame_out is not None:
            shot_new_values["data"]["frame_out"] = frame_out

        fps = row.get("FPS", None)
        if fps is not None:
            shot_new_values["data"]["fps"] = fps

        for name, field_name in self.descriptor_fields.items():
            if name in row:
                shot_new_values["data"][field_name] = row[name]

        tasks_update = self.get_tasks_update(row)

        if entity is None:
            entity = Entity.create(**{**shot_values, **shot_new_values})
            events.emit(
                "shot:new", {"shot_id": str(entity.id)}, project_id=project_id
            )

            self.create_and_update_tasks(
                tasks_update, entity, shot_creation=True
            )

        elif self.is_update:
            entity.update(shot_new_values)
            events.emit(
                "shot:update",
                {"shot_id": str(entity.id)},
                project_id=project_id,
            )

            self.create_and_update_tasks(
                tasks_update, entity, shot_creation=False
            )

        return entity.serialize()

    def run_import(self, project_id, file_path):
        entities = super().run_import(project_id, file_path)
        for task_type in self.task_types_in_project_for_shots:
            create_tasks(task_type.serialize(), self.created_shots)
        return entities
