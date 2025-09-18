# Configuration

Zou requires several configuration parameters. In the following, you will find
the list of all expected parameters.

## Database

* `DB_HOST` (default: localhost): The database server host.
* `DB_PORT` (default: 5432): The port on which the database is running.
* `DB_USERNAME` (default: postgres): The username used to access the database.
* `DB_PASSWORD` (default: mysecretpassword): The password used to access the
  database.
* `DB_DATABASE` (default: zoudb): The database name to use.
* `DB_POOL_SIZE` (default: 30): The number of connections opened simultaneously 
  to access the database.
* `DB_MAX_OVERFLOW` (default: 60): The number of additional connections available 
  once the pool is full. They are disconnected when the request is finished. They
  are not reused.

## Key-Value store

* `KV_HOST` (default: localhost): The Redis server host.
* `KV_PORT` (default: 6379): The Redis server port.

## Indexer

Kitsu uses the Meilisearch service for its indexation.

* `INDEXER_KEY` (default: masterkey): The key required by Meilisearch.
* `INDEXER_HOST` (default: localhost): The Meilisearch host.
* `INDEXER_PORT` (default: 7700): The Meilisearch port.

## Authentication

* `AUTH_STRATEGY` (default: auth\_local\_classic): Allow to choose between
traditional auth and Active Directory auth (auth\_remote\_active\_directory).
* `SECRET_KEY` (default: mysecretkey) Complex key used for auth token encryption.

## Previews

* `PREVIEW_FOLDER` (default: ./previews): The folder where
  thumbnails will be stored. The default value is set for development
  environments. We encourage you to set an absolute path when you use it in
  production.
* `REMOVE_FILES` (default: "False"): Delete files when deleting comments and revisions

## Users

* `USER_LIMIT` (default: "100"): Max number of users
* `MIN_PASSWORD_LENGTH` (default: "8"): The minimum password length
* `DEFAULT_TIMEZONE` (default: "Europe/Paris"): The default timezone for new user accounts
* `DEFAULT_LOCALE` (default: "en_US"): The default language for new user accounts

## Emails

The email configuration is required for emails sent after a password reset and,
email notifications.

* `MAIL_SERVER` (default: "localhost"): The host of your email server
* `MAIL_PORT` (default: "25"): The port of your email server
* `MAIL_USERNAME` (default: ""): The username to access to your mail server
* `MAIL_PASSWORD` (default: ""): The password to access to your mail server
* `MAIL_DEBUG` (default: "0"): Set 1 if you are in a development environment
  (emails are printed in the console instead of being sent).
* `MAIL_USE_TLS` (default: "False"): To use TLS to communicate with the email
  server.
* `MAIL_USE_SSL` (default: "False"): To use SSL to communicate with the email
  server.
* `MAIL_DEFAULT_SENDER` (default: "no-reply@cg-wire.com"): To set the sender
  email.
* `DOMAIN_NAME` (default: "localhost:8080"): To build URLs (for a password reset
  for instance).
* `DOMAIN_PROTOCOL` (default: "https"): To build URLs (for a password reset
  for instance).

You can find more information here:
https://flask-mail.readthedocs.io/en/latest/

## Indexes

* `INDEXES_FOLDER` (default: "./indexes"): The folder to store your indexes, we
  recommend to set a full path here.


## S3 Storage

If you want to store your previews in an S3 backend, add the following
variables (we assume that you created a programmatic user that can access
to S3).

* `FS_BACKEND`: Set this variable with "s3"
* `FS_BUCKET_PREFIX`: A prefix for your bucket names. It's mandatory to 
   set it to properly use S3.
* `FS_S3_REGION`: Example: *eu-west-3*
* `FS_S3_ENDPOINT`: The url of your region. 
   Example: *https://s3.eu-west-3.amazonaws.com*
* `FS_S3_ACCESS_KEY`: Your user access key.
* `FS_S3_SECRET_KEY`: Your user secret key.

Then install the following package in your virtual environment:

```
cd /opt/zou
. zouenv/bin/activate
pip install boto3
```

When you restart Zou, it should use S3 to store and retrieve files.

## Swift Storage

If you want to store your previews in a Swift backend, add the following
variables (Only Auth 2.0 and 3.0 are supported).

* `FS_BACKEND`: Set this variable with "swift"
* `FS_BUCKET_PREFIX`: A prefix for your bucket/container names.
* `FS_SWIFT_AUTH_URL`: Authentication URL of your swift backend.
* `FS_SWIFT_USER`: Your Swift login.
* `FS_SWIFT_TENANT_NAME`: The Swift tenant name.
* `FS_SWIFT_KEY`: Your Swift password.
* `FS_SWIFT_REGION_NAME`: Your Swift region name.

## LDAP

These variables are active only if auth\_remote\_ldap strategy is selected.

* `LDAP_HOST` (default: "127.0.0.1"): The IP address of your LDAP server.
* `LDAP_PORT` (default: "389"): The listening port of your LDAP server.
* `LDAP_BASE_DN` (default: "CN=Users,DC=studio,DC=local"): The base domain of your
   LDAP configuration.
* `LDAP_DOMAIN` (default: "studio.local"): The domain used for your LDAP
  authentication (NTLM).
* `LDAP_FALLBACK` (default: "False"): Set to True if you want to allow admins
  to fallback on default auth strategy when the LDAP server is down.
* `LDAP_IS_AD` (default: "False"): Set to True if you use LDAP with an active directory.


## Job queue

* `ENABLE_JOB_QUEUE` (default: "False"): Set to True if you want to send
  asynchronous tasks to the `zou-jobs` service.
* `JOB_QUEUE_TIMEOUT` (default: 3600): Set the timeout (in seconds) for preview and playlist encoding jobs sent to the `zou-jobs` service.
* `ENABLE_JOB_QUEUE_REMOTE` (default: "False"): Set to True if you want to send
  playlist builds to a Nomad cluster.


## Misc

* `TMP_DIR` (default: /tmp): The temporary directory used to handle uploads.
* `DEBUG` (default: False): Activate the debug mode for development purposes.
* `CRISP TOKEN` (default: ): Activate the Crisp support chatbox on the bottom right.
* `REMOVE_FILES` (default: False): If set to True, Zou will delete files from storage when their entries are removed via the API (e.g. preview files or attachments). When False, the database record is removed but the file remains on disk.
* `EVENT_HANDLERS_FOLDER` (default: ): Path to the folder where custom event handler scripts are stored. Zou will load scripts from this directory if provided.
* `DEFAULT_TIMEZONE` (default: UTC): The default timezone used by Zou for timestamp fields when none is explicitly provided. Affects display of times in the UI and in logs.
* `DEFAULT_LOCALE` (default: en): The locale used for formatting dates, numbers, and other locale-sensitive content in Zou’s UI.

