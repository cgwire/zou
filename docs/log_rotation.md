# Log rotation

Log produced by the API grow quickly and lead to big log files. You will need
quickly to configure `logrotate` to create a new log file every day.


## Store PID of zou processes

To create a folder on boot to store pid files add a RuntimeDirectory add a line
before ExecStart in the unit file
(`/etc/systemd/system/zou.service`):

```
RuntimeDirectory=zou
```

Add this to the ExecStart line to create the pid file for zou

```
-p /run/zou/zou.pid
```
For example:
> ExecStart=/opt/zou/zouenv/bin/gunicorn -p /run/zou/zou.pid  -c /etc/zou/gunicorn.conf -b 127.0.0.1:5000 zou.app:app

Edit the zou-events unit file to create the pid file for zou-events  
(`/etc/systemd/system/zou-events.service`):

```
-p /run/zou/zou-events.pid
```

PIDs are now stored in mentioned files. 

## Configure logrotate

We can now proceed to the Logrotate configuration. Logrotate is a Unix tool 
that will handle the log rotation for you. It just requires a configuration 
file to work properly.

Add this logrotate configuration (`/etc/logrotate.d/zou`):

```
/opt/zou/logs/gunicorn_access.log {
    daily
    missingok
    rotate 14
    notifempty
    nocompress
    size 100M
    create 644 zou zou
    postrotate
        kill -USR1 `cat /run/zou/zou.pid`
    endscript
}

/opt/zou/logs/gunicorn_error.log {
    daily
    missingok
    rotate 14
    nocompress
    size 100M
    notifempty
    create 644 zou zou
    postrotate
        kill -USR1 `cat /run/zou/zou.pid`
    endscript
}

/opt/zou/logs/gunicorn_events_access.log {
    daily
    missingok
    rotate 14
    nocompress
    size 100M
    notifempty
    create 644 zou zou
    postrotate
        kill -USR1 `cat /run/zou/zou-events.pid`
    endscript
}

/opt/zou/logs/gunicorn_events_error.log {
    daily
    missingok
    rotate 14
    nocompress
    size 100M
    notifempty
    create 644 zou zou
    postrotate
        kill -USR1 `cat /run/zou/zou-events.pid`
    endscript
}
```

It will create a new log file for each day, and keep only the last 14 files.

You can test the log rotation is set up correctly by running
```
logrotate /etc/logrotate.d/zou --debug
```
You're done with log rotation!
