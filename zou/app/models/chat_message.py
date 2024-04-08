from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class ChatMessage(db.Model, BaseMixin, SerializerMixin):
    """
    Message shared in the entity chat feeds.
    """

    chat_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("chat.id"),
        nullable=False,
        index=True,
    )
    person_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        nullable=False,
        index=True,
    )
    text = db.Column(db.Text())
    attachment_files = db.relationship(
        "AttachmentFile", backref="chat_message", lazy="joined"
    )

    # TODO
    # * mentions
    # * reactions
    # * concept links ?
    # * task links ?

    def __repr__(self):
        return "<Message of %s>" % self.object_id
