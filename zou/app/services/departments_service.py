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
    department = Department.get(department_id)
    if not department:
        raise DepartmentNotFoundException
    return department


def _check_software_exists(software_id):
    software = Software.get(software_id)
    if not software:
        raise SoftwareNotFoundException
    return software


def _check_hardware_item_exists(hardware_item_id):
    hardware_item = HardwareItem.get(hardware_item_id)
    if not hardware_item:
        raise HardwareItemNotFoundException
    return hardware_item


def get_all_software_for_departments():
    """
    Get all software items for all departments organized by department
    in a dictionary where the key is the department id and the value is a
    list of linked software items.
    """
    software_list = (
        Software.query.join(SoftwareDepartmentLink)
        .add_columns(SoftwareDepartmentLink.department_id)
        .all()
    )
    department_map = {}
    for software, department_id in software_list:
        if department_id not in department_map:
            department_map[department_id] = []
        department_map[department_id].append(software.serialize())
    return department_map


def get_all_hardware_items_for_departments():
    """
    Get all hardware items for all departments organized by department
    in a dictionary where the key is the department id and the value is a
    list of linked hardware items.
    """
    hardware_item_list = (
        HardwareItem.query.join(HardwareItemDepartmentLink)
        .add_columns(HardwareItemDepartmentLink.department_id)
        .all()
    )
    department_map = {}
    for hardware_item, department_id in hardware_item_list:
        if department_id not in department_map:
            department_map[department_id] = []
        department_map[department_id].append(hardware_item.serialize())
    return department_map


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
    else:
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
    else:
        link.delete()
        return link.serialize()
