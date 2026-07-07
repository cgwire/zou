from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from zou.app.blueprints.entities.resources import (
    EntityPreviewFilesResource,
    EntityNewsResource,
    EntityTaskCreationResource,
    EntityTimeSpentsResource,
    EntitiesLinkedWithTasksResource,
    ProjectDeleteEntitiesResource,
)

routes = [
    (
        "/actions/projects/<project_id>/delete-entities",
        ProjectDeleteEntitiesResource,
    ),
    ("/data/entities/<entity_id>/news", EntityNewsResource),
    ("/data/entities/<entity_id>/preview-files", EntityPreviewFilesResource),
    ("/data/entities/<entity_id>/tasks", EntityTaskCreationResource),
    ("/data/entities/<entity_id>/time-spents", EntityTimeSpentsResource),
    (
        "/data/entities/<entity_id>/entities-linked/with-tasks",
        EntitiesLinkedWithTasksResource,
    ),
]

blueprint = Blueprint("entities", "entities")
api = configure_api_from_blueprint(blueprint, routes)
