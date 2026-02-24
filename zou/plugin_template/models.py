from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

from sqlalchemy.orm import declarative_base
from sqlalchemy import MetaData, Column, Integer

from zou.app.utils.plugins import create_plugin_metadata

plugin_metadata = create_plugin_metadata("myplugin")  # plugin id expected here
PluginBase = declarative_base(metadata=plugin_metadata)


class Count(PluginBase, BaseMixin, SerializerMixin):
    """
    A simple model to keep track of a count.
    """

    __tablename__ = "hello_count"
    __table_args__ = {"extend_existing": True}
    count = Column(Integer, nullable=False, default=0)
