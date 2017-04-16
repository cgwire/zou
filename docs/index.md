[![Zou Logo](zou.png)](https://github.com/cgwire/zou)

# Welcome to the Zou documentation

Zou is an API that allows to store and manage the data of your CG production.
Through it you can link all the tools of your pipeline and make sure they are
all synchronized. 

To integrate it quickly in your tools you can rely on the dedicated Python client 
named [Gazu](https://gazu.cg-wire.com). 

The source is available on [Github](https://github.com/cgwire/cgwire-api).

# Who is it for?

The audience for Zou is made of Technical Directors, ITs and
Software Engineers from CG studios. With Zou they can enhance the
tools they provide to all departments.

# Features 

Zou can:

* Store production data: projects, shots, assets, tasks, files
  metadata and validations.
* Provide folder and file paths for any task.
* Data import from Shotgun or CSV files.
* Export main data to CSV files.
* Provide helpers to manage task workflow (start, publish, retake).
* Provide an event system to plug external modules on it.

# Install 

## Pre-requisites

The installation requires:

* An up and running Postgres instance (version >= 9.2)
* Python (version >= 2.7)
* A Nginx instance
* Uwsgi

## Setup

First let's install third parties software:

```bash
sudo apt-get install postgres python nginx uwsgi
```

*NB: We recommend to install postgres in a separate machine.*


The following command will install Zou components on your machine:

```bash
pip install git+https://github.com/cgwire/cgwire-api.git
```

Then, we need to start a daemon with `uwsgi` and to redirect incoming traffic to that
server.


Let's write the `uwsgi` configuration:

*Path: /etc/zou/uwsgi.ini*

```
[uwsgi]
module = wsgi

master = true
processes = 5

socket = zou.sock
chmod-socket = 660
vacuum = true

die-on-term = true
```

Then we demonize `uwsgi` via upstart:

*Path: /etc/init/zou.conf*

```
description "uWSGI server instance configured to serve the Zou API"

start on runlevel [2345]
stop on runlevel [!2345]

setuid zou
setgid www-data

env PATH=/home/user/myproject/myprojectenv/bin
chdir /home/user/myproject
exec uwsgi --ini myproject.ini
```


Finally we serve the API through a Nginx server. For that, add this
configuration file to Nginx:

*Path: /etc/nginx/sites-available/zou*

```
server {
    listen 80;
    server_name server_domain_or_IP;

    location / {
        include uwsgi_params;
        uwsgi_pass unix:/tmp/zou.sock;
    }
}
```

*NB: We use the 80 port here to make things simpler but the 443 port and https connection are highly recommended.*


We enable that Nginx configuration with this command:

```bash
sudo ln -s /etc/nginx/sites-available/zou /etc/nginx/sites-enabled
```

Finally we can start our daemon and restart Nginx:

```bash
sudo service zou start
sudo service nginx restart
```

# Configuration 

To run properly, Zou requires a bunch of parameters you can give through
environment variables. All variables are listed in the [configuration
section](configuration).

# Available actions

To know more about what is possible to do with the CGWire API, refer to the
[API section](api).


# About authors

Zou is written by CG Wire, a company based in France. We help small to
midsize CG studios to manage their production and build pipeline efficiently.

We apply software craftmanship principles as much as possible. We love
coding and consider that strong quality and good developer experience matter a lot.
Our extensive experience allows studios to get better at doing software and focus
more on the artistic work.

Visit [cg-wire.com](https://cg-wire.com) for more information.

[![CGWire Logo](cgwire.png)](https://cgwire.com)
