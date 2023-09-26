# Backup

It's a good practice to backup your database and your preview files. Here is a
quick guide to backup all the required files. You will find information too
about how to restore them.

## Backup database

To run a backup of the Zou database, run the following command:

```bash
cd /opt/zou/backups
DB_PASSWORD=mysecretpassword /opt/zou/zouenv/bin/zou dump-database
```

All data will be stored in a file in the current directory.  The generated file
name will follow this format: `2021-03-21-zou-db-backup.sql.gz`


*Restoration*

To restore the database to a new Postgres instance make sure the source and target version 
of the api match, otherwise the database schema may not match, if all matches run

```bash
gunzip 2021-03-21-zou-db-backup.sql.gz
createdb -h localhost -p 5432 -U postgres targetdb
psql -h yourphost -p 5432 -U postgres -1 -d targetdb -f 2021-03-21-zou-db-backup.sql
```
you can also just write directly to zoudb (the default database):
```bash
gunzip 2021-03-21-zou-db-backup.sql.gz
psql -h yourphost -p 5432 -U postgres -1 -d zoudb -f 2021-03-21-zou-db-backup.sql
```
when writing to a previously created database, make sure to terminate all the connections to said 
database by using the following statement:
```bash
SELECT pg_terminate_backend (pid) FROM pg_stat_activity WHERE datname = 'zoudb';
```
you can also change the name of a database to convert it to the default db:
```bash
ALTER DATABASE targetdb RENAME TO zoudb;
```
you can also change the database being used by using an environment variable in

/etc/systemd/system/zou.service
```bash
Environment="DB_DATABASE=targetdb"
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
