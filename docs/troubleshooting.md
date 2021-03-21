# Troubleshooting

To solve issues related to your installation, you can do several actions to
get information about what is going wrong.

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
. zou/bin/activate
zou set_default_password email@studio.com
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
