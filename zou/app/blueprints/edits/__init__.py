from flask import Blueprint

from zou.app.blueprints.edits.resources import (
    AllEditsResource,
    EditPreviewsResource,
    EditResource,
    EditsAndTasksResource,
    EditTasksResource,
    EditTaskTypesResource,
    EditVersionsResource,
    EpisodeEditsResource,
    EpisodeEditTasksResource,
    ProjectEditsResource,
)
from zou.app.utils.api import configure_api_from_blueprint

routes = [
    ("/data/edits", AllEditsResource),
    # Same listing, second path kept because gazu queries edits/all.
    ("/data/edits/all", AllEditsResource),
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
