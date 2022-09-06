from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class TaskStatus(db.Model, BaseMixin, SerializerMixin):
    """
    Describe the state of a task. A status marked as reviewable expects a
    preview file linked to relate comment.
    """

    name = db.Column(db.String(40), nullable=False)
    archived = db.Column(db.Boolean(), default=False)
    short_name = db.Column(
        db.String(10), unique=True, nullable=False, index=True
    )
    color = db.Column(db.String(7), nullable=False)

    is_done = db.Column(db.Boolean(), default=False, index=True)
    is_artist_allowed = db.Column(db.Boolean(), default=True)
    is_client_allowed = db.Column(db.Boolean(), default=True)
    is_retake = db.Column(db.Boolean(), default=False)
    is_feedback_request = db.Column(db.Boolean(), default=False, index=True)
    is_default = db.Column(db.Boolean(), default=False, index=True)
    shotgun_id = db.Column(db.Integer)
