# Log rotation

Log produced by the API grow quickly and lead to big log files. You will need
quickly to configure `logrotate` to create a new log file every day.


## Store PID of zou processes

Add this folder and change owner to `zou` user:

```
mkdir /var/run/zou
chown zou: /var/run/zou
```

Add this line to Zou gunicorn configuration file (`/etc/zou/gunicorn.conf`):

```
PIDFile=/var/run/zou/zou.pid
```

Add this line to Zou Events gunicorn configuration file 
(`/etc/zou/gunicorn-events.conf`):

```
PIDFile=/var/run/zou/zou-events.pid
```

PIDs are now stored in mentioned files. 

## Configure logrotate

We can now proceed to the Logrotate configuration. Logrotate is a Unix tool 
that will handle the log rotation for you. It just requires a configuration 
file to work properly.

Add this logrotate configuration (`/etc/logrotate.d/zou`):

```
/var/log/zou/gunicorn_access.log {
    daily
    missingok
    rotate 14
    notifempty
    nocompress
    size 100M
    create 640 zou zou
    postrotate
        kill -USR1 `cat /run/zou/zou.pid`
    endscript
}

/var/log/zou/gunicorn_error.log {
    daily
    missingok
    rotate 14
    nocompress
    size 100M
    notifempty
    create 640 zou zou
    postrotate
        kill -USR1 `cat /run/zou/zou.pid`
    endscript
}

/var/log/zou/gunicorn_events_access.log {
    daily
    missingok
    rotate 14
    nocompress
    size 100M
    notifempty
    create 640 zou zou
    postrotate
        kill -USR1 `cat /run/zou/zou-events.pid`
    endscript
}

/var/log/zou/gunicorn_events_error.log {
    daily
    missingok
    rotate 14
    nocompress
    size 100M
    notifempty
    create 640 zou zou
    postrotate
        kill -USR1 `cat /run/zou/zou-events.pid`
    endscript
}
```

It will create a new log file for each day, and keep only the last 14 files.
You're done with log rotation!
