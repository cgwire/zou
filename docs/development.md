# Development environment

To start with developing on Zou you need Python installed (2 or 3) and a
Postgres database instance. 

## Database

To run Postgres we recommend to use Docker (it's simpler and it won't impact
your local system):

```bash
sudo docker pull postgres
sudo docker start postgres
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
pip install -r requirements_test.txt 
```

## Init data

Create a database in postgres named `zou` with user `postgres` and password
`mysecretpassword`. Then init db:

```bash
bin/zou reset_db
bin/zou init_data
```

Create a first user:

```bash
bin/zou create_admin
```

Run server:

```bash
bin/zou runserver
```

You can now use the API by requesting `http://localhost:5000`.


## Tests

To run unit tests we recommend to use another database. For that set the
`DB_DATABASE` environment variable:

```bash
DB_DATABASE=zou-test py.test
```
