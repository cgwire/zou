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

## File trees

* `DEFAULT_FILE_TREE` (default: standard): The file tree to set by default on a
  project.
* `FILE_TREE_FOLDER` (default: /usr/local/share/zou/file_trees): The folder
  where your file tree definitions are stored.

## Event handlers 

* `EVENT_HANDLERS_FOLDER` (default: /usr/local/share/zou/thumbnails): The
  folder to put custom event handlers.


## Thumbnails

* `THUMBNAIL_FOLDER` (default: /usr/local/share/zou/standard): The folder where
  thumbnails will be stored.

## Misc 

* `TMP_DIR` (default: /tmp): The temporary directory used to handle uploads.
