"""
Compatibility alias. The domain exceptions are in ``zou.app.exceptions``.
Each layer (utils, models, services, blueprints) can import them from
there without an import of the services. Plugins that use this path
continue to work.
"""

from zou.app.exceptions import *  # noqa: F401,F403
