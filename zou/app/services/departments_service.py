from sqlalchemy.orm import selectinload

from zou.app.exceptions import (
    DepartmentNotFoundException,
    HardwareItemNotFoundException,
    SoftwareNotFoundException,
)
from zou.app.models.department import (
    Department,
    HardwareItemDepartmentLink,
    SoftwareDepartmentLink,
)
from zou.app.models.hardware_item import HardwareItem
from zou.app.models.person import DepartmentLink, Person
from zou.app.models.software import Software
from zou.app.services import (
    base_service,
    task_types_service,
)
from zou.app.utils import cache, events, fields


def _check_department_exists(department_id):
    """
    Return the department that has the given ID as an active record. If it
    does not exist, raise DepartmentNotFoundException.
    """
    department = Department.get(department_id)
    if not department:
        raise DepartmentNotFoundException
    return department


def _check_software_exists(software_id):
    """
    Return the software that has the given ID as an active record. If it
    does not exist, raise SoftwareNotFoundException.
    """
    software = Software.get(software_id)
    if not software:
        raise SoftwareNotFoundException
    return software


def _check_hardware_item_exists(hardware_item_id):
    """
    Return the hardware item that has the given ID as an active record. If
    it does not exist, raise HardwareItemNotFoundException.
    """
    hardware_item = HardwareItem.get(hardware_item_id)
    if not hardware_item:
        raise HardwareItemNotFoundException
    return hardware_item


def _group_by_department(model, link_model):
    """
    Return the serialized rows of the given model, grouped by their linked
    department. The result is a dict: the key is the department ID.
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
    Return the software items of all departments as a dict. The key is the
    department ID and the value is the list of linked software items.
    """
    return _group_by_department(Software, SoftwareDepartmentLink)


def get_all_hardware_items_for_departments():
    """
    Return the hardware items of all departments as a dict. The key is the
    department ID and the value is the list of linked hardware items.
    """
    return _group_by_department(HardwareItem, HardwareItemDepartmentLink)


def get_software_for_department(department_id):
    """
    Return all the software items of the given department.
    """
    _check_department_exists(department_id)
    return fields.serialize_models(
        Software.query.join(SoftwareDepartmentLink)
        .filter(SoftwareDepartmentLink.department_id == department_id)
        .all()
    )


def get_persons_for_department(department_id, minimal=False):
    """
    Return all the persons of the given department.
    """
    _check_department_exists(department_id)
    persons = (
        Person.query.join(
            DepartmentLink, DepartmentLink.person_id == Person.id
        )
        .filter(DepartmentLink.department_id == department_id)
        .options(selectinload(Person.departments))
        .order_by(Person.first_name, Person.last_name)
        .all()
    )
    return [
        (
            person.present_minimal(relations=True)
            if minimal
            else person.serialize_safe(relations=True)
        )
        for person in persons
    ]


def get_hardware_items_for_department(department_id):
    """
    Return all the hardware items of the given department.
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
    Remove a software item from a department. Return the removed link as a
    dict. If the software was not linked, return None.
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
    Remove a hardware item from a department. Return the removed link as a
    dict. If the hardware item was not linked, return None.
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


def clear_department_cache(department_id):
    """
    Remove the memoized serializations of the given department and of the
    department list.
    """
    cache.cache.delete_memoized(get_department, department_id)
    cache.cache.delete_memoized(get_departments)


@cache.memoize_function(120)
def get_departments():
    """
    Return every department.
    """
    return fields.serialize_models(Department.get_all())


@cache.memoize_function(120)
def get_department(department_id):
    """
    Return the department that has the given ID as a dict.
    """
    return base_service.get_instance(
        Department, department_id, DepartmentNotFoundException
    ).serialize()


def get_department_from_task_type(task_type_id):
    """
    Return the department of the given task type as a dict.
    """
    task_type = task_types_service.get_task_type_raw(task_type_id)
    return get_department(task_type.department_id)


def get_or_create_department(name, color="#000000"):
    """
    Return the department that has the given name as a dict. If it does not
    exist, create it and emit a department:new event.
    """
    department = Department.get_by(name=name)
    if department is None:
        department = Department(name=name, color=color)
        department.save()
        clear_department_cache(department.id)
        events.emit("department:new", {"department_id": department.id})
    return department.serialize()
