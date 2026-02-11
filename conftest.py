import os

# Must be set before zou.app is imported.
os.environ.setdefault("CACHE_TYPE", "simple")
os.environ.setdefault("BCRYPT_LOG_ROUNDS", "4")
