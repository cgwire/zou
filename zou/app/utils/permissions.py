from functools import wraps
from flask_principal import RoleNeed, Permission
from werkzeug.exceptions import Forbidden

admin_permission = Permission(RoleNeed("admin"))
manager_permission = Permission(RoleNeed("manager"))
supervisor_permission = Permission(RoleNeed("supervisor"))
client_permission = Permission(RoleNeed("client"))
vendor_permission = Permission(RoleNeed("vendor"))


class PermissionDenied(Forbidden):
    pass


def has_manager_permissions():
    """
    Return True if user is an admin or a manager.
    """
    return admin_permission.can() or manager_permission.can()


def has_admin_permissions():
    """
    Return True if user is an admin.
    """
    return admin_permission.can()


def has_client_permissions():
    """
    Return True if user is a client.
    """
    return client_permission.can()


def has_vendor_permissions():
    """
    Return True if user is a vendor.
    """
    return vendor_permission.can()


def has_supervisor_permissions():
    """
    Return True if user is a supervisor.
    """
    return supervisor_permission.can()


def check_manager_permissions():
    """
    Return True if user is admin or manager. It raises a PermissionDenied
    exception in case of failure.
    """
    if has_manager_permissions():
        return True
    else:
        raise PermissionDenied


def check_admin_permissions():
    """
    Return True if user is admin. It raises a PermissionDenied exception in case
    of failure.
    """
    if admin_permission.can():
        return True
    else:
        raise PermissionDenied


def require_admin(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        check_admin_permissions()
        return function(*args, **kwargs)

    return decorated_function


def require_manager(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        check_manager_permissions()
        return function(*args, **kwargs)

    return decorated_function
