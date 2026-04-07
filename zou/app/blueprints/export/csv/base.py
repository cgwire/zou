from flask import abort
from flask_jwt_extended import jwt_required

from flask_restful import Resource
from zou.app.utils import csv_utils, permissions


class BaseCsvExport(Resource):
    def __init__(self):
        Resource.__init__(self)
        self.file_name = "export"

    def check_permissions(self):
        permissions.check_manager_permissions()
        return True

    def prepare_import(self):
        pass

    @jwt_required()
    def get(self):
        """
        Export csv
        ---
        tags:
          - Export
        description: Export data as CSV file. Returns a CSV file with
          formatted data based on the resource type.
        produces:
          - text/csv
        responses:
            200:
              description: CSV file exported successfully
              content:
                text/csv:
                  schema:
                    type: string
                  example: "Header1,Header2\nValue1,Value2"
        """
        self.prepare_import()
        try:
            self.check_permissions()
        except permissions.PermissionDenied:
            raise

        def row_generator():
            yield self.build_headers()
            for result in self.build_query().yield_per(500):
                yield self.build_row(result)

        return csv_utils.build_csv_stream_response(
            row_generator(), file_name=self.file_name
        )
