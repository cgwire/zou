from zou.app.utils.api import create_blueprint_for_api

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
    ("/data/edits/<uuid:edit_id>", EditResource),
    ("/data/edits/<uuid:edit_id>/task-types", EditTaskTypesResource),
    ("/data/edits/<uuid:edit_id>/tasks", EditTasksResource),
    ("/data/edits/<uuid:edit_id>/preview-files", EditPreviewsResource),
    ("/data/edits/<uuid:edit_id>/versions", EditVersionsResource),
    ("/data/episodes/<uuid:episode_id>/edits", EpisodeEditsResource),
    ("/data/episodes/<uuid:episode_id>/edit-tasks", EpisodeEditTasksResource),
    ("/data/projects/<uuid:project_id>/edits", ProjectEditsResource),
]


blueprint = create_blueprint_for_api("edits", routes)
