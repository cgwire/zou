from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin
from zou.app.utils import fields


class Organisation(db.Model, BaseMixin, SerializerMixin):
    """
    Model to represent current organisation settings.
    """

    name = db.Column(db.String(80), unique=True, nullable=False)
    hours_by_day = db.Column(db.Float, default=8, nullable=False)
    has_avatar = db.Column(db.Boolean(), default=False)
    use_original_file_name = db.Column(db.Boolean(), default=False)
    timesheets_locked = db.Column(db.Boolean(), default=False)
    hd_by_default = db.Column(db.Boolean(), default=False)
    chat_token_slack = db.Column(db.String(80), default="")
    chat_webhook_mattermost = db.Column(db.String(80), default="")
    chat_token_discord = db.Column(db.String(80), default="")

    def present(self):
        return fields.serialize_dict(
            {
                "id": self.id,
                "chat_token_slack": self.chat_token_slack,
                "chat_webhook_mattermost": self.chat_webhook_mattermost,
                "chat_token_discord": self.chat_token_discord,
                "name": self.name,
                "has_avatar": self.has_avatar,
                "hours_by_day": self.hours_by_day,
                "hd_by_default": self.hd_by_default,
                "use_original_file_name": self.use_original_file_name,
                "timesheets_locked": self.timesheets_locked,
                "updated_at": self.updated_at,
                "created_at": self.created_at,
            }
        )
