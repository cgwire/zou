from sqlalchemy_utils import EmailType, URLType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class Plugin(db.Model, BaseMixin, SerializerMixin):
    """
    A plugin is a module used to extend the functionality of Zou.
    You can extend the REST API routes and the database models.
    """

    plugin_id = db.Column(
        db.String(80), unique=True, nullable=False, index=True
    )
    name = db.Column(db.String(80), nullable=False, index=True)
    description = db.Column(db.Text())
    version = db.Column(db.String(50), nullable=False)
    maintainer_name = db.Column(db.String(200), nullable=False)
    maintainer_email = db.Column(EmailType)
    website = db.Column(URLType)
    license = db.Column(db.String(80), nullable=False)
    revision = db.Column(db.String(12), nullable=True)
