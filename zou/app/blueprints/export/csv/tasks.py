from zou.app.blueprints.export.csv.base import BaseCsvExport
from sqlalchemy.orm import aliased

from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.models.task import Task
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType

from zou.app.services import projects_service


class TasksCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)

        self.file_name = "tasks_export"

    def build_headers(self):
        return [
            "Project",
            "Task Type",
            "Episode",
            "Sequence",
            "Entity Type",
            "Entity",
            "Assigner",
            "Assignees",
            "Duration",
            "Estimation",
            "Start date",
            "Due date",
            "WIP date",
            "Validation date",
            "Task Status",
        ]

    def build_query(self):
        Sequence = aliased(Entity, name="sequence")
        Episode = aliased(Entity, name="episode")
        open_status = projects_service.get_open_status()

        query = Task.query.order_by(Project.name, TaskType.name, Task.name)
        query = query.join(Project)
        query = query.join(TaskType)
        query = query.join(TaskStatus)
        query = query.join(Entity, Task.entity_id == Entity.id)
        query = query.join(EntityType)
        query = (
            query.outerjoin(Person, Task.assigner_id == Person.id)
            .outerjoin(Sequence, Sequence.id == Entity.parent_id)
            .outerjoin(Episode, Episode.id == Sequence.parent_id)
        )
        query = query.add_columns(
            Project.name,
            TaskType.name,
            TaskStatus.name,
            Episode.name,
            Sequence.name,
            EntityType.name,
            Entity.name,
            Person.first_name,
            Person.last_name,
        )
        query = query.filter(Project.project_status_id == open_status["id"])
        query = query.order_by(
            Project.name,
            TaskType.name,
            Episode.name,
            Sequence.name,
            EntityType.name,
            Entity.name,
        )

        return query

    def build_row(self, task_data):
        (
            task,
            project_name,
            task_type_name,
            task_status_name,
            episode_name,
            sequence_name,
            entity_type_name,
            entity_name,
            assigner_first_name,
            assigner_last_name,
        ) = task_data

        assigner_name = ""
        if assigner_first_name is not None and assigner_last_name is not None:
            assigner_name = assigner_first_name + " " + assigner_last_name
        elif assigner_first_name is not None:
            assigner_name = assigner_first_name
        elif assigner_last_name is not None:
            assigner_name = assigner_last_name

        persons = task.assignees_as_string()

        start_date = ""
        if task.start_date is not None:
            start_date = task.start_date.strftime("%Y-%m-%d")

        due_date = ""
        if task.due_date is not None:
            due_date = task.due_date.strftime("%Y-%m-%d")

        real_start_date = ""
        if task.real_start_date is not None:
            real_start_date = task.real_start_date.strftime("%Y-%m-%d")

        end_date = ""
        if task.end_date is not None:
            end_date = task.end_date.strftime("%Y-%m-%d")

        return [
            project_name,
            task_type_name,
            episode_name,
            sequence_name,
            entity_type_name,
            entity_name,
            assigner_name,
            persons,
            task.duration,
            task.estimation,
            start_date,
            due_date,
            real_start_date,
            end_date,
            task_status_name,
        ]
