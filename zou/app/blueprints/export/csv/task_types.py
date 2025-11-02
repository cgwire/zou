from zou.app.blueprints.export.csv.base import BaseCsvExport
from flask_jwt_extended import jwt_required

from zou.app.models.department import Department
from zou.app.models.task_type import TaskType


class TaskTypesCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)

        self.name = "task_types_export"

    @jwt_required()
    def get(self):
        """
        Export task types csv
        ---
        tags:
          - Export
        description: Export task types as CSV file. Includes department
          and task type name information.
        produces:
          - text/csv
        responses:
            200:
              description: Task types exported as CSV successfully
              content:
                text/csv:
                  schema:
                    type: string
                  example: "Department,Name\nAnimation,Animation\nModeling,Modeling"
        """
        return super().get()

    def build_headers(self):
        return ["Department", "Name"]

    def build_query(self):
        query = TaskType.query.order_by(Department.name, TaskType.name)
        query = query.join(Department, TaskType.department_id == Department.id)
        query = query.add_columns(Department.name)
        return query

    def build_row(self, task_type_row):
        (task_type, department_name) = task_type_row
        return [department_name, task_type.name]
