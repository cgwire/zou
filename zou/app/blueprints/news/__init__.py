from zou.app.utils.api import create_blueprint_for_api

from .resources import (
    NewsResource,
    ProjectNewsResource,
    ProjectSingleNewsResource,
)


routes = [
    ("/data/projects/news", NewsResource),
    ("/data/projects/<project_id>/news", ProjectNewsResource),
    ("/data/projects/<project_id>/news/<news_id>", ProjectSingleNewsResource),
]

blueprint = create_blueprint_for_api("news", routes)
