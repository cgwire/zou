from zou.app.blueprints.export.csv.base import BaseCsvExport

from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.time_spent import TimeSpent
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType

from zou.app.services import names_service, persons_service
from zou.app.utils import date_helpers


class TimeSpentsCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)

    def prepare_import(self):
        user = persons_service.get_current_user()
        date = date_helpers.get_today_string_with_timezone(user["timezone"])
        self.file_name = "%s_open_projects_time_spents_export" % date

    def build_headers(self):
        return [
            "Project",
            "Person",
            "Entity Type Name",
            "Entity",
            "Task Type",
            "Date",
            "Time spent",
        ]

    def build_query(self):
        query = (
            TimeSpent.query.order_by(
                TimeSpent.created_at,
                Person.last_name,
                Project.name,
                EntityType.name,
                Entity.name,
            )
            .join(Task, TimeSpent.task_id == Task.id)
            .join(Entity, Task.entity_id == Entity.id)
            .join(EntityType)
            .join(Project, Task.project_id == Project.id)
            .join(TaskType)
            .join(Person, TimeSpent.person_id == Person.id)
            .add_columns(Project.name)
            .add_columns(EntityType.name)
            .add_columns(Entity.id)
            .add_columns(Entity.name)
            .add_columns(TaskType.name)
            .add_columns(Person.first_name)
            .add_columns(Person.last_name)
        )
        return query

    def build_row(self, time_spent_row):
        (
            time_spent,
            project_name,
            entity_type_name,
            entity_id,
            entity_name,
            task_type_name,
            person_first_name,
            person_last_name,
        ) = time_spent_row
        if entity_type_name == "Shot":
            entity_name, _ = names_service.get_full_entity_name(entity_id)

        date = ""
        if time_spent.created_at is not None:
            date = time_spent.created_at.strftime("%Y-%m-%d")

        person_name = "%s %s" % (person_first_name, person_last_name)

        return [
            project_name,
            person_name.strip(),
            entity_type_name,
            entity_name,
            task_type_name,
            date,
            time_spent.duration,
        ]
