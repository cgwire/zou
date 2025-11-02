from flask import request, abort
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from sqlalchemy.exc import StatementError

from zou.app.models.data_import_error import DataImportError


class ShotgunImportErrorsResource(Resource):

    def __init__(self):
        Resource.__init__(self)

    @jwt_required()
    def get(self):
        """
        Get shotgun import errors
        ---
        description: Get all Shotgun import errors from the database.
          Returns a list of data import errors with source "shotgun".
        tags:
          - Import
        responses:
          200:
            description: List of import errors retrieved successfully
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Import error unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      source:
                        type: string
                        description: Source of the import error
                        example: "shotgun"
                      event_data:
                        type: object
                        description: Error event data
                        example: {"error": "Import failed"}
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2024-01-15T10:30:00Z"
          400:
            description: Invalid request
        """
        criterions = {"source": "shotgun"}
        import_errors = DataImportError.query.filter_by(**criterions).all()
        return DataImportError.serialize_list(import_errors)

    @jwt_required()
    def post(self):
        """
        Create shotgun import error
        ---
        description: Create a new Shotgun import error record. The error
          event data should be provided in the JSON body.
        tags:
          - Import
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                description: Error event data
                properties:
                  error:
                    type: string
                    description: Error message
                    example: "Failed to import asset"
                  details:
                    type: object
                    description: Additional error details
                    example: {"shotgun_id": 12345, "reason": "Missing field"}
                example:
                  error: "Failed to import asset"
                  details:
                    shotgun_id: 12345
                    reason: "Missing required field"
        responses:
          201:
            description: Import error created successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Import error unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    source:
                      type: string
                      description: Source of the import error
                      example: "shotgun"
                    event_data:
                      type: object
                      description: Error event data
                      example: {"error": "Failed to import asset"}
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2024-01-15T10:30:00Z"
          400:
            description: Invalid request body
        """
        error = DataImportError(event_data=request.json, source="shotgun")
        error.save()
        return error.serialize(), 201


class ShotgunImportErrorResource(Resource):
    def __init__(self):
        Resource.__init__(self)

    @jwt_required()
    def delete(self, error_id):
        """
        Delete shotgun import error
        ---
        description: Delete a Shotgun import error by its unique identifier.
          Returns success confirmation when the error is deleted.
        tags:
          - Import
        parameters:
          - in: path
            name: error_id
            required: true
            schema:
              type: string
              format: uuid
            description: Import error unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          204:
            description: Import error deleted successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    deletion_success:
                      type: boolean
                      description: Whether deletion was successful
                      example: true
          400:
            description: Invalid error ID format
        """
        try:
            error = DataImportError.get(error_id)
        except StatementError:
            abort(404)

        if error is None:
            abort(404)
        error.delete()

        return {"deletion_success": True}, 204
