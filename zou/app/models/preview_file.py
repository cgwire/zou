from sqlalchemy_utils import UUIDType, ChoiceType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

from sqlalchemy.dialects.postgresql import JSONB

STATUSES = [
    ("processing", "Processing"),
    ("ready", "Ready"),
    ("broken", "Broken"),
]

VALIDATION_STATUSES = [
    ("validated", "Validated"),
    ("rejected", "Rejected"),
    ("neutral", "Neutral"),
]


class PreviewFile(db.Model, BaseMixin, SerializerMixin):
    """
    Describes a file which is aimed at being reviewed. It is not a publication
    neither a working file.
    """

    name = db.Column(db.String(250))
    original_name = db.Column(db.String(250))
    revision = db.Column(db.Integer(), default=1)
    position = db.Column(db.Integer(), default=1)
    extension = db.Column(db.String(6))
    description = db.Column(db.Text())
    path = db.Column(db.String(400))
    source = db.Column(db.String(40))
    file_size = db.Column(db.BigInteger(), default=0)
    status = db.Column(
        ChoiceType(STATUSES), default="processing", nullable=False
    )
    validation_status = db.Column(
        ChoiceType(VALIDATION_STATUSES), default="neutral", nullable=False
    )
    annotations = db.Column(JSONB)
    width = db.Column(db.Integer(), default=0)
    height = db.Column(db.Integer(), default=0)
    duration = db.Column(db.Float, default=0)

    task_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task.id"), index=True
    )
    person_id = db.Column(UUIDType(binary=False), db.ForeignKey("person.id"))
    source_file_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("output_file.id")
    )

    __table_args__ = (
        db.UniqueConstraint("name", "task_id", "revision", name="preview_uc"),
    )

    shotgun_id = db.Column(db.Integer, unique=True)

    is_movie = db.Column(db.Boolean, default=False)  # deprecated
    url = db.Column(db.String(600))  # deprecated
    uploaded_movie_url = db.Column(db.String(600))  # deprecated
    uploaded_movie_name = db.Column(db.String(150))  # deprecated

    def __repr__(self):
        return "<PreviewFile %s>" % self.id

    @classmethod
    def create_from_import(cls, data):
        del data["type"]
        if "comments" in data:
            del data["comments"]
        previous_data = cls.get(data["id"])
        if "status" not in data or data["status"] is None:
            data["status"] = "ready"
        if previous_data is None:
            return (cls.create(**data), False)
        else:
            previous_data.update(data)
            return (previous_data, True)

    def present(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "original_name": self.original_name,
            "extension": self.extension,
            "revision": self.revision,
            "position": self.position,
            "file_size": self.file_size,
            "status": str(self.status),
            "validation_status": str(self.validation_status),
            "task_id": str(self.task_id),
            "person_id": str(self.person_id),
        }
