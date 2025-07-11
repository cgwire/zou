from sqlalchemy_utils import UUIDType
from sqlalchemy.dialects.postgresql import JSONB
from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class TaskPersonLink(db.Model):
    __tablename__ = "task_person_link"
    task_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("task.id"),
        primary_key=True,
    )
    person_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        primary_key=True,
    )


class Task(db.Model, BaseMixin, SerializerMixin):
    """
    Describes a task done by a CG artist on an entity of the CG production.
    The task has a state and assigned to people. It handles notion of time like
    duration, start date and end date.
    """

    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text())

    priority = db.Column(db.Integer, default=0)
    difficulty = db.Column(db.Integer, default=3, nullable=False)
    duration = db.Column(db.Float, default=0)
    estimation = db.Column(db.Float, default=0)
    completion_rate = db.Column(db.Integer, default=0)
    retake_count = db.Column(db.Integer, default=0)
    sort_order = db.Column(db.Integer, default=0)
    start_date = db.Column(db.DateTime)
    due_date = db.Column(db.DateTime)
    real_start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    done_date = db.Column(db.DateTime)
    last_comment_date = db.Column(db.DateTime)
    nb_assets_ready = db.Column(db.Integer, default=0)
    data = db.Column(JSONB)
    nb_drawings = db.Column(db.Integer, default=0)

    shotgun_id = db.Column(db.Integer)
    last_preview_file_id = db.Column(UUIDType(binary=False))

    project_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("project.id"), index=True
    )
    task_type_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_type.id"), index=True
    )
    task_status_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_status.id"), index=True
    )
    entity_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("entity.id"), index=True
    )
    assigner_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("person.id"), index=True
    )
    assignees = db.relationship("Person", secondary=TaskPersonLink.__table__)

    __table_args__ = (
        db.UniqueConstraint(
            "name", "project_id", "task_type_id", "entity_id", name="task_uc"
        ),
        db.CheckConstraint(
            "difficulty > 0 AND difficulty < 6", name="check_difficulty"
        ),
    )

    def assignees_as_string(self):
        return ", ".join([x.full_name for x in self.assignees])

    def set_assignees(self, person_ids):
        from zou.app.models.person import Person

        self.assignees = []
        for person_id in person_ids:
            person = Person.get(person_id)
            if person is not None:
                self.assignees.append(person)
        self.save()

    @classmethod
    def create_from_import(cls, data):
        previous_task = cls.get(data["id"])
        person_ids = data.get("assignees", None)
        is_update = False
        if "assignees" in data:
            data.pop("assignees", None)
        if "type" in data:
            data.pop("type", None)

        if previous_task is None:
            previous_task = cls.create(**data)
            previous_task.save()
        else:
            is_update = True
            previous_task.update(data)
            previous_task.save()

        if person_ids is not None:
            previous_task.set_assignees(person_ids)

        return (previous_task, is_update)
