from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class Organisation(db.Model, BaseMixin, SerializerMixin):
    """
    Model to represent current organisation settings.
    """

    name = db.Column(db.String(80), unique=True, nullable=False)
    hours_by_day = db.Column(db.Float, default=8, nullable=False)
    has_avatar = db.Column(db.Boolean(), default=False)
    use_original_file_name = db.Column(db.Boolean(), default=False)
    timesheets_locked = db.Column(db.Boolean(), default=False)
    format_duration_in_hours = db.Column(db.Boolean(), default=False)
    hd_by_default = db.Column(db.Boolean(), default=False)
    chat_token_slack = db.Column(db.String(80), default="")
    chat_webhook_mattermost = db.Column(db.String(80), default="")
    chat_token_discord = db.Column(db.String(80), default="")
    dark_theme_by_default = db.Column(db.Boolean(), default=False)
    format_duration_in_hours = db.Column(db.Boolean(), default=False)

    def present(self, sensitive=False):
        return self.serialize(
            ignored_attrs=(
                []
                if sensitive
                else [
                    "chat_token_slack",
                    "chat_webhook_mattermost",
                    "chat_token_discord",
                ]
            )
        )
