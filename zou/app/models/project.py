from sqlalchemy_utils import UUIDType
from sqlalchemy.dialects.postgresql import JSONB

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class ProjectPersonLink(db.Model):
    __tablename__ = "project_person_link"
    project_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("project.id"), primary_key=True
    )
    person_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("person.id"), primary_key=True
    )
    shotgun_id = db.Column(db.Integer)


class ProjectTaskTypeLink(db.Model, BaseMixin, SerializerMixin):
    __tablename__ = "project_task_type_link"
    project_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("project.id"), primary_key=True
    )
    task_type_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_type.id"), primary_key=True
    )
    priority = db.Column(db.Integer, default=None)

    __table_args__ = (
        db.UniqueConstraint(
            "project_id", "task_type_id", name="project_tasktype_uc"
        ),
    )


class ProjectTaskStatusLink(db.Model):
    __tablename__ = "project_task_status_link"
    project_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("project.id"), primary_key=True
    )
    task_status_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("task_status.id"),
        primary_key=True,
    )


class ProjectAssetTypeLink(db.Model):
    __tablename__ = "project_asset_type_link"
    project_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("project.id"), primary_key=True
    )
    asset_type_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("entity_type.id"),
        primary_key=True,
    )


class Project(db.Model, BaseMixin, SerializerMixin):
    """
    Describes a CG production the studio works on.
    """

    name = db.Column(db.String(80), nullable=False, unique=True, index=True)
    code = db.Column(db.String(80))
    description = db.Column(db.Text())
    shotgun_id = db.Column(db.Integer)
    file_tree = db.Column(JSONB)
    data = db.Column(JSONB)
    has_avatar = db.Column(db.Boolean(), default=False)
    fps = db.Column(db.String(10))
    ratio = db.Column(db.String(10))
    resolution = db.Column(db.String(12))
    production_type = db.Column(db.String(20), default="short")
    start_date = db.Column(db.Date())
    end_date = db.Column(db.Date())
    man_days = db.Column(db.Integer)
    nb_episodes = db.Column(db.Integer, default=0)
    episode_span = db.Column(db.Integer, default=0)

    project_status_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("project_status.id"), index=True
    )

    team = db.relationship("Person", secondary="project_person_link")
    asset_types = db.relationship(
        "EntityType", secondary="project_asset_type_link"
    )
    task_statuses = db.relationship(
        "TaskStatus", secondary="project_task_status_link"
    )
    task_types = db.relationship(
        "TaskType", secondary="project_task_type_link"
    )

    def set_team(self, person_ids):
        for person_id in person_ids:
            link = ProjectPersonLink.query.filter_by(
                project_id=self.id, person_id=person_id
            ).first()
            if link is None:
                link = ProjectPersonLink(
                    project_id=self.id, person_id=person_id
                )
                db.session.add(link)
        db.session.commit()

    def set_task_types(self, task_type_ids):
        return self.set_links(
            task_type_ids, ProjectTaskTypeLink, "project_id", "task_type_id"
        )

    def set_task_statuses(self, task_status_ids):
        return self.set_links(
            task_status_ids,
            ProjectTaskStatusLink,
            "project_id",
            "task_status_id",
        )

    def set_asset_types(self, asset_type_ids):
        return self.set_links(
            asset_type_ids, ProjectAssetTypeLink, "project_id", "asset_type_id"
        )

    @classmethod
    def create_from_import(cls, data):
        is_update = False
        previous_project = cls.get(data["id"])
        data.pop("team", None)
        data.pop("type", None)
        data.pop("project_status_name", None)
        person_ids = data.pop("team", None)
        task_type_ids = data.pop("task_types", None)
        task_status_ids = data.pop("task_statuses", None)
        asset_type_ids = data.pop("asset_types", None)

        if previous_project is None:
            previous_project = cls.create(**data)
            previous_project.save()
        else:
            is_update = True
            previous_project.update(data)
            previous_project.save()

        if person_ids is not None:
            previous_project.set_team(person_ids)

        if task_type_ids is not None:
            previous_project.set_task_types(task_type_ids)

        if task_status_ids is not None:
            previous_project.set_task_statuses(task_status_ids)

        if asset_type_ids is not None:
            previous_project.set_asset_types(asset_type_ids)

        return (previous_project, is_update)
