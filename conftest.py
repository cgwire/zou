import os

# Force SimpleCache for tests to avoid Redis network overhead.
# This must be set before zou.app is imported.
os.environ.setdefault("CACHE_TYPE", "simple")
