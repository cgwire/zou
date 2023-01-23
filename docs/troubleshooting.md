# Troubleshooting

To solve issues related to your installation, you can do several actions to
get information about what is going wrong.


## Database status

Prior to look for logs or any clue about your problem, make sure that the
database is up and up to date:

```bash
DB_PASSWORD=yourdbpassword zou upgrade-db
```

## Error logs

Main error logs are stored in the `/opt/zou/gunicorn_error.log` file. Errors 
can be explicit. They can tell what is going wrong.

## Status route


To know if all the required services are up, you can connect to the following
route: `http://kitsu.mystudio.com/api/status`.

You should see something like this:

```javascript
{
    "name": "Zou"
    "database-up": true,
    "event-stream-up": true,
    "job-queue-up": true,
    "key-value-store-up": true,
    "version": "0.11.3",
}
```

If one of the service is set to false, it means that it is down or that
Zou cannot connect to it. Zou cannot run properly in that case.

NB: Database refers to Posgres, Key Value Store refers to Redis, Event
Stream refers to `zou-events` service, job queue refers to `zou-rq` service.

# Changing password

If, for any reasons, the user cannot access to his rest password email, you can
put his password back to "default" with the following command:

```bash
cd /opt/zou
. zouenv/bin/activate
DB_PASSWORD=yourdbpassword zou set-default-password email@studio.com
```

## Installing on Ubuntu server or minimal desktop

Zou install will require `libjpeg-dev` to be installed at the 3rd party
software step:

```bash
sudo apt-get install libjpeg-dev
```

## To enable zou to start on reboot

```bash
sudo systemctl enable zou

sudo systemctl enable zou-events
```


## Job queue

Error logs are not displayed in the zou error log files. So you have to check
directly the service logs if you look for error messages related to
asynchronous jobs (email sending, video normalization and playlist buird).

To see the job queue logs, run the following command:

```bash
journalctl -u zou-rq.service
```

## Postgres connection slots

If your Zou server complains by the lack of connection to Postgres available, 
you can increase the value of `BD_POOL_SIZE` (default 30) and 
`DB_MAX_OVERFLOW` (default 60). They are two environment variables that must be
set in your systemd configuration alongside the others. 

If the problem persists, you can dig into 
[pgpool](https://pgpool.net/mediawiki/index.php/Main_Page) software.


## Playlist build failing

### Unmatching resolutions

If your previews have different resolutions, the build will fail. Make sure
your playlists have movies with the same size.

The build doesn't include pictures, only movies are included.

### Disk space

Check logs and look for: `OSError: [Errno 28] No space left on device`

Make sure it's coherent with what your system tells:

```
df -h
du -sh /opt/zou/previews/movies
du -sh /opt/zou/previews/files
du -sh /opt/zou/previews/pictures
```

The error is explicit: your drive is full. You have three options there:

* Add more space
* Delete unused files
* Delete data into Kitsu old projects, old shots or old preview revisions (or
  both).

### Unable to successfully upgrade from a much earlier version

If your current working version of Zou is much earlier than the latest 
version, upgrading directly to the latest may cause problems with the database.
This is because occasionally important changes are made to the database during
the upgrade process.

The solution is to upgrade in smaller steps, making sure you don't miss any 
critical versions.  Since it can be hard to know which version is critical,
one option is to apply all updates one after the other.

The following script can assist by making updating to a specific version and
then incrementing to the next quite easy.  Add your database password and
edit for any other path differences is run as <script name> <zou version>
eg; ./zou_to_version.sh 0.14.12

```
cd /opt/zou
. zouenv/bin/activate
zouenv/bin/pip3 install 'zou=='$1 #this is the version number variable
DB_PASSWORD=<db password here> zou upgrade-db
deactivate
chown -R zou:www-data .
service zou restart
service zou-events restart
```