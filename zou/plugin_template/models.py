from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

from sqlalchemy.orm import declarative_base
from sqlalchemy import MetaData, Column, Integer

plugin_metadata = MetaData()
PluginBase = declarative_base(metadata=plugin_metadata)


class Count(PluginBase, BaseMixin, SerializerMixin):
    """
    Describe a plugin.
    """

    __tablename__ = "toto_count"
    count = Column(Integer, nullable=False, default=0)
