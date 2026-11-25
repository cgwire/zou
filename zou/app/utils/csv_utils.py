import csv
from io import StringIO

from flask import Response, make_response, stream_with_context
from slugify import slugify


def build_csv_response(csv_content, file_name="export"):
    """
    Make a Flask response that returns the content of a CSV file.
    """
    file_name = build_csv_file_name(file_name)
    response_body = build_csv_string(csv_content)
    csv_response = make_response(response_body)
    csv_response = build_csv_headers(csv_response, file_name)

    return csv_response


def build_csv_stream_response(row_generator, file_name="export"):
    """
    Make a streaming Flask response from a row generator. Write and
    flush each row immediately, so that the full CSV does not stay in a
    memory buffer.
    """
    file_name = build_csv_file_name(file_name)

    def generate():
        for row in row_generator:
            buf = StringIO()
            csv.writer(buf, delimiter=";").writerow(row)
            yield buf.getvalue()

    response = Response(
        stream_with_context(generate()),
        mimetype="text/csv",
    )
    response.headers["Content-Disposition"] = (
        f"attachment; filename={file_name}.csv"
    )
    return response


def build_csv_file_name(file_name):
    """
    Add the application name as a prefix of the file name.
    """
    return f"kitsu_{slugify(file_name, separator='_')}"


def build_csv_string(csv_content):
    """
    Build a CSV formatted string from an array.
    """
    string_wrapper = StringIO()
    csv_writer = csv.writer(string_wrapper, delimiter=";")
    csv_writer.writerows(csv_content)
    return string_wrapper.getvalue()


def build_csv_headers(csv_response, file_name):
    """
    Build the HTTP response headers that are necessary to return CSV
    content as a file.
    """
    csv_response.headers["Content-Disposition"] = (
        f"attachment; filename={file_name}.csv"
    )
    csv_response.headers["Content-type"] = "text/csv"
    return csv_response
