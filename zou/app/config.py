import os
import datetime

from zou.app.utils import dbhelpers

PROPAGATE_EXCEPTIONS = True
RESTFUL_JSON = {"ensure_ascii": False}
DEBUG = os.getenv("DEBUG", 0)

APP_NAME = "Zou"
APP_SYSTEM_ERROR_SUBJECT_LINE = "%s system error" % APP_NAME
SECRET_KEY = os.getenv("SECRET_KEY", "mysecretkey")

AUTH_STRATEGY = os.getenv("AUTH_STRATEGY", "auth_local_classic")

KEY_VALUE_STORE = {
    "host": os.getenv("KV_HOST", "localhost"),
    "port": os.getenv("KV_PORT", "6379"),
}
AUTH_TOKEN_BLACKLIST_KV_INDEX = 0
MEMOIZE_DB_INDEX = 1
KV_EVENTS_DB_INDEX = 2
KV_JOB_DB_INDEX = 3

JWT_BLACKLIST_ENABLED = True
JWT_BLACKLIST_TOKEN_CHECKS = ["access", "refresh"]
JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(days=7)
JWT_REFRESH_TOKEN_EXPIRES = datetime.timedelta(days=15)
JWT_TOKEN_LOCATION = ["cookies", "headers"]
JWT_REFRESH_COOKIE_PATH = "/auth/refresh-token"
JWT_COOKIE_CSRF_PROTECT = False
JWT_SESSION_COOKIE = False
JWT_COOKIE_SAMESITE = "Lax"

DATABASE = {
    "drivername": os.getenv("DB_DRIVER", "postgresql"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "username": os.getenv("DB_USERNAME", "postgres"),
    "password": os.getenv("DB_PASSWORD", "mysecretpassword"),
    "database": os.getenv("DB_DATABASE", "zoudb"),
}
SQLALCHEMY_DATABASE_URI = str(dbhelpers.get_db_uri())
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_size": int(os.getenv("DB_POOL_SIZE", 30)),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", 60)),
}

NB_RECORDS_PER_PAGE = 100

PREVIEW_FOLDER = os.getenv(
    "PREVIEW_FOLDER", os.getenv("THUMBNAIL_FOLDER", "previews")
)
TMP_DIR = os.getenv("TMP_DIR", os.path.join(os.sep, "tmp", "zou"))

EVENT_STREAM_HOST = os.getenv("EVENT_STREAM_HOST", "localhost")
EVENT_STREAM_PORT = os.getenv("EVENT_STREAM_PORT", 5001)
EVENT_HANDLERS_FOLDER = os.getenv(
    "EVENT_HANDLERS_FOLDER", os.path.join(os.getcwd(), "event_handlers")
)

MAIL_SERVER = os.getenv("MAIL_SERVER", "localhost")
MAIL_PORT = os.getenv("MAIL_PORT", 25)
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_DEBUG = os.getenv("MAIL_DEBUG", 0) != 0
MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "False").lower() == "true"
MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "False").lower() == "true"
MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "no-reply@cg-wire.com")
if os.getenv("MAIL_SUPPRESS_SEND") is not None:
    MAIL_SUPPRESS_SEND = os.getenv("MAIL_SUPPRESS_SEND")
DOMAIN_NAME = os.getenv("DOMAIN_NAME", "localhost:8080")
DOMAIN_PROTOCOL = os.getenv("DOMAIN_PROTOCOL", "https")

PLUGIN_FOLDER = os.getenv(
    "PLUGIN_FOLDER", os.path.join(os.getcwd(), "plugins")
)

FS_BACKEND = os.getenv("FS_BACKEND", "local")
FS_ROOT = PREVIEW_FOLDER
FS_BUCKET_PREFIX = os.getenv("FS_BUCKET_PREFIX", "")
FS_SWIFT_AUTHURL = os.getenv("FS_SWIFT_AUTHURL")
FS_SWIFT_USER = os.getenv("FS_SWIFT_USER")
FS_SWIFT_TENANT_NAME = os.getenv("FS_SWIFT_TENANT_NAME")
FS_SWIFT_KEY = os.getenv("FS_SWIFT_KEY")
FS_SWIFT_REGION_NAME = os.getenv("FS_SWIFT_REGION_NAME")
FS_S3_REGION = os.getenv("FS_S3_REGION")
FS_S3_ENDPOINT = os.getenv("FS_S3_ENDPOINT")
FS_S3_ACCESS_KEY = os.getenv("FS_S3_ACCESS_KEY")
FS_S3_SECRET_KEY = os.getenv("FS_S3_SECRET_KEY")

ENABLE_JOB_QUEUE = os.getenv("ENABLE_JOB_QUEUE", "False").lower() == "true"
ENABLE_JOB_QUEUE_REMOTE = (
    os.getenv("ENABLE_JOB_QUEUE_REMOTE", "False").lower() == "true"
)
JOB_QUEUE_NOMAD_PLAYLIST_JOB = os.getenv(
    "JOB_QUEUE_NOMAD_PLAYLIST_JOB", "zou-playlist"
)
JOB_QUEUE_NOMAD_NORMALIZE_JOB = os.getenv("JOB_QUEUE_NOMAD_NORMALIZE_JOB", "")
JOB_QUEUE_NOMAD_HOST = os.getenv("JOB_QUEUE_NOMAD_HOST", "zou-nomad-01.zou")
JOB_QUEUE_TIMEOUT = os.getenv("JOB_QUEUE_TIMEOUT", 3600)


LDAP_HOST = os.getenv("LDAP_HOST", "127.0.0.1")
LDAP_PORT = os.getenv("LDAP_PORT", "389")
LDAP_BASE_DN = os.getenv("LDAP_BASE_DN", "cn=Users,dc=zou,dc=local")
LDAP_GROUP = os.getenv("LDAP_GROUP", "")
LDAP_DOMAIN = os.getenv("LDAP_DOMAIN", "zou.local")
LDAP_FALLBACK = os.getenv("LDAP_FALLBACK", "False").lower() == "true"
LDAP_IS_AD = os.getenv("LDAP_IS_AD", "False").lower() == "true"
LDAP_IS_AD_SIMPLE = os.getenv("LDAP_IS_AD_SIMPLE", "False").lower() == "true"
LDAP_SSL = os.getenv("LDAP_SSL", "False").lower() == "true"


LOGS_MODE = os.getenv("LOGS_MODE", "default")
LOGS_HOST = os.getenv("LOGS_HOST", "localhost")
LOGS_PORT = os.getenv("LOGS_PORT", 2202)
LOGS_TOKEN = os.getenv("LOGS_TOKEN")

CRISP_TOKEN = os.getenv("CRISP_TOKEN", "")

USER_LIMIT = int(os.getenv("USER_LIMIT", "100"))

DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Europe/Paris")

# Deprecated
TO_REVIEW_TASK_STATUS = "To review"
DEFAULT_FILE_STATUS = "To review"
DEFAULT_FILE_TREE = os.getenv("DEFAULT_FILE_TREE", "default")
FILE_TREE_FOLDER = os.getenv("FILE_TREE_FOLDER")
