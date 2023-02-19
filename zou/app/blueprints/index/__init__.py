"""
This module is named source instead of import because import is a Python
keyword.
"""
from zou.app.utils.api import create_blueprint_for_api

from .resources import (
    ConfigResource,
    IndexResource,
    InfluxStatusResource,
    StatusResource,
    StatusResourcesResource,
    StatsResource,
    TxtStatusResource,
)

routes = [
    ("/", IndexResource),
    ("/status", StatusResource),
    ("/status/influx", InfluxStatusResource),
    ("/status/resources", StatusResourcesResource),
    ("/status.txt", TxtStatusResource),
    ("/stats", StatsResource),
    ("/config", ConfigResource),
]

blueprint = create_blueprint_for_api("index", routes)
