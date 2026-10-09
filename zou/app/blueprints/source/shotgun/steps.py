from flasgger import swag_from
from flask import current_app
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.models.department import Department
from zou.app.models.task_type import TaskType
from zou.app.utils import colors
from zou.app.services import (
    task_types_service,
)

from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)


class ImportShotgunStepsResource(BaseImportShotgunResource):
    def __init__(self):
        MethodView.__init__(self)

    @jwt_required()
    @swag_from("openapi/ImportShotgunStepsResource_post.yml")
    def post(self):
        """
        Import shotgun steps
        """
        return super().post()

    def extract_data(self, sg_step):
        color = self.extract_color(sg_step)
        department_name = self.extract_department_name(sg_step)
        return {
            "name": sg_step["code"],
            "short_name": sg_step.get("short_name", ""),
            "shotgun_id": sg_step["id"],
            "color": color,
            "department_name": department_name,
            "for_entity": sg_step.get("entity_type", "Asset"),
        }

    def extract_color(self, sg_step):
        color = sg_step.get("color", "0,0,0")
        return colors.rgb_to_hex(color)

    def extract_department_name(self, sg_step):
        splitted_name = sg_step["code"].split(" ")
        department_name = splitted_name[0]
        return department_name

    def import_entry(self, data):
        department = self.save_department(data)
        return self.save_task_type(department, data)

    def save_department(self, data):
        department = Department.get_by(name=data["department_name"])
        if department is None:
            department_data = {
                "name": data["department_name"],
                "color": data["color"],
            }
            department = Department(**department_data)
            department.save()
            current_app.logger.info(f"Department created: {department}")
        del data["department_name"]
        return department

    def save_task_type(self, department, data):
        task_type = TaskType.get_by(shotgun_id=data["shotgun_id"])
        data["department_id"] = department.id
        matched_by_name = False
        if task_type is None:
            # matched regardless of case: a step named after an existing
            # task type must update it rather than create a twin the
            # clients cannot tell apart, since they resolve them by name
            # and lower-case it on the way
            task_type = TaskType.get_by_case_insensitive(
                name=data["name"], for_entity=data["for_entity"]
            )
            matched_by_name = task_type is not None

        if task_type is None:
            task_type = TaskType(**data)
            task_type.save()
            current_app.logger.info(f"Task Type created: {task_type}")
        else:
            existing_task_type = TaskType.get_by_case_insensitive(
                name=data["name"],
                for_entity=data["for_entity"],
                department_id=data["department_id"],
            )
            if existing_task_type is not None:
                data.pop("name", None)
                data.pop("for_entity", None)
                data.pop("department_id", None)
            elif matched_by_name:
                # a task type matched in another case keeps its name, even
                # when the step moves it to another department
                data.pop("name", None)
            task_type.update(data)
            task_types_service.clear_task_type_cache(str(task_type.id))
            current_app.logger.info(f"Task Type updated: {task_type}")
        return task_type


class ImportRemoveShotgunStepResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(self, TaskType)

    @jwt_required()
    @swag_from("openapi/ImportRemoveShotgunStepResource_post.yml")
    def post(self):
        """
        Remove shotgun step
        """
        return super().post()
