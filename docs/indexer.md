# Data indexation

To allow full-text search, Kitsu relies on an Indexing engine. It uses the
[Meilisearch](https://www.meilisearch.com/docs) technology.

The indexer is optional. Kitsu can run without it.

## Setup the indexer

Create a Meilisearch user:

```
sudo useradd meilisearch 
```

Install the Meilisearch package:

```
# Add Meilisearch package
echo "deb [trusted=yes] https://apt.fury.io/meilisearch/ /" | sudo tee /etc/apt/sources.list.d/fury.list

# Update APT and install Meilisearch
sudo apt update && sudo apt install meilisearch
```

Create a folder for the index:

```
sudo mkdir /opt/meilisearch
sudo chown -R meilisearch: /opt/meilisearch
```

Define a master key (any alphanumeric string with 16 or more bytes) then create the service file for Meilisearch:

*Path: /etc/systemd/system/meilisearch.service*

```
[Unit]
Description=Meilisearch search engine
After=network.target

[Service]
User=meilisearch
Group=meilisearch
ExecStart=/usr/bin/meilisearch --master-key="masterkey"

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
zou reset-search-index
```