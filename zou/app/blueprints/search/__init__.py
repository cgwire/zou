"""
Utility routes to run full text search on Kitsu data.
"""

from flask import Blueprint

from zou.app.blueprints.search.resources import SearchResource
from zou.app.utils.api import configure_api_from_blueprint

routes = [("/data/search", SearchResource)]

blueprint = Blueprint("search", "search")
api = configure_api_from_blueprint(blueprint, routes)
