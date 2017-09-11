[![Zou Logo](zou.png)](https://github.com/cgwire/zou)

# Welcome to the Zou documentation

Zou is an API that allows to store and manage the data of your CG production.
Through it you can link all the tools of your pipeline and make sure they are
all synchronized. 

To integrate it quickly in your tools you can rely on the dedicated Python client 
named [Gazu](https://gazu.cg-wire.com). 

The source is available on [Github](https://github.com/cgwire/cgwire-api).

# Who is it for?

The audience for Zou is made of Technical Directors, ITs and
Software Engineers from CG studios. With Zou they can enhance the
tools they provide to all departments.

# Features 

Zou can:

* Store production data: projects, shots, assets, tasks, files
  metadata and validations.
* Provide folder and file paths for any task.
* Data import from Shotgun or CSV files.
* Export main data to CSV files.
* Provide helpers to manage task workflow (start, publish, retake).
* Provide an event system to plug external modules on it.

# Install 

## Pre-requisites

The installation requires:

* An up and running Postgres instance (version >= 9.2)
* An up and running Redis server instance (version >= 2.0)
* Python (version >= 2.7, version 3 is prefered)
* A Nginx instance
* Uwsgi

## Setup


### Dependecies

First let's install third parties software:

```bash
sudo apt-get install postgresql postgresql-client libpq-dev
sudo apt-get install redis-server
sudo apt-get install python3 python3-pip python3-dev
sudo apt-get install libffi-dev libjpeg-dev git
sudo apt-get install nginx
```

*NB: We recommend to install postgres in a separate machine.*


### Get sources

Create zou user:

```bash
sudo useradd --disabled-password --home /opt/zou zou 
```

Get sources:

```bash
cd /opt/
sudo git clone https://github.com/cgwire/zou.git
```

Install Python dependencies:

```
sudo pip3 install virtualenv
cd zou
sudo virtualenv zouenv
. zouenv/bin/activate
sudo zouenv/bin/python3 setup.py install
sudo chown -R zou:www-data .
sudo zouenv/bin/pip3 install gunicorn
sudo zouenv/bin/pip3 install gevent
```


### Prepare database

Create Zou database in postgres:

```
sudo su -l postgres
psql -c 'create database zoudb;' -U postgres
```

Set a password for your postgres user. For that start the Postgres CLI:

```bash
psql
```

Then set the password (*mysecretpassword* if you want to do some tests).

```bash
psql (9.4.12)
Type "help" for help.

postgres=# \password postgres
Enter new password: 
Enter it again: 
```

Then exit from the postgres client console.

Finally, create database tables (it is required to leave the posgres console
and to activate the Zou virtual environment):

```
# Run it in your bash console.
zou init_db
```

### Prepare key value store

Currently Redis require no extra configuration. 

To remove warnings in Redis logs and improve background saving success rate,
you can add this to `/etc/systcl.conf`:

```
vm.overcommit_memory = 1
```

If you want to do performance tuning, have a look at [this
article](https://www.techandme.se/performance-tips-for-redis-cache-server/).

### Configure Gunicorn

We need to run the application through *gunicorn*, a WSGI server that will run zou as a daemon. Let's write the *gunicorn* configuration:

*Path: /etc/zou/gunicorn.conf*

```
accesslog = "/opt/zou/logs/gunicorn_access.log"
errorlog = "/opt/zou/logs/gunicorn_error.log"
workers = 3
worker_class = "gevent"
```

Let's create the log folder:

```
sudo mkdir /opt/zou/logs
sudo chown zou: /opt/zou/logs
```

Then we daemonize the *gunicorn* process via Systemd. For that we add a new
file that will add a new daemon to be managed by Systemd:

*Path: /etc/systemd/system/zou.service*

```
[Unit]
Description=Gunicorn instance to serve the Zou API
After=network.target

[Service]
User=zou
Group=www-data
WorkingDirectory=/opt/zou
Environment="PATH=/opt/zou/zouenv/bin"
ExecStart=/opt/zou/zouenv/bin/gunicorn  -c /etc/zou/gunicorn.conf -b 127.0.0.1:5000 wsgi:application

[Install]
WantedBy=multi-user.target
```


### Configure Nginx

Finally we serve the API through a Nginx server. For that, add this
configuration file to Nginx to redirect the traffic to the *uwsgi* daemon:

*Path: /etc/nginx/sites-available/zou*

```nginx
server {
    listen 80;
    server_name server_domain_or_IP;

    location /api {
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_pass http://localhost:5000/;
    }
}
```

*NB: We use the 80 port here to make this documentation simpler but the 443 port and https connection are highly recommended.*

Make sure too that default configuration is removed: 

```bash
sudo rm /etc/nginx/sites-enabled/default
```


We enable that Nginx configuration with this command:

```bash
sudo ln -s /etc/nginx/sites-available/zou /etc/nginx/sites-enabled
```

Finally we can start our daemon and restart Nginx:

```bash
sudo service zou start
sudo service nginx restart
```

## Update


### Update database schema

#### Actions to run only the first time

This operation can break things, so backup your database before doing
this. 

First we need to install alembic, an utilitary that manages schema upgrade:

```
cd /opt/zou
. zouenv/bin/activate
pip install alembic
alembic init alembic
```

Then edit the `alembic.ini` file generated and add this line (modify it,
depending on your postgres database location):

```
sqlalchemy.url = postgres://postgres:mysecretpassword@localhost:5432/zoudb
```

And modify the `alembic/env.py` file to include this (replace the corresponding
lines):

```
from zou.app import db
target_metadata = db.Model.metadata
```


#### Actions to run each time

Then we need to generate the upgrade script. Each script require a new name,
so add a date each time you run this command. 

```
alembic revision --autogenerate -m "Release 2017-09-12"
```

Unique ids are not well supported by alembic so add this line to your alembic
script (the file generated through the previous command):

```
import sqlalchemy_utils
```

And run the following command:

```
sed -i 's/length=16/binary=False/g' alembic/versions/*
```

Then run the upgrade script.

```
alembic upgrade head
```

Your database is now ready to accept the new code.

### Update sources and dependencies

To update the application simply update the Zou sources and run the setup.py
command again. Once done, restart the Zou service.

```
cd /opt/zou
. zouenv/bin/activate
sudo zouenv/bin/python3 setup.py install
sudo chown -R zou:www-data .
sudo service zou restart
```

That's it! Your Zou instance should be up to date.


## Deploying Kitsu 

[Kitsu](https://kitsu.cg-wire.com) is a javascript UI that allows to manage Zou
data from the browser.

Deploying Kitsu requires to retrieve the built version. For that let's grab it
from Github: 

```
sudo mkdir /opt/kitsu
cd /opt/kitsu
sudo git clone -b build https://github.com/cgwire/kitsu
sudo git checkout build
chowm -R zou:www-data /opt/kitsu
```

Then we need to adapt the Nginx configuration to allow it to serve it properly:

```nginx
server {
    listen 80;
    server_name server_domain_or_IP;

    location /api {
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Host $host;
        proxy_pass http://localhost:5000/;
    }

    location / {
        autoindex on;
        root  /opt/kitsu/kitsu/dist;
    }
}
```

Restart your Nginx server:

```bash
sudo service nginx restart
```

You can now connect directly to your server IP through your browser and enjoy
Kitsu!


### Upgrade Kitsu 

To upgrade Kitsu, update the files through Git:

```
cd /opt/kitsu
git reset --hard
git pull origin build
```


## Admin users

To start with Zou you need to add an admin user. This user will be able to to
log in and to create other users. For that go into the terminal and run the
`zou` binary:

```
zou create_admin adminemail@yourstudio.com
```

It expects the password as first argument. Then your user will be created with
the email as login, `default` as password and "Super Admin" as first name and
last name.

## Initialise data:

Some basic data are required by Kitsu to work properly (like project status) :

```
zou init_data
```

# Configuration 

To run properly, Zou requires a bunch of parameters you can give through
environment variables. These variables can be set in your systemd script. 
All variables are listed in the [configuration
section](configuration).

# Available actions

To know more about what is possible to do with the CGWire API, refer to the
[API section](api).

# About authors

Zou is written by CG Wire, a company based in France. We help small to
midsize CG studios to manage their production and build pipeline efficiently.

We apply software craftmanship principles as much as possible. We love
coding and consider that strong quality and good developer experience matter a lot.
Our extensive experience allows studios to get better at doing software and focus
more on the artistic work.

Visit [cg-wire.com](https://cg-wire.com) for more information.

[![CGWire Logo](cgwire.png)](https://cg-wire.com)
