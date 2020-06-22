"""
This module is named source instead of import because import is a Python
keyword.
"""
from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from .resources import (
    ConfigResource,
    IndexResource,
    InfluxStatusResource,
    StatusResource,
    StatsResource,
    TxtStatusResource,
)

routes = [
    ("/", IndexResource),
    ("/status", StatusResource),
    ("/status/influx", InfluxStatusResource),
    ("/status.txt", TxtStatusResource),
    ("/stats", StatsResource),
    ("/config", ConfigResource),
]

blueprint = Blueprint("index", "index")
api = configure_api_from_blueprint(blueprint, routes)
