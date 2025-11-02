from flask import abort, current_app

from sqlalchemy.exc import StatementError
from flask_jwt_extended import jwt_required

from zou.app.models.software import Software
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.services import files_service


class SoftwaresResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Software)

    def check_read_permissions(self, options=None):
        return True


class SoftwareResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Software)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    def get(self, instance_id):
        """
        Get software
        ---
        tags:
          - Crud
        description: Retrieve a software instance by its ID and return it
          as a JSON object.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Software retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Maya
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid ID format or query error
        """
        try:
            software = files_service.get_software(instance_id)
            self.check_read_permissions(software)
            return self.clean_get_result(software)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            abort(404)

    def post_update(self, instance_dict, data):
        files_service.clear_software_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        files_service.clear_software_cache(instance_dict["id"])
        return instance_dict
