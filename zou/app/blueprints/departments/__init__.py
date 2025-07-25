from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from zou.app.blueprints.departments.resources import (
    AllDepartmentSoftwareResource,
    AddSoftwareToDepartmentResource,
    SoftwareDepartmentResource,
    AllDepartmentHardwareItemsResource,
    AddHardwareItemToDepartmentResource,
    HardwareItemDepartmentResource,
)

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
]

blueprint = Blueprint("departments", "departments")
api = configure_api_from_blueprint(blueprint, routes)
