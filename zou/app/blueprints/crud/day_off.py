from flask_jwt_extended import jwt_required

from zou.app.models.day_off import DayOff
from zou.app.models.time_spent import TimeSpent

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.services import user_service, time_spents_service

from zou.app.services.exception import WrongParameterException

from zou.app.utils import permissions


class DayOffsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, DayOff)

    def check_create_permissions(self, data):
        return user_service.check_day_off_access(data)

    @jwt_required()
    def get(self):
        """
        Get day offs
        ---
        tags:
          - Crud
        description: Retrieve all day offs. Supports filtering via query
          parameters and pagination.
        parameters:
          - in: query
            name: page
            required: false
            schema:
              type: integer
            example: 1
            description: Page number for pagination
          - in: query
            name: limit
            required: false
            schema:
              type: integer
            example: 50
            description: Number of results per page
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Whether to include relations
        responses:
            200:
              description: Day offs retrieved successfully
              content:
                application/json:
                  schema:
                    oneOf:
                      - type: array
                        items:
                          type: object
                      - type: object
                        properties:
                          data:
                            type: array
                            items:
                              type: object
                            example: []
                          total:
                            type: integer
                            example: 100
                          nb_pages:
                            type: integer
                            example: 2
                          limit:
                            type: integer
                            example: 50
                          offset:
                            type: integer
                            example: 0
                          page:
                            type: integer
                            example: 1
            400:
              description: Invalid filter format or query error
        """
        return super().get()

    @jwt_required()
    def post(self):
        """
        Create day off
        ---
        tags:
          - Crud
        description: Create a new day off with data provided in the
          request body. JSON format is expected. Deletes overlapping
          time spent entries.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - date
                  - end_date
                  - person_id
                properties:
                  date:
                    type: string
                    format: date
                    example: "2024-01-15"
                  end_date:
                    type: string
                    format: date
                    example: "2024-01-20"
                  person_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Day off created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      date:
                        type: string
                        format: date
                        example: "2024-01-15"
                      end_date:
                        type: string
                        format: date
                        example: "2024-01-20"
                      person_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or day off already exists
        """
        return super().post()

    def check_creation_integrity(self, data):
        if time_spents_service.get_day_offs_between(
            data["date"], data["end_date"], data["person_id"]
        ):
            raise WrongParameterException(
                "Day off already exists for this period"
            )
        return data

    def post_creation(self, instance):
        TimeSpent.delete_all_by(
            instance.date >= TimeSpent.date,
            instance.end_date <= TimeSpent.date,
            person_id=instance.person_id,
        )
        return instance.serialize()


class DayOffResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, DayOff)

    @jwt_required()
    def get(self, instance_id):
        """
        Get day off
        ---
        tags:
          - Crud
        description: Retrieve a day off by its ID and return it as a JSON
          object. Supports including relations.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: true
            example: true
            description: Whether to include relations
        responses:
            200:
              description: Day off retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      date:
                        type: string
                        format: date
                        example: "2024-01-15"
                      end_date:
                        type: string
                        format: date
                        example: "2024-01-20"
                      person_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
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
        return super().get(instance_id)

    @jwt_required()
    def put(self, instance_id):
        """
        Update day off
        ---
        tags:
          - Crud
        description: Update a day off with data provided in the request
          body. JSON format is expected. Deletes overlapping time spent
          entries.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  date:
                    type: string
                    format: date
                    example: "2024-01-16"
                  end_date:
                    type: string
                    format: date
                    example: "2024-01-21"
        responses:
            200:
              description: Day off updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      date:
                        type: string
                        format: date
                        example: "2024-01-16"
                      end_date:
                        type: string
                        format: date
                        example: "2024-01-21"
                      person_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T11:00:00Z"
            400:
              description: Invalid data format or day off already exists
        """
        return super().put(instance_id)

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete day off
        ---
        tags:
          - Crud
        description: Delete a day off by its ID. Returns empty response
          on success.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Day off deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def check_delete_permissions(self, instance_dict):
        return user_service.check_day_off_access(instance_dict)

    def check_read_permissions(self, instance_dict):
        return user_service.check_day_off_access(instance_dict)

    def check_update_permissions(self, instance_dict, data):
        if (
            "person_id" in data.keys()
            and instance_dict["person_id"] != data["person_id"]
            and not permissions.has_admin_permissions()
        ):
            raise permissions.PermissionDenied()
        return user_service.check_day_off_access(instance_dict)

    def post_update(self, instance_dict, data):
        TimeSpent.delete_all_by(
            self.instance.date >= TimeSpent.date,
            self.instance.end_date <= TimeSpent.date,
            person_id=self.instance.person_id,
        )
        return instance_dict

    def pre_update(self, instance_dict, data):
        if time_spents_service.get_day_offs_between(
            data.get("date", instance_dict["date"]),
            data.get("end_date", instance_dict["end_date"]),
            data.get("person_id", instance_dict["person_id"]),
            exclude_id=instance_dict["id"],
        ):
            raise WrongParameterException(
                "Day off already exists for this period"
            )
        return data
