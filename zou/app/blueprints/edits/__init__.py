from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from .resources import (
    EditResource,
    EditsResource,
    AllEditsResource,
    EditsAndTasksResource,
    EditPreviewsResource,
    EditTaskTypesResource,
    EditTasksResource,
    EditVersionsResource,
    ProjectEditsResource,
    EpisodeEditsResource,
    EpisodeEditTasksResource,
)

routes = [
    ("/data/edits", AllEditsResource),
    ("/data/edits/all", EditsResource),
    ("/data/edits/with-tasks", EditsAndTasksResource),
    ("/data/edits/<edit_id>", EditResource),
    ("/data/edits/<edit_id>/task-types", EditTaskTypesResource),
    ("/data/edits/<edit_id>/tasks", EditTasksResource),
    ("/data/edits/<edit_id>/preview-files", EditPreviewsResource),
    ("/data/edits/<edit_id>/versions", EditVersionsResource),
    ("/data/episodes/<episode_id>/edits", EpisodeEditsResource),
    ("/data/episodes/<episode_id>/edit-tasks", EpisodeEditTasksResource),
    ("/data/projects/<project_id>/edits", ProjectEditsResource),
]


blueprint = Blueprint("edits", "edits")
api = configure_api_from_blueprint(blueprint, routes)
