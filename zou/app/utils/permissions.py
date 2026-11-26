from functools import wraps

from flask import g
from flask_jwt_extended import get_current_user, get_jwt
from werkzeug.exceptions import Forbidden


class PermissionDenied(Forbidden):
    pass


def _project_role():
    """
    Return the effective role that the project access check of the current
    request resolved, or None if no project context is resolved.
    """
    try:
        return g.get("project_role")
    except RuntimeError:
        return None


def _global_role():
    """
    Return the global role of the authenticated identity, or None outside
    an authenticated request context.
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


def _effective_role():
    """
    Return the effective role of the current identity: the project role if
    a project context is resolved, else the global role. Admin is a global
    role only. If a project slot holds "admin", the data is not valid: use
    the global role, and do not give admin-tier rights.
    """
    role = _project_role()
    return role if role not in (None, "admin") else _global_role()


def get_effective_role():
    """
    Return the effective role. This public function is for the callers
    that must key a response on it (e.g. an ETag). Resolve the project
    first, as for all permission checks.
    """
    return _effective_role()


def has_manager_permissions():
    """
    Tell whether the user is an admin or a manager. If a project context is
    resolved, use the project role.
    """
    return _effective_role() in ("admin", "manager")


def has_artist_permissions():
    """
    Tell whether the user is an artist on the resolved project. Without a
    project context, the result is always False: the function does not
    read the global role.
    """
    return _project_role() == "user"


def has_admin_permissions():
    """
    Tell whether the user is an admin. Admin is a global role only, so
    this check ignores the resolved project role.
    """
    return _global_role() == "admin"


def has_client_permissions():
    """
    Tell whether the user is a client. If a project context is
    resolved, use the project role.
    """
    return _effective_role() == "client"


def has_vendor_permissions():
    """
    Tell whether the user is a vendor. If a project context is
    resolved, use the project role.
    """
    return _effective_role() == "vendor"


def has_supervisor_permissions():
    """
    Tell whether the user is a supervisor. If a project context is
    resolved, use the project role.
    """
    return _effective_role() == "supervisor"


def has_person_permissions():
    """
    Tell whether the identity is a person (session or person API token)
    and not a bot.
    """
    return _auth_type() in ("person", "person_api")


def has_at_least_supervisor_permissions():
    """
    Tell whether the user is a supervisor, a manager or an admin. If a
    project context is resolved, use the project role.
    """
    return _effective_role() in ("admin", "manager", "supervisor")


def check_at_least_supervisor_permissions():
    """
    Return True if the user is an admin, a manager or a supervisor. Else,
    raise a PermissionDenied exception.
    """
    if has_at_least_supervisor_permissions():
        return True
    else:
        raise PermissionDenied


def check_manager_permissions():
    """
    Return True if the user is an admin or a manager. Else, raise a
    PermissionDenied exception.
    """
    if has_manager_permissions():
        return True
    else:
        raise PermissionDenied


def check_admin_permissions():
    """
    Return True if the user is an admin. Else, raise a PermissionDenied
    exception.
    """
    if has_admin_permissions():
        return True
    else:
        raise PermissionDenied


def check_person_permissions():
    """
    Return True if the user is a person. Else, raise a PermissionDenied
    exception.
    """
    if has_person_permissions():
        return True
    else:
        raise PermissionDenied


def require_admin(function):
    """
    Decorate a function to run check_admin_permissions() before it.
    """

    @wraps(function)
    def decorated_function(*args, **kwargs):
        check_admin_permissions()
        return function(*args, **kwargs)

    return decorated_function


def require_person(function):
    """
    Decorate a function to run check_person_permissions() before it.
    """

    @wraps(function)
    def decorated_function(*args, **kwargs):
        check_person_permissions()
        return function(*args, **kwargs)

    return decorated_function
