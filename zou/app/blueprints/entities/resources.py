from flask import request
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app.services import (
    entities_service,
    news_service,
    preview_files_service,
    time_spents_service,
    user_service,
)


class EntityNewsResource(Resource):
    @jwt_required
    def get(self, entity_id):
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return news_service.get_news_for_entity(entity_id)


class EntityPreviewFilesResource(Resource):
    @jwt_required
    def get(self, entity_id):
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return preview_files_service.get_preview_files_for_entity(entity_id)


class EntityTimeSpentsResource(Resource):
    @jwt_required
    def get(self, entity_id):
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return time_spents_service.get_time_spents_for_entity(entity_id)
