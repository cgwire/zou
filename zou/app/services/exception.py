"""
Compatibility alias: the domain exceptions live in ``zou.app.exceptions``,
importable by every layer (utils, models, services, blueprints) without
pulling the services in. Plugins written against this path keep working.
"""

from zou.app.exceptions import *  # noqa: F401,F403
