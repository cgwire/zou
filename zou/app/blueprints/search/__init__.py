"""
Utility routes to run full text search on Kitsu data.
"""
from zou.app.utils.api import create_blueprint_for_api

from .resources import SearchResource

routes = [("/data/search", SearchResource)]

blueprint = create_blueprint_for_api("search", routes)
