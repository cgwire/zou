[![Kitsu Logo](kitsu.png)](https://github.com/cgwire/zou)

# Welcome to the Kitsu API (Zou) documentation

The Kitsu API allows to store and manage the data of your animation/VFX production.
Through it you can link all the tools of your pipeline and make sure they are
all synchronized. 

To integrate it in your tools you can rely on the dedicated Python
client named [Gazu](https://gazu.cg-wire.com). 

# Who is it for?

The Kitsu API is made for Technical Directors, ITs and
Software Engineers from animation and VFX studios. With this API they can enhance
the tools they provide to the studio departments.

On top of the API, you can deploy the Kitsu frontend, which bring you the full
bundle of the collaboration platform developed by CGWire.

# Features 

The Kitsu API can:

* Store production data: projects, shots, assets, tasks, files
  metadata and validations.
* Store preview files of any kind.
* Publish an event stream of changes.
* Provide folder and file paths for any task.
* Export main data to CSV files.

For more details you can check [the full specification](https://kitsu-api.cg-wire.com).

# Quickstart (Docker Image)

To try Kitsu on your local machine you can use Docker to run a local
instance via this command:

*Warning: This image is not aimed at production usage.*

```
docker run -d -p 80:80 --name cgwire cgwire/cgwire
```

Then you can access to the Kitsu API, through `http://localhost/api` and
enjoy the Kitsu web UI at `http://localhost`.

The credentials are:

* login: admin@example.com
* password: mysecretpassword


# Install 

## Pre-requisites

The installation requires:

* Ubuntu (version >= 20.04)
* Python (version >= 3.6)
* An up and running Postgres instance (version >= 9.2)
* An up and running Redis server instance (version >= 2.0)
* A Nginx instance

## Setup


### Dependencies

First let's install third parties software:

```bash
sudo apt-get install postgresql postgresql-client postgresql-server-dev-all
sudo apt-get install redis-server
sudo apt-get install python3 python3-pip
sudo apt-get install git
sudo apt-get install nginx
sudo apt-get install ffmpeg
```

*NB: We recommend to install postgres in a separate machine.*


### Get sources

Create zou user:

```bash
sudo useradd --home /opt/zou zou 
sudo mkdir /opt/zou
sudo chown zou: /opt/zou
sudo mkdir /opt/zou/backups
sudo chown zou: /opt/zou/backups
```

Install Zou and its dependencies:

```
sudo pip3 install virtualenv
cd /opt/zou
sudo virtualenv zouenv
sudo /opt/zou/zouenv/bin/pip3 install zou
sudo chown -R zou:www-data .
```

Create a folder to store the previews:

```
sudo mkdir /opt/zou/previews
sudo chown -R zou:www-data /opt/zou
```

Create a folder to store the full text search indexes:

```
sudo mkdir /opt/zou/indexes
sudo chown -R zou:www-data /opt/zou/indexes
```

Create a folder to store the temp files:

```
sudo mkdir /opt/zou/tmp
sudo chown -R zou:www-data /opt/zou/tmp
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

Alternatively, if you want to set the password avoiding interactive prompts use : 
```bash
psql -U postgres -d postgres -c "alter user postgres with password 'mysecretpassword';"
```

Finally, create database tables (it is required to leave the posgres console
and to activate the Zou virtual environment):

```
# Run it in your bash console.
sudo -u zou DB_PASSWORD=yourdbpassword /opt/zou/zouenv/bin/zou init-db
```

*NB: You can specify a custom username and database. See the [configuration section](https://zou.cg-wire.com/configuration/).*

### Prepare key value store

Currently Redis require no extra configuration. 

To remove warnings in Redis logs and improve background saving success rate,
you can add this to `/etc/sysctl.conf`:

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
Environment="TMP_DIR=/opt/zou/tmp"
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
Environment="SECRET_KEY=yourrandomsecretkey" # Same one than zou.service
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
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
        send_timeout 600s;
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

*sudo service zou-events startNB: We use the 80 port here to make this documentation simpler but the 443 port and https connection are highly recommended.*

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
sudo systemctl enable zou
sudo systemctl enable zou-events
sudo systemctl start zou
sudo systemctl start zou-events
sudo systemctl restart nginx
```

## Update

### Update package

First, you have to upgrade the zou package:

```bash
cd /opt/zou
sudo /opt/zou/zouenv/bin/pip3 install --upgrade zou
```


### Update database schema

Then, you need to upgrade the database schema:

```bash
cd /opt/zou
sudo -u zou DB_PASSWORD=yourdbpassword /opt/zou/zouenv/bin/zou upgrade-db
```


### Restart the Zou service

Finally, restart the Zou service:

```bash
sudo chown -R zou:www-data .
sudo systemctl restart zou
sudo systemctl restart zou-events
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
cd kitsu
git config --global --add safe.directory /opt/kitsu
sudo git config --global --add safe.directory /opt/kitsu
sudo git checkout build
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
        client_max_body_size 500M;
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
        send_timeout 600s;
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
sudo systemctl restart nginx
```

You can now connect directly to your server IP through your browser and enjoy
Kitsu!


### Update Kitsu 

To update Kitsu, update the files through Git:

```
cd /opt/kitsu
sudo git reset --hard
sudo git pull --rebase origin build
```


## Admin users

To start with Zou you need to add an admin user. This user will be able to to
log in and to create other users. For that go into the terminal and run the
`zou` binary:

```
cd /opt/zou/
sudo -u zou DB_PASSWORD=yourdbpassword /opt/zou/zouenv/bin/zou create-admin adminemail@yourstudio.com
```

It expects the password as first argument. Then your user will be created with
the email as login, `default` as password and "Super Admin" as first name and
last name.

## Initialise data:

Some basic data are required by Kitsu to work properly (like project status) :

```
cd /opt/zou/
sudo -u zou DB_PASSWORD=yourdbpassword /opt/zou/zouenv/bin/zou init-data
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

Kitsu is written by CGWire, a company based in France. We help animation and
VFX studios to collaborate better through efficient tooling.

Visit [cg-wire.com](https://cg-wire.com) for more information.

[![CGWire Logo](cgwire.png)](https://cg-wire.com)
