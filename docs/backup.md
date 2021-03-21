# Backup

It's a good practice to backup your database and your preview files. Here is a
quick guide to backup all the required files. You will find information too
about how to restore them.

## Backup database

To run a backup of the Zou database, run the following command:

```bash
cd /opt/zou
. zouenv/bin/activate
DB_PASSWORD=yourdbpassword zou dump-database
```

All data will be stored in a file in the current directory.  The generated file
name will follow this format: `2021-03-21-zou-db-backup.sql.gz`


*Restoration*

To restore the database to a new Postgres instance run

```bash
gunzip 2021-03-21-zou-db-backup.sql.gz
createdb -h localhost -p 5432 -U postgres targetdb
pg_restore -h yourphost -p 5432 -U postgres -d targetdb 2021-03-21-zou-db-backup.sql
```


## Backup files

If you rely on an object storage, you have to check with your provider
that your data are properly replicated.

If you store your files directly on your drive, you must backup the preview
folder (`/opt/zou/previews` by default). There are plenty of documentation and
tools available on the internet to do that. We won't cover this subject here.

*Restoration*

To restore the files you simply have to put the files from your backups the
directory you want. Then make sure thate the `PREVIEW_FOLDER` environment
variable targets it properly.
