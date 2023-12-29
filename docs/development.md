# Development environment

To start with developing on Zou you need Python 3 installed and a
Postgres database instance.

## Database

To run Postgres we recommend to use Docker (it's simpler and it won't impact
your local system):

```bash
sudo docker pull postgres
sudo docker run \
    --name postgres \
    -p 5432:5432 \
    -e POSTGRES_PASSWORD=mysecretpassword \
    -d postgres
```

## Key-value store

To run Redis we recommend to use Docker again:

```bash
sudo docker pull redis
sudo docker run \
    --name redis \
    -p 6379:6379 \
    -d redis
```

## Indexer

To run Meilisearch we recommend to use Docker again:

```bash
sudo docker pull getmeili/meilisearch:v1.5
sudo docker run -it --rm \      
    --name meilisearch \               
    -p 7700:7700 \
    -e MEILI_ENV='development' \
    -e MEILI_MASTER_KEY='meilimasterkey' \
    -v $(pwd)/meili_data:/meili_data \
    -d getmeili/meilisearch:v1.5
```

## FFMPEG

For video operations, it is required to have FFMPEG installed. For that, simply install it through your OS package manager:

```
sudo apt-get install ffmpeg
```


## Source and dependencies

Then get Zou sources:

```bash
git clone git@github.com:cgwire/zou.git
```

Install `virtualenvwrapper`:

```bash
pip install virtualenvwrapper
```

Add configuration for `virtualenvwrapper` to your .bashrc:

```bash
export WORKON_HOME=directory_for_virtualenvs
VIRTUALENVWRAPPER_PYTHON=/usr/bin/python3
source ~/.local/bin/virtualenvwrapper.sh
```

Create a virtual environment with `mkvirtualenv`:

```bash
mkvirtualenv zou
workon zou
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Init data

Create a database in postgres named `zoudb` with user `postgres` and password
`mysecretpassword`. Then init db:

```bash
python zou/cli.py clear-db
python zou/cli.py init-db
python zou/cli.py init-data
```

Create a first user:

```bash
python zou/cli.py create-admin super.user@mycgstudio.com --password=mysecretpassword
```

Run server:

```bash
PREVIEW_FOLDER=$PWD/previews DEBUG=1 MAIL_DEBUG=1 FLASK_DEBUG=1 FLASK_APP=zou.app INDEXER_KEY=meilimasterkey python zou/debug.py
```

You can now use the API by requesting `http://localhost:5000`.


## Update database
In case of adding/removing attributes of models, you must generate the DB update file:

```
python zou/cli.py migrate-db
```

### Event server

To run the Server Events server used to update the web GUI in realtime, use the
following command.

```bash
gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker -b 127.0.0.1:5001 -w 1 zou.event_stream:app
```

## Tests

To run unit tests we recommend to use another database. 

### Create testing database

In the CLI of the hosting the PostgreSQL DB execute the following:
*If Docker, connect with: `docker exec -it postgres bash`*

```
sudo su -l postgres
psql -c 'create database zoutest;' -U postgres
```

### Run the tests

In your zou environment `workon zou`, execute the tests with the `DB_DATABASE` environment variable:

```
DB_DATABASE=zoutest py.test
```

If you want to run a specific test (you can list several):

```
DB_DATABASE=zoutest py.test tests/models/test_entity_type.py
```

### Debug email sending

If you set properly the `MAIL_DEBUG=1` flag, the body of each sent email is
displayed in the console.
