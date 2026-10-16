from flask import Blueprint

from zou.app.blueprints.departments.resources import (
    AddHardwareItemToDepartmentResource,
    AddSoftwareToDepartmentResource,
    AllDepartmentHardwareItemsResource,
    AllDepartmentSoftwareResource,
    DepartmentPersonsResource,
    HardwareItemDepartmentResource,
    SoftwareDepartmentResource,
)
from zou.app.utils.api import configure_api_from_blueprint

routes = [
    ("/data/departments/software-licenses", AllDepartmentSoftwareResource),
    (
        "/data/departments/<department_id>/software-licenses",
        AddSoftwareToDepartmentResource,
    ),
    (
        "/data/departments/<department_id>/software-licenses/<software_id>",
        SoftwareDepartmentResource,
    ),
    ("/data/departments/hardware-items", AllDepartmentHardwareItemsResource),
    (
        "/data/departments/<department_id>/hardware-items",
        AddHardwareItemToDepartmentResource,
    ),
    (
        "/data/departments/<department_id>/hardware-items/<hardware_item_id>",
        HardwareItemDepartmentResource,
    ),
    ("/data/departments/<department_id>/persons", DepartmentPersonsResource),
]

blueprint = Blueprint("departments", "departments")
api = configure_api_from_blueprint(blueprint, routes)
