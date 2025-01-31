[![Kitsu Logo](kitsu.png)](https://github.com/cgwire/zou)

# Welcome to the Kitsu API (Zou) documentation

The Kitsu API allows you to store and manage the data of your animation/VFX production.
Through it, you can link all the tools of your pipeline and make sure they are
all synchronized. 

To integrate it into your tools, you can rely on the dedicated Python
client named [Gazu](https://gazu.cg-wire.com). 

# Who is it for?

The Kitsu API is made for Technical Directors, ITs, and
Software Engineers from animation and VFX studios. With this API, they can enhance
the tools they provide to the studio departments.

On top of the API, you can deploy the Kitsu frontend, which brings you the full
bundle of the collaboration platform developed by CGWire.

# Features 

The Kitsu API can:

* Store production data: projects, shots, assets, tasks, files,
  metadata, and validations.
* Store preview files of any kind.
* Publish an event stream of changes.
* Provide folder and file paths for any task.
* Export main data to CSV files.

For more details, you can check [the full specification](https://api-docs.kitsu.cloud).

# Quickstart (Docker Image)

To try Kitsu on your local machine, you can use Docker to run a local
instance via this command:

*Warning: This image is not aimed at production usage.*

```
docker run -d -p 80:80 --name cgwire cgwire/cgwire
```

Then you can access the Kitsu API, through `http://localhost/api` and
enjoy the Kitsu web UI at `http://localhost`.

The credentials are:

* login: admin@example.com
* password: mysecretpassword


# Install 

## Hardware prerequisites

Users    | Cores | RAM
---------|-------|----
1-10     | 2     | 4
11 - 30  | 2     | 8
31 - 80  | 4     | 15
81 - 200 | 8     | 30

That's the recommended minimum. But it depends on the activity of the production/studio.

* The size of the files/videos sent
* The frequency with which files/videos are sent
* The network speed available between the workstations and the instance.

Regarding disk space, you need to allow for a factor of x2.5 x3 of all the files sent (large estimation).

It is advisable to separate:

* The database on another VM
* `PREVIEW_FOLDER` directory on a separate volume

This simplifies migration/augmentation of volumes.

## Pre-requisites

The installation requires:

* Ubuntu (version >= 20.04)
* Python (version >= 3.9)
* An up-and-running Postgres instance (version >= 9.2)
* An up-and-running Redis server instance (version >= 2.0)
* A Nginx instance


## Setup


### Dependencies

First, let's install third-party software:

```bash
sudo apt-get install postgresql postgresql-client postgresql-server-dev-all
sudo apt-get install build-essential
sudo apt-get install redis-server
sudo apt-get install nginx
sudo apt-get install xmlsec1
sudo apt-get install ffmpeg
```

*NB: We recommend installing Postgres on a separate machine.*

### Install Python 3.12

```
sudo apt-get install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
sudo apt-get install python3.12 python3.12-venv python3.12-dev
```

### Get sources

Create zou user:

```bash
sudo useradd --home /opt/zou zou 
sudo mkdir /opt/zou
sudo mkdir /opt/zou/backups
sudo chown zou: /opt/zou/backups
```

Install Zou and its dependencies:

```
sudo python3.12 -m venv /opt/zou/zouenv
sudo /opt/zou/zouenv/bin/python -m pip install --upgrade pip
sudo /opt/zou/zouenv/bin/python -m pip install zou
```

Create a folder to store the previews:

```
sudo mkdir /opt/zou/previews
sudo chown -R zou:www-data /opt/zou/previews
```

Create a folder to store the temp files:

```
sudo mkdir /opt/zou/tmp
sudo chown -R zou:www-data /opt/zou/tmp
```

### Prepare database

Create Zou database in Postgres:

```
sudo -u postgres psql -c 'create database zoudb;' -U postgres
```

Set a password for your postgres user. For that start the Postgres CLI:

```bash
sudo -u postgres psql
```

Then set the password (*mysecretpassword* if you want to do some tests).

```bash
psql (9.4.12)
Type "help" for help.

postgres=# \password postgres
Enter new password: 
Enter it again: 
```

Then, exit from the Postgres client console.

Alternatively, if you want to set the password to avoid interactive prompts, use: 
```bash
sudo -u postgres psql -U postgres -d postgres -c "alter user postgres with password 'mysecretpassword';"
```

`SECRET_KEY` must be generated randomly
(use `pwgen 16` command for that).

Create the environment variables file for the database:

*Path: /etc/zou/zou.env*
```bash
DB_PASSWORD=mysecretpassword
SECRET_KEY=yourrandomsecretkey
PREVIEW_FOLDER=/opt/zou/previews
TMP_DIR=/opt/zou/tmp
SECRET_KEY=yourrandomsecretkey

# If you add variables above, add the exports below
export DB_PASSWORD SECRET_KEY PREVIEW_FOLDER TMP_DIR SECRET_KEY
```

You need to have these variables in memory when you run a `zou` command.
The easiest way to do this is to run this command:

`. /etc/zou/zou.env`

This line is included with every command in the documentation so that you don't forget it. But you don't have to run it every time.

Finally, create database tables (it is required to leave the Postgres console
and to activate the Zou virtual environment):

```bash
# Run it in your bash console.
. /etc/zou/zou.env
/opt/zou/zouenv/bin/zou init-db
```

*NB: You can specify a custom username and database. See the [configuration section](https://zou.cg-wire.com/configuration/).*

### Prepare the key-value store

Currently, Redis requires no extra configuration. 

To remove warnings in Redis logs and improve background saving success rate,
you can add this to `/etc/sysctl.conf`:

```
vm.overcommit_memory = 1
```

If you want to do performance tuning, have a look at [this
article](https://www.techandme.se/performance-tips-for-redis-cache-server/).


### Set up the indexer (optional)

Create a Meilisearch user:

```
sudo useradd meilisearch 
```

Install Meilisearch:

```
echo "deb [trusted=yes] https://apt.fury.io/meilisearch/ /" | sudo tee /etc/apt/sources.list.d/fury.list
sudo apt-get update && sudo apt-get install meilisearch
```

Create a folder for the index:
```
sudo mkdir /opt/meilisearch
sudo chown -R meilisearch: /opt/meilisearch
```


Define a master key then create the service file for Meilisearch:

*Path: /etc/systemd/system/meilisearch.service*

```
[Unit]
Description=Meilisearch search engine
After=network.target

[Service]
User=meilisearch
Group=meilisearch
WorkingDirectory=/opt/meilisearch
ExecStart=/usr/bin/meilisearch --master-key="masterkey"

[Install]
WantedBy=multi-user.target
```

To finish, start the Meilisearch indexer:

```
sudo systemctl enable meilisearch
sudo systemctl start meilisearch
```


### Configure Gunicorn

#### Configure the main API server

First, create a configuration folder:

```
sudo mkdir /etc/zou
```

We need to run the application through *gunicorn*, a WSGI server that will run zou as a daemon. Let's write the *gunicorn* configuration:

*Path: /etc/zou/gunicorn.py*

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

Then we daemonize the *gunicorn* process via Systemd. For that, we add a new
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
# ffmpeg must be in PATH
Environment="PATH=/opt/zou/zouenv/bin:/usr/bin"
EnvironmentFile=/etc/zou/zou.env
ExecStart=/opt/zou/zouenv/bin/gunicorn  -c /etc/zou/gunicorn.py -b 127.0.0.1:5000 zou.app:app

[Install]
WantedBy=multi-user.target
```

#### Configure Events Stream API server


Let's write the *gunicorn* configuration:

*Path: /etc/zou/gunicorn-events.py*

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
Environment="PATH=/opt/zou/zouenv/bin"
EnvironmentFile=/etc/zou/zou.env
ExecStart=/opt/zou/zouenv/bin/gunicorn -c /etc/zou/gunicorn-events.py -b 127.0.0.1:5001 zou.event_stream:app

[Install]
WantedBy=multi-user.target
```


### Configure Nginx

Finally, we serve the API through a Nginx server. For that, add this
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

*NB: We use the 80 port here to make this documentation simpler but the 443 port and https connection are highly recommended.*

Finally, make sure that the default configuration is removed: 

```bash
sudo rm /etc/nginx/sites-enabled/default
```


We enable that Nginx configuration with this command:

```bash
sudo ln -s /etc/nginx/sites-available/zou /etc/nginx/sites-enabled/zou
```

Finally, we can start our daemon and restart Nginx:

```bash
sudo systemctl enable zou zou-events
sudo systemctl start zou zou-events
sudo systemctl restart nginx
```

## Update

### Update package

First, you have to upgrade the zou package:

```bash
sudo /opt/zou/zouenv/bin/python -m pip install --upgrade zou
```


### Update database schema

Then, you need to upgrade the database schema:

```bash
DB_PASSWORD=mysecretpassword /opt/zou/zouenv/bin/zou upgrade-db
```


### Restart the Zou service

Finally, restart the Zou service:

```bash
sudo systemctl restart zou zou-events
```

That's it! Your Zou instance is now up to date. 

*NB: Make it sure by getting the API version number from `https://myzoudomain.com/api`.*


## Deploying Kitsu 

[Kitsu](https://kitsu.cg-wire.com) is a javascript UI that allows to manage Zou
data from the browser.

Deploying Kitsu requires retrieving the built version. For that let's grab it
from Github: 

```
sudo mkdir -p /opt/kitsu/dist
curl -L -o /tmp/kitsu.tgz $(curl -v https://api.github.com/repos/cgwire/kitsu/releases/latest | grep 'browser_download_url.*kitsu-.*.tgz' | cut -d : -f 2,3 | tr -d \")
sudo tar xvzf /tmp/kitsu.tgz -C /opt/kitsu/dist/
rm /tmp/kitsu.tgz
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

To update Kitsu, update the files:

```
sudo rm -rf /opt/kitsu/dist
sudo mkdir /opt/kitsu/dist
curl -L -o /tmp/kitsu.tgz $(curl -v https://api.github.com/repos/cgwire/kitsu/releases/latest | grep 'browser_download_url.*kitsu-.*.tgz' | cut -d : -f 2,3 | tr -d \")
sudo tar xvzf /tmp/kitsu.tgz -C /opt/kitsu/dist/
rm /tmp/kitsu.tgz
```

## Initialise data:

Some basic data are required by Kitsu to work properly (like project status) :

```
. /etc/zou/zou.env
/opt/zou/zouenv/bin/zou init-data
```

If you have install the indexer, you can also index the data:

```
. /etc/zou/zou.env
/opt/zou/zouenv/bin/zou reset-search-index
```

## Admin users

To start with Zou you need to add an admin user. This user will be able to
log in and create other users. For that go into the terminal and run the
`zou` binary:

```
. /etc/zou/zou.env
/opt/zou/zouenv/bin/zou create-admin --password 1SecretPass adminemail@yourstudio.com
```

It expects the password as the first argument. Then your user will be created with
the email as login, `1SecretPass` as password, and "Super Admin" as first name and
last name.

# Configuration 

To run properly, Zou requires a bunch of parameters you can give through
environment variables. These variables can be set in your systemd script. 
All variables are listed in the [configuration
section](configuration).

# Available actions

To know more about what is possible to do with the CGWire API, refer to the
[API section](api).

# Packaging

Get the sources, and increment the version located in the `zou/__init__.py` file.
Tag the repository with the new version and run the following commands:

```bash
pip install wheel twine
python setup.py bdist_wheel
twine upload dist/<package>.whl
```

*NB: It requires access to Pypi CGWire repository.*

# About authors

Kitsu is written by CGWire, a company based in France. We help animation and
VFX studios collaborate better through efficient tooling.

Visit [cg-wire.com](https://cg-wire.com) for more information.

[![CGWire Logo](cgwire.png)](https://cg-wire.com)
