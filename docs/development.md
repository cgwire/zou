# Development environment

To start with developing on Zou you need Python installed (2 or 3) and a
Postgres database instance. 

## Database

To run Postgres we recommend to use Docker (it's simpler and it won't impact
your local system):

```bash
sudo docker pull postgres
sudo docker run postgres \
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
    --name unit-redis \
    -p 6379:6379 \
    -d redis
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

Create a virtual environment with `mkvirtualenv`:

```bash
pip install mkvirtualenv
mkvirtualenv zou
workon zou
```

Install dependencies:

```bash
pip install -r requirements.txt 
```

## Init data

Create a database in postgres named `zou` with user `postgres` and password
`mysecretpassword`. Then init db:

```bash
python zou/cli.py clear_db
python zou/cli.py init_db
python zou/cli.py init_data
```

Create a first user:

```bash
python zou/cli.py create_admin super.user@mycgstudio.com
```

Run server:

```bash
python zou/cli.py runserver
```

You can now use the API by requesting `http://localhost:5000`.


## Tests

To run unit tests we recommend to use another database. For that set the
`DB_DATABASE` environment variable:

```bash
DB_DATABASE=zou-test py.test
```
