# Data indexation

To allow full-text search, Kitsu relies on an Indexing engine. It uses the
[Meilisearch](https://www.meilisearch.com/docs) technology.

The indexer is optional. Kitsu can run without it.

## Setup the indexer

First, retrieve the Meilisearch package:

```
# Add Meilisearch package
echo "deb [trusted=yes] https://apt.fury.io/meilisearch/ /" | sudo tee /etc/apt/sources.list.d/fury.list

# Update APT and install Meilisearch
sudo apt update && sudo apt install meilisearch
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
ExecStart=/usr/bin/meilisearch --master-key="yourmasterkey"

[Install]
WantedBy=multi-user.target
```

Finally, start the Meilisearch indexer:

```
sudo service meilisearch start
```



## Configuring the connection to the indexer

To connect to the indexer Kitsu relies on three environment variables.

The first one is the master key you set when you started Meilisearch.

```
INDEXER_KEY="yourkey"
```

The two other variables are the indexer API location (host and port): 

```
INDEXER_HOST="localhost"
INDEXER_PORT="7700"
```

Once set, Kitsu will be able to connect to the indexer and will enable
full-text search.


## Refreshing indexes

If for any reason, the indexer was not running during changes in the Kitsu
database, you can reset it at any time. Simply use this command (assuming all
environment variables are properly set).

```
zou reset-search-index zou reset-search-index
```

Or add directly your environment variables in the command:

```
DB_PASSWORD=yourdbpasword INDEXER_KEY=yourindexerapikey zou reset-search-index
```
