# Configuration

Zou requires several configuration parameters. In the following you will find
the list of all expected parameters.

## Database

* `DB_HOST` (default: localhost): The database server host.
* `DB_PORT` (default: 5432): The port on which the database is running.
* `DB_USERNAME` (default: postgres): The username used to access the database.
* `DB_PASSWORD` (default: mysecretpassword): The password used to access the
  database.
* `DB_DATABASE` (default: zoudb): The name of the database to use.

## Key Value store

* `KV_HOST` (default: localhost): The Redis server host.
* `KV_PORT` (default: 6379): The Redis server port.

## Authentication

* `AUTH_STRATEGY` (default: auth\_local\_classic): Allow to chose between
traditional auth and Active Directory auth (auth\_remote\_active\_directory).
* `SECRET_KEY` (default: mysecretkey) complex key used for auth token encryption.

## File trees

* `DEFAULT_FILE_TREE` (default: standard): The file tree to set by default on a
  project.
* `FILE_TREE_FOLDER` (default: /usr/local/share/zou/file_trees): The folder
  where your file tree definitions are stored.

## Event handlers 

* `EVENT_HANDLERS_FOLDER` (default: /usr/local/share/zou/thumbnails): The
  folder to put custom event handlers.

## Previews

* `PREVIEW_FOLDER` (default: /usr/local/share/zou/standard): The folder where
  thumbnails will be stored.

If you want to store you previews in a Swift backend, add the following
variables (Only Auth 2.0 and 3.0 is supported).

* `FS_BACKEND`: Set this variable with "swift"
* `FS_BUCKET_PREFIX`: A prefix for your bucket/container names.
* `FS_SWIFT_AUTH_URL`: Authentication URL of your swift backend.
* `FS_SWIFT_USER`: Your Swift login. 
* `FS_SWIFT_TENANT_NAME`: The Swift tenant name. 
* `FS_SWIFT_KEY`: Your Swift password. 
* `FS_SWIFT_REGION_NAME`: Your Swift region name. 

## Emails

Email configuration is required for mail sents after a password reset. In the
future, we expect to propose email notifications too.

* `MAIL_SERVER` (default: "localhost"): the host of your email server
* `MAIL_PORT` (default: "25"): the port of your email server
* `MAIL_USERNAME` (default: ""): the username to access to your mail server
* `MAIL_PASSWORD` (default: ""): the password to access to your mail server
* `MAIL_DEBUG` (default: "0"): set 1 if you are in a development environment
  (emails are printed in the console instead of being sent).
* `MAIL_USE_TLS` (default: "False"): To use TLS to communicate with the email
  server. 
* `MAIL_USE_SSL` (default: "False"): To use SSL to communicate with the email
  server.
* `MAIL_DEFAULT_SENDER` (default: "no-reply@cg-wire.com"): to set the sender
  email. 
* `DOMAIN_NAME` (default: "localhost:8080"): To build URLs (for password reset
  for instance).

## LDAP 

These variables are active only if auth\_remote\_ldap strategy is selected.

* `LDAP_HOST` (default: "127.0.0.1"): the IP address of your LDAP server.
* `LDAP_PORT` (default: "389"): the listening port of your LDAP server.
* `LDAP_BASE_DN` (default: "CN=Users,DC=studio,DC=local"): the base domain of your 
   LDAP configuration.
* `LDAP_DOMAIN` (default: "studio.local"): the domain used for your LDAP
  authentication (NTLM).
* `LDAP_FALLBACK` (default: "False"): Set to True if you want to allow admins
  to fallback on default auth strategy when the LDAP server is down.

## Misc 

* `TMP_DIR` (default: /tmp): The temporary directory used to handle uploads.
* `DEBUG` (default: False): Activate the debug mode for development purpose.
