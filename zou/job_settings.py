from zou.app import config, create_app, db

REDIS_HOST = config.KEY_VALUE_STORE["host"]
REDIS_PORT = config.KEY_VALUE_STORE["port"]
REDIS_DB = config.KV_JOB_DB_INDEX
REDIS_PASSWORD = config.KEY_VALUE_STORE["password"]

# RQ runs each job in a fork of this process: build the application once
# here, which also syncs the config to Redis, so a job does not pay for a
# whole boot. Drop the database connections a plugin may have opened: a
# fork must not share them.
app = create_app()
with app.app_context():
    db.engine.dispose()
