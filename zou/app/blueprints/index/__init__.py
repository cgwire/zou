"""
This module is named source instead of import because import is a Python
keyword.
"""

from flask import Blueprint

from zou.app.blueprints.index.resources import (
    ConfigResource,
    IndexResource,
    InfluxStatusResource,
    StatsResource,
    StatusResource,
    StatusResourcesResource,
    TestEventsResource,
    TxtStatusResource,
)
from zou.app.utils.api import configure_api_from_blueprint

routes = [
    ("/", IndexResource),
    ("/status", StatusResource),
    ("/status/influx", InfluxStatusResource),
    ("/status/resources", StatusResourcesResource),
    ("/status.txt", TxtStatusResource),
    ("/status/test-event", TestEventsResource),
    ("/stats", StatsResource),
    ("/config", ConfigResource),
]

blueprint = Blueprint("index", "index")
api = configure_api_from_blueprint(blueprint, routes)
