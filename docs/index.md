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

# Quickstart (Docker Image)

To try Zou and Kitsu on your local machine you can use Docker to run a local
instance of the CGWire suite. For that, install docker and run this command:

*Warning: This image is not aimed at production usage.*


```
docker run -d -p 80:80 --name cgwire cgwire/cgwire
```

Then you can access to the Zou API through `http://localhost/api` and enjoy the Kitsu
web UI at `http://localhost`.


# Install 

## Pre-requisites

The installation requires:

* An up and running Postgres instance (version >= 9.2)
* An up and running Redis server instance (version >= 2.0)
* Python (version >= 2.7, version 3 is prefered)
* A Nginx instance
* Uwsgi

## Setup


### Dependencies

First let's install third parties software:

```bash
sudo apt-get install postgresql postgresql-client
sudo apt-get install redis-server
sudo apt-get install python3 python3-pip
sudo apt-get install git
sudo apt-get install nginx
```

*NB: We recommend to install postgres in a separate machine.*


### Get sources

Create zou user:

```bash
sudo useradd --home /opt/zou zou 
```

Install Zou and its dependencies:

```
sudo pip3 install virtualenv
cd /opt/zou
sudo virtualenv zouenv
. zouenv/bin/activate
sudo zouenv/bin/pip3 install zou
sudo chown -R zou:www-data .
```

Then create a folder to store the previews:

```
sudo mkdir /opt/zou/previews
sudo chown -R zou:www-data /opt/zou
```

If it complains about missing ffmpeg binary set properly the `FFMPEG_BINARY`
env variable (= the ffmpeg binary path).


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
DB_PASSWORD=yourdbpassword zou init_db
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

#### Configure main API server

First, create configuration folder:

```
sudo mkdir /etc/zou
```

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

Please note that environment variables are positioned here. `DB_PASSWORD` must
be set with your database password. `SECRET_KEY` must be generated randomly
(use `pwgen 16` command for that).

```
[Unit]
Description=Gunicorn instance to serve the Zou API
After=network.target

[Service]
User=zou
Group=www-data
WorkingDirectory=/opt/zou
# Append DB_USERNAME=username DB_HOST=server when default values aren't used
# ffmpeg must be in PATH
Environment="DB_PASSWORD=yourdbpassword"
Environment="SECRET_KEY=yourrandomsecretkey"
Environment="PATH=/opt/zou/zouenv/bin:/usr/bin"
Environment="PREVIEW_FOLDER=/opt/zou/previews"
ExecStart=/opt/zou/zouenv/bin/gunicorn  -c /etc/zou/gunicorn.conf -b 127.0.0.1:5000 zou.app:app

[Install]
WantedBy=multi-user.target
```

#### Configure Events Stream API server


Let's write the *gunicorn* configuration:

*Path: /etc/zou/gunicorn-events.conf*

```
accesslog = "/opt/zou/logs/gunicorn_events_access.log"
errorlog = "/opt/zou/logs/gunicorn_events_error.log"
workers = 1
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
```

Then we daemonize the *gunicorn* process via Systemd:

*Path: /etc/systemd/system/zou-events.service*

```
[Unit]
Description=Gunicorn instance to serve the Zou Events API
After=network.target

[Service]
User=zou
Group=www-data
WorkingDirectory=/opt/zou
# Append DB_USERNAME=username DB_HOST=server when default values aren't used
Environment="PATH=/opt/zou/zouenv/bin"
ExecStart=/opt/zou/zouenv/bin/gunicorn -c /etc/zou/gunicorn-events.conf -b 127.0.0.1:5001 zou.event_stream:app

[Install]
WantedBy=multi-user.target
```


### Configure Nginx

Finally we serve the API through a Nginx server. For that, add this
configuration file to Nginx to redirect the traffic to the Gunicorn servers:

*Path: /etc/nginx/sites-available/zou*

```nginx
server {
    listen 80;
    server_name server_domain_or_IP;

    location /api {
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_pass http://localhost:5000/;
        client_max_body_size 500M;
    }

    location /socket.io {
		proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header Upgrade $http_upgrade;
		proxy_set_header Connection "Upgrade";
        proxy_pass http://localhost:5001;
    }
}
```

*NB: We use the 80 port here to make this documentation simpler but the 443 port and https connection are highly recommended.*

Finally, make sure that default configuration is removed: 

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
sudo service zou-events start
sudo service nginx restart
```

## Update

### Update package

First, you have to upgrade the zou package:

```bash
cd /opt/zou
. zouenv/bin/activate
sudo zouenv/bin/pip3 install --upgrade zou
```


### Update database schema

Then, you need to upgrade the database schema:

```bash
DB_PASSWORD=yourdbpassword zou upgrade_db
```


### Restart the Zou service

Finally, restart the Zou service:

```bash
sudo chown -R zou:www-data .
sudo service zou restart
sudo service zou-events restart
```

That's it! Your Zou instance is now up to date. 

*NB: Make it sure by getting the API version number from `https://myzoudomain.com/api`.*


## Deploying Kitsu 

[Kitsu](https://kitsu.cg-wire.com) is a javascript UI that allows to manage Zou
data from the browser.

Deploying Kitsu requires to retrieve the built version. For that let's grab it
from Github: 

```
cd /opt/
sudo git clone -b build https://github.com/cgwire/kitsu
sudo git checkout build
chown -R zou:www-data /opt/kitsu
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

    location /socket.io {
		proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header Upgrade $http_upgrade;
		proxy_set_header Connection "Upgrade";
        proxy_pass http://localhost:5001;
    }

    location / {
        autoindex on;
        root  /opt/kitsu/dist;
        try_files $uri $uri/ /index.html;
        
    }
}
```

Restart your Nginx server:

```bash
sudo service nginx restart
```

You can now connect directly to your server IP through your browser and enjoy
Kitsu!


### Update Kitsu 

To update Kitsu, update the files through Git:

```
cd /opt/kitsu
git reset --hard
git pull --rebase origin build
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
DB_PASSWORD=yourdbpassword zou init_data
```

# Configuration 

To run properly, Zou requires a bunch of parameters you can give through
environment variables. These variables can be set in your systemd script. 
All variables are listed in the [configuration
section](configuration).

# Available actions

To know more about what is possible to do with the CGWire API, refer to the
[API section](api).

# Packaging

Get the sources, increment the version located in the `zou/__init__.py` file.
Tag the repository with the new version and run the following commands:

```bash
pip install wheel twine
python setup.py bdist_wheel
twine upload dist/<package>.whl
```

*NB: It requires access to Pypi CGWire repository.*

# About authors

Zou is written by CG Wire, a company based in France. We help small to
midsize CG studios to manage their production and build pipeline efficiently.

We apply software craftmanship principles as much as possible. We love
coding and consider that strong quality and good developer experience matter a lot.
Our extensive experience allows studios to get better at doing software and focus
more on the artistic work.

Visit [cg-wire.com](https://cg-wire.com) for more information.

[![CGWire Logo](cgwire.png)](https://cg-wire.com)
