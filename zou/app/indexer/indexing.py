import meilisearch
from meilisearch.errors import MeilisearchApiError

from zou.app import config
from zou.app.utils import cache

client = None


def init():
    """
    Configure Meilisearch client.
    """
    global client
    if client is None:
        protocol = config.INDEXER["protocol"]
        host = config.INDEXER["host"]
        port = config.INDEXER["port"]
        client = meilisearch.Client(
            f"{protocol}://{host}:{port}",
            config.INDEXER["key"],
            timeout=config.INDEXER["timeout"],
        )


def create_index(index_name, searchable_fields=[], filterable_fields=[]):
    """
    Create a new index and configure it properly by setting searchable_fields
    and allowing to filter on project ids.
    """
    index = None
    try:
        index = get_index(index_name)
    except MeilisearchApiError:
        pass
    if index is None:
        task = client.create_index(index_name, {"primaryKey": "id"})
        client.wait_for_task(
            task.task_uid, timeout_in_ms=config.INDEXER["timeout"]
        )
        index = get_index(index_name)
    index.update_searchable_attributes(searchable_fields)
    index.update_settings(
        {
            "filterableAttributes": filterable_fields,
            "sortableAttributes": [
                "name",
            ],
        }
    )

    return index


@cache.memoize_function(120)
def get_index(index_name):
    """
    Get index matching given name.
    """
    init()
    index = client.get_index(index_name)
    return index


def clear_index(index_name):
    """
    Clear all data into the index matching given name.
    """
    cache.cache.delete_memoized(get_index)
    index = get_index(index_name)
    task = index.delete_all_documents()
    client.wait_for_task(
        task.task_uid, timeout_in_ms=config.INDEXER["timeout"]
    )
    return index


def index_document(index, document):
    """
    Add given document to given index.
    """
    task = index.add_documents([document])
    client.wait_for_task(
        task.task_uid, timeout_in_ms=config.INDEXER["timeout"]
    )
    return index


def index_documents(index, documents):
    """
    Add given documents to given index.
    """
    task = index.add_documents(documents)
    client.wait_for_task(
        task.task_uid, timeout_in_ms=config.INDEXER["timeout"]
    )
    return documents


def search(ix, query, project_ids=[], limit=10, offset=0):
    """
    Perform a search on given index and filter result based on project IDs.
    The number of results can be specified.
    """
    project_ids = ",".join(project_ids)
    search_options = {
        "limit": limit,
        "offset": offset,
        "sort": ["name:asc"],
        "showMatchesPosition": True,
    }
    if len(project_ids) > 0:
        search_options["filter"] = f"project_id IN [{project_ids}]"
    search_results = ix.search(query, search_options)

    results = []
    for result in search_results["hits"]:
        document_id = result["id"]
        matched_fields = []
        for field in result["_matchesPosition"].keys():
            if "metadatas" in field:
                matched_fields.append(field[10:])
            else:
                matched_fields.append(field)
        results.append((document_id, matched_fields))

    return results


def remove_document(index, entry_id):
    """
    Remove document matching given id from given index.
    """
    index.delete_document(entry_id)
    return entry_id
