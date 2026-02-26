# Data indexation

To allow full-text search, Kitsu relies on an Indexing engine. It uses the
[Meilisearch](https://www.meilisearch.com/docs) technology.

The indexer is optional. Kitsu can run without it.

## Setup the indexer

Create a Meilisearch user:

```
sudo useradd -d /var/lib/meilisearch -s /bin/false -m -r meilisearch
```

Install the Meilisearch package:

```
sudo apt install curl -y
# Install Meilisearch latest version from the script
curl -L https://install.meilisearch.com | sh
# Make the binary accessible from anywhere in your system
sudo mv ./meilisearch /usr/local/bin/
sudo chown meilisearch:meilisearch /usr/local/bin/meilisearch
```

Create the configuration folder:

```
sudo mkdir /var/lib/meilisearch/data /var/lib/meilisearch/dumps /var/lib/meilisearch/snapshots
sudo chown -R meilisearch: /var/lib/meilisearch
sudo chmod 750 /var/lib/meilisearch
sudo curl https://raw.githubusercontent.com/meilisearch/meilisearch/latest/config.toml > /etc/meilisearch.toml
```

Define a master key (any alphanumeric string with 16 or more bytes).

Edit the configuration file:

```
sudo vim /etc/meilisearch.toml
```

```
db_path = "/var/lib/meilisearch/data"
env = "production"
master_key = "masterkey"
dump_dir = "/var/lib/meilisearch/dumps"
snapshot_dir = "/var/lib/meilisearch/snapshots"
```

Then create the service file for Meilisearch:

*Path: /etc/systemd/system/meilisearch.service*

```
[Unit]
Description=Meilisearch
After=systemd-user-sessions.service

[Service]
Type=simple
WorkingDirectory=/var/lib/meilisearch
ExecStart=/usr/local/bin/meilisearch --config-file-path /etc/meilisearch.toml
User=meilisearch
Group=meilisearch
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Finally, start the Meilisearch indexer:

```
sudo systemctl enable meilisearch
sudo systemctl start meilisearch
```


## Configuring the connection to the indexer

To connect to the indexer Kitsu relies on three environment variables.
Add them to the zou environment variables file.

*Path: /etc/zou/zou.env*

The first one is the master key you set when you started Meilisearch.

```
INDEXER_KEY="masterkey"
```

The two other variables are the indexer API location (host and port): 

```
INDEXER_HOST="localhost"
INDEXER_PORT="7700"
```

Add these variables on the "export..." line.

Once set, Kitsu will be able to connect to the indexer and will enable
full-text search.

## Verify the indexer is up and running

Browse to [http://localhost/api/status](http://localhost/api/status)
You should see "indexer-up": "true"


## Refreshing indexes

If for any reason, the indexer was not running during changes in the Kitsu
database, you can reset it at any time. Simply use this command (assuming all
environment variables are correctly set).

```
. /etc/zou/zou.env
/opt/zou/zouenv/bin/zou reset-search-index
```
