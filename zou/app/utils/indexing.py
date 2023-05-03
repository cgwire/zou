from whoosh import index
from whoosh.query import Or, Term
from whoosh.qparser import MultifieldParser


def create_index(path, schema):
    return index.create_in(path, schema)


def get_index(path):
    return index.open_dir(path)


def index_data(ix, data):
    writer = ix.writer(limitmb=1024)
    writer.add_document(**data)
    writer.commit()
    return writer


def search(ix, query, project_ids=[], limit=10):
    fields = ["name"]
    for field in ix.reader().indexed_field_names():
        if field.startswith("data_"):
            fields.append(field)
    query_parser = MultifieldParser(fields, schema=ix.schema)
    whoosh_query = query_parser.parse(query)
    is_project_filter = len(project_ids) > 0
    ids = []
    with ix.searcher() as searcher:
        if is_project_filter:
            project_id_terms = Or(
                [Term("project_id", project_id) for project_id in project_ids]
            )
            results = searcher.search(
                whoosh_query, filter=project_id_terms, limit=limit
            )
        else:
            results = searcher.search(whoosh_query, limit=limit)
        for result in results:
            ids.append(result["id"])
    return ids
