from zou.app.utils.api import create_blueprint_for_api

from .resources import (
    EntityPreviewFilesResource,
    EntityNewsResource,
    EntityTimeSpentsResource,
)


routes = [
    ("/data/entities/<entity_id>/news", EntityNewsResource),
    ("/data/entities/<entity_id>/preview-files", EntityPreviewFilesResource),
    ("/data/entities/<entity_id>/time-spents", EntityTimeSpentsResource),
]

blueprint = create_blueprint_for_api("entities", routes)
