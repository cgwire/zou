from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class ChatParticipant(db.Model):
    __tablename__ = "chat_participant"
    chat_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("chat.id"),
        primary_key=True,
    )
    person_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        primary_key=True,
    )


class Chat(db.Model, BaseMixin, SerializerMixin):
    """
    Message shared in the entity chat feeds.
    """

    object_id = db.Column(UUIDType(binary=False), nullable=False, index=True)
    object_type = db.Column(
        db.String(80), nullable=False, index=True, default="entity"
    )
    last_message = db.Column(db.DateTime, nullable=True)
    participants = db.relationship(
        "Person", secondary="chat_participant", lazy="joined"
    )

    def __repr__(self):
        return "<Message of %s>" % self.object_id

    def present(self):
        return {
            "id": str(self.id),
            "object_id": str(self.object_id),
            "last_message": self.last_message,
        }
