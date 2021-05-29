from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class AttachmentFile(db.Model, BaseMixin, SerializerMixin):
    """
    Describes a file which is attached to a comment.
    """

    name = db.Column(db.String(250))
    size = db.Column(db.Integer(), default=1)
    extension = db.Column(db.String(6))
    mimetype = db.Column(db.String(255))
    comment_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("comment.id"), index=True
    )

    __table_args__ = (
        db.UniqueConstraint("name", "comment_id", name="attachment_uc"),
    )

    def __repr__(self):
        return "<AttachmentFile %s>" % self.id

    def present(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "extension": self.extension,
            "size": self.size,
        }

    @classmethod
    def create_from_import(cls, data):
        data.pop("type", None)
        data.pop("comment", None)
        previous_data = cls.get(data["id"])
        if previous_data is None:
            return cls.create(**data)
        else:
            previous_data.update(data)
            return previous_data

