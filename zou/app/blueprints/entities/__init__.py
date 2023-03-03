from zou.app.utils.api import create_blueprint_for_api

from .resources import (
    EntityPreviewFilesResource,
    EntityNewsResource,
    EntityTimeSpentsResource,
)


routes = [
    ("/data/entities/<uuid:entity_id>/news", EntityNewsResource),
    (
        "/data/entities/<uuid:entity_id>/preview-files",
        EntityPreviewFilesResource,
    ),
    ("/data/entities/<uuid:entity_id>/time-spents", EntityTimeSpentsResource),
]

blueprint = create_blueprint_for_api("entities", routes)
