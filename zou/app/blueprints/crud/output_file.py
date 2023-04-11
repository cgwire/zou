from zou.app.models.output_file import OutputFile
from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.services import user_service, entities_service
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource


class OutputFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, OutputFile)

    def check_read_permissions(self):
        user_service.block_access_to_vendor()
        return True

    def add_project_permission_filter(self, query):
        if permissions.has_admin_permissions():
            return query
        else:
            query = (
                query.join(Entity, OutputFile.entity_id == Entity.id)
                .join(Project)
                .filter(user_service.build_related_projects_filter())
            )
            return query


class OutputFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, OutputFile)

    def check_read_permissions(self, instance):
        entity = entities_service.get_entity(instance["entity_id"])
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])
        return True

    def check_update_permissions(self, output_file, data):
        if permissions.has_manager_permissions():
            return True
        else:
            return user_service.check_working_on_entity(
                output_file["temporal_entity_id"] or output_file["entity_id"]
            )
