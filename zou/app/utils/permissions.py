from functools import wraps

from flask import g
from flask_jwt_extended import get_current_user, get_jwt
from werkzeug.exceptions import Forbidden


class PermissionDenied(Forbidden):
    pass


def _project_role():
    """
    Return the effective role resolved by the current request's project
    access check, or None when no project context has been resolved.
    """
    try:
        return g.get("project_role")
    except RuntimeError:
        return None


def _global_role():
    """
    Return the authenticated identity's global role, or None outside an
    authenticated request context.
    """
    try:
        user = get_current_user()
    except RuntimeError:
        return None
    if user is None:
        return None
    return getattr(user.role, "code", user.role)


def _auth_type():
    """
    Return the JWT identity type (person, bot or person_api), or None
    outside an authenticated request context.
    """
    try:
        return get_jwt().get("identity_type")
    except RuntimeError:
        return None


def has_manager_permissions():
    """
    Return True if user is an admin or a manager, using the project role
    when a project context is resolved.
    """
    role = _project_role()
    if role is not None:
        return role == "manager"
    return _global_role() in ("admin", "manager")


def has_artist_permissions():
    """
    Return True if user is an artist on the resolved project. Without a
    project context this is always False: Flask-Principal never granted a
    "user" need, so the historical global fallback is preserved as-is.
    """
    role = _project_role()
    if role is not None:
        return role == "user"
    return False


def has_admin_permissions():
    """
    Return True if user is an admin.
    """
    return _global_role() == "admin"


def has_client_permissions():
    """
    Return True if user is a client, using the project role when a project
    context is resolved.
    """
    role = _project_role()
    if role is not None:
        return role == "client"
    return _global_role() == "client"


def has_vendor_permissions():
    """
    Return True if user is a vendor, using the project role when a project
    context is resolved.
    """
    role = _project_role()
    if role is not None:
        return role == "vendor"
    return _global_role() == "vendor"


def has_supervisor_permissions():
    """
    Return True if user is a supervisor, using the project role when a
    project context is resolved.
    """
    role = _project_role()
    if role is not None:
        return role == "supervisor"
    return _global_role() == "supervisor"


def has_person_permissions():
    """
    Return True if user is a person.
    """
    return _auth_type() in ("person", "person_api")


def has_at_least_supervisor_permissions():
    """
    Return True if user is a supervisor, a manager or an admin, using the
    project role when a project context is resolved.
    """
    role = _project_role()
    if role is not None:
        return role in ("supervisor", "manager")
    return _global_role() in ("admin", "manager", "supervisor")


def check_at_least_supervisor_permissions():
    """
    Return True if user is admin, manager or supervisor. It raises a
    PermissionDenied exception in case of failure.
    """
    if has_at_least_supervisor_permissions():
        return True
    else:
        raise PermissionDenied


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
    if has_admin_permissions():
        return True
    else:
        raise PermissionDenied


def check_person_permissions():
    """
    Return True if user is a person. It raises a PermissionDenied exception in
    case of failure.
    """
    if has_person_permissions():
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


def require_person(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        check_person_permissions()
        return function(*args, **kwargs)

    return decorated_function
