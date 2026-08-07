from zou.app.models.department import (
    Department,
    SoftwareDepartmentLink,
    HardwareItemDepartmentLink,
)
from zou.app.models.hardware_item import HardwareItem
from zou.app.models.software import Software
from zou.app.utils import fields

from zou.app.services.exception import (
    DepartmentNotFoundException,
    SoftwareNotFoundException,
    HardwareItemNotFoundException,
)


def _check_department_exists(department_id):
    """
    Raise if no department matches given id, and return it.
    """
    department = Department.get(department_id)
    if not department:
        raise DepartmentNotFoundException
    return department


def _check_software_exists(software_id):
    """
    Raise if no software matches given id, and return it.
    """
    software = Software.get(software_id)
    if not software:
        raise SoftwareNotFoundException
    return software


def _check_hardware_item_exists(hardware_item_id):
    """
    Raise if no hardware item matches given id, and return it.
    """
    hardware_item = HardwareItem.get(hardware_item_id)
    if not hardware_item:
        raise HardwareItemNotFoundException
    return hardware_item


def _group_by_department(model, link_model):
    """
    Return the serialized rows of given model grouped by the department they
    are linked to, as a dictionary keyed by department id.
    """
    rows = (
        model.query.join(link_model)
        .add_columns(link_model.department_id)
        .all()
    )
    department_map = {}
    for instance, department_id in rows:
        department_map.setdefault(department_id, []).append(
            instance.serialize()
        )
    return department_map


def get_all_software_for_departments():
    """
    Get all software items for all departments organized by department
    in a dictionary where the key is the department id and the value is a
    list of linked software items.
    """
    return _group_by_department(Software, SoftwareDepartmentLink)


def get_all_hardware_items_for_departments():
    """
    Get all hardware items for all departments organized by department
    in a dictionary where the key is the department id and the value is a
    list of linked hardware items.
    """
    return _group_by_department(HardwareItem, HardwareItemDepartmentLink)


def get_software_for_department(department_id):
    """
    Get all software items for a given department.
    """
    _check_department_exists(department_id)
    return fields.serialize_models(
        Software.query.join(SoftwareDepartmentLink)
        .filter(SoftwareDepartmentLink.department_id == department_id)
        .all()
    )


def get_hardware_items_for_department(department_id):
    """
    Get all hardware items for a given department.
    """
    _check_department_exists(department_id)
    return fields.serialize_models(
        HardwareItem.query.join(HardwareItemDepartmentLink)
        .filter(HardwareItemDepartmentLink.department_id == department_id)
        .all()
    )


def add_software_to_department(department_id, software_id):
    """
    Add a software item to a department.
    """
    _check_department_exists(department_id)
    _check_software_exists(software_id)
    link = SoftwareDepartmentLink.get_or_create(
        department_id=department_id, software_id=software_id
    )
    return link.serialize()


def remove_software_from_department(department_id, software_id):
    """
    Remove a software item from a department.
    """
    _check_department_exists(department_id)
    _check_software_exists(software_id)
    link = SoftwareDepartmentLink.get_by(
        department_id=department_id, software_id=software_id
    )
    if not link:
        return None
    link.delete()
    return link.serialize()


def add_hardware_item_to_department(department_id, hardware_item_id):
    """
    Add a hardware item to a department.
    """
    _check_department_exists(department_id)
    _check_hardware_item_exists(hardware_item_id)
    link = HardwareItemDepartmentLink.get_or_create(
        department_id=department_id, hardware_item_id=hardware_item_id
    )
    return link.serialize()


def remove_hardware_item_from_department(department_id, hardware_item_id):
    """
    Remove a hardware item from a department.
    """
    _check_department_exists(department_id)
    _check_hardware_item_exists(hardware_item_id)
    link = HardwareItemDepartmentLink.get_by(
        department_id=department_id, hardware_item_id=hardware_item_id
    )
    if not link:
        return None
    link.delete()
    return link.serialize()
