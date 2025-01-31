# Data migration

## Raw mode

To migrate a Kitsu from an instance to another, you can simply dump the
database and restore it to the new instance. Once done, you have to move all 
the files stored in the preview folder to the preview folder of the new
instance.

## With Zou CLI

We assume here that you are evolving in the zou virtualenv environment and that
all your environment variables are loaded.

### Prepare the new instance (reset data)

Clear original database and rebuild tables:

```
. /etc/zou/zou.env
zou clear-db
zou reset-migrations
zou upgrade-db
```

### Get data

Retrieve base data:

```
. /etc/zou/zou.env
SYNC_LOGIN="admin@yourstudio.com" \
SYNC_PASSWORD="password" \
zou sync-full --source http://yourpreviouskitsu.url/api --no-projects
```

Retrieve project data:

```
. /etc/zou/zou.env
SYNC_LOGIN="admin@yourstudio.com" \
SYNC_PASSWORD="password" \
zou sync-full --source http://yourpreviouskitsu.url/api --only-projects
```

Retrieve a given project:

```
. /etc/zou/zou.env
SYNC_LOGIN="admin@yourstudio.com" \
SYNC_PASSWORD="password" \
zou sync-full --source http://yourpreviouskitsu.url/api --project AwesomeProject
```

If some changes occured after the migration, you can run the command again and
retrieve the difference. Beware that deletion won't be handled.

### Get files

The previous steps were used to retrieve the data stored in the database.

Retrieve all files:

```
. /etc/zou/zou.env
SYNC_LOGIN="admin@yourstudio.com" \
SYNC_PASSWORD="password" \
zou sync-full-files --source http://yourpreviouskitsu.url/api
```

Retrieve files for a given project:

```
. /etc/zou/zou.env
SYNC_LOGIN="admin@yourstudio.com" \
SYNC_PASSWORD="password" \
zou sync-full-files --source http://yourpreviouskitsu.url/api
```

If some changes occured after the migration, you can run the command again and
retrieve the difference. Beware that deletion won't be handled.
