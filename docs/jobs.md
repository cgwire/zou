# Job Queue

To run jobs asynchronously in a job queue, an additional service
is required.


## What will be run in the job queue

* Playlists build
* Event handlers loaded in Zou


## Enabling job queue

Set `ENABLE_JOB_QUEUE` environment variable to `True` in the main service file.


## Setting up RQ, the job manager

Create a systemd file:

*Path: /etc/systemd/system/zou-jobs.service*

```
[Unit]
Description=RQ Job queue to run asynchronous job from Zou
After=network.target

[Service]
User=zou
Group=www-data
WorkingDirectory=/opt/zou
Environment="DB_PASSWORD=yourdbpassword"
Environment="SECRET_KEY=yourrandomsecretkey"
Environment="PATH=/opt/zou/zouenv/bin:/usr/bin"
Environment="PREVIEW_FOLDER=/opt/zou/previews"
ExecStart=/opt/zou/zouenv/bin/rq worker -c zou.job_settings 

[Install]
WantedBy=multi-user.target
```
