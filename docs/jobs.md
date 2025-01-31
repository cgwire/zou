# Job Queue

To run jobs asynchronously in a job queue, an additional service
is required.


## What will be run in the job queue

* Playlists build
* Event handlers loaded in Zou


## Enabling job queue

Set `ENABLE_JOB_QUEUE` environment variable to `True` in the variables file (/etc/zou/zou.env).

## S3 Storage

If your variables file (/etc/zou/zou.env) uses a S3 backend.

* `FS_BACKEND`: Set this variable with "s3"
* `FS_BUCKET_PREFIX`: A prefix for your bucket names, it's mandatory to 
   set it to properly use S3.
* `FS_S3_REGION`: Example: *eu-west-3*
* `FS_S3_ENDPOINT`: The url of your region. 
   Example: *https://s3.eu-west-3.amazonaws.com*
* `FS_S3_ACCESS_KEY`: Your user access key.
* `FS_S3_SECRET_KEY`: Your user secret key.

If not yet installed, install the following package in your virtual environment:

```
sudo /opt/zou/zouenv/bin/python -m pip install boto3
```

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
EnvironmentFile=/etc/zou/zou.env
Environment="PATH=/opt/zou/zouenv/bin:/usr/bin"
ExecStart=/opt/zou/zouenv/bin/rq worker -c zou.job_settings 

[Install]
WantedBy=multi-user.target
```

Start the service:
```
sudo systemctl enable zou-jobs
sudo systemctl start zou-jobs
```
