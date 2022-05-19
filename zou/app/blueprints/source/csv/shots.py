from zou.app.blueprints.source.csv.base import BaseCsvProjectImportResource

from zou.app.models.entity import Entity
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task_type import TaskType
from zou.app.services import shots_service, projects_service
from zou.app.services.tasks_service import (
    create_task,
    create_tasks,
    get_tasks_for_shot,
    get_task_statuses,
)
from zou.app.services.comments_service import create_comment
from zou.app.services.persons_service import get_current_user
from zou.app.services.exception import TaskStatusNotFoundException
from zou.app.utils import events


class ShotsCsvImportResource(BaseCsvProjectImportResource):
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
            status["id"]: [status[n].lower() for n in ("name", "short_name")]
            for status in get_task_statuses()
        }
        self.current_user_id = get_current_user()["id"]

    def import_row(self, row, project_id):
        if self.is_tv_show:
            episode_name = row["Episode"]
        sequence_name = row["Sequence"]
        shot_name = row["Name"]
        description = row.get("Description", "")
        nb_frames = row.get("Nb Frames", None) or row.get("Frames", None)
        data = {
            "frame_in": row.get("Frame In", None) or row.get("In", None),
            "frame_out": row.get("Frame Out", None) or row.get("Out", None),
            "fps": row.get("FPS", None),
        }

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
        entity = Entity.get_by(
            name=shot_name,
            project_id=project_id,
            parent_id=sequence_id,
            entity_type_id=shot_type["id"],
        )

        for name, field_name in self.descriptor_fields.items():
            if name in row:
                data[field_name] = row[name]
            elif (
                entity is not None
                and entity.data is not None
                and field_name in entity.data
            ):
                data[field_name] = entity.data[field_name]

        # Search for task name and comment column and append values for update
        # in a dictionnary using task name as key.
        tasks_update = {}
        for task_type in self.task_types_in_project_for_shots:
            # search for status update and get this id if found
            task_status_name = row.get(task_type.name, "").lower()
            task_status_id = ""
            if task_status_name:
                for status_id, status_names in self.task_statuses.items():
                    if task_status_name in status_names:
                        task_status_id = status_id
                        break
                else:
                    raise TaskStatusNotFoundException(
                        "Task status not found for %s" % task_status_name
                    )
            # search for comment
            task_comment_text = row.get("%s comment" % task_type.name, "")
            # append updates if valided
            if task_status_id or task_comment_text:
                tasks_update[task_type.name] = {
                    "status": task_status_id,
                    "comment": task_comment_text,
                }

        tasks = []
        if entity is None:
            if nb_frames is None or len(nb_frames) == 0:
                entity = Entity.create(
                    name=shot_name,
                    description=description,
                    project_id=project_id,
                    parent_id=sequence_id,
                    entity_type_id=shot_type["id"],
                    data=data,
                )
            else:
                entity = Entity.create(
                    name=shot_name,
                    description=description,
                    project_id=project_id,
                    parent_id=sequence_id,
                    entity_type_id=shot_type["id"],
                    nb_frames=nb_frames,
                    data=data,
                )
            events.emit(
                "shot:new", {"shot_id": str(entity.id)}, project_id=project_id
            )
            if tasks_update:
                # if task updates are required we need to create the entity
                # tasks immediately and append it in the task list in order
                # to update it at the end of this current row import process.
                for task_type in self.task_types_in_project_for_shots:
                    tasks.append(
                        create_task(task_type.serialize(), entity.serialize())
                    )
            else:
                # if there is no update for task we append the entity in the
                # created entities list in order to optimize task creation in
                # the run_import method call when all rows are imported.
                self.created_shots.append(entity.serialize())

        elif self.is_update:
            entity.update(
                {
                    "description": description,
                    "nb_frames": nb_frames,
                    "data": data,
                }
            )
            events.emit(
                "shot:update",
                {"shot_id": str(entity.id)},
                project_id=project_id,
            )
            if tasks_update:
                tasks = get_tasks_for_shot(str(entity.id))

        # Update task status and/or comment using the created tasks list and
        # the tasks_update dictionnary.
        for task in tasks:
            task_name = task["task_type_name"]
            if task_name in tasks_update:
                task_status = tasks_update[task_name]["status"]
                task_comment = tasks_update[task_name]["comment"]
                if task_status != task["task_status_id"] or task_comment:
                    create_comment(
                        self.current_user_id,
                        task["id"],
                        task_status or task["task_status_id"],
                        task_comment,
                        [],
                        {},
                        "",
                    )

        return entity.serialize()

    def run_import(self, project_id, file_path):
        entities = super().run_import(project_id, file_path)
        for task_type in self.task_types_in_project_for_shots:
            create_tasks(task_type.serialize(), self.created_shots)
        return entities
