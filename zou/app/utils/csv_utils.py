import csv

from io import StringIO
from flask import Response, make_response, stream_with_context
from slugify import slugify


def build_csv_response(csv_content, file_name="export"):
    """
    Construct a Flask response that returns content of a csv a file.
    """
    file_name = build_csv_file_name(file_name)
    response_body = build_csv_string(csv_content)
    csv_response = make_response(response_body)
    csv_response = build_csv_headers(csv_response, file_name)

    return csv_response


def build_csv_stream_response(row_generator, file_name="export"):
    """
    Construct a streaming Flask response from a row generator.
    Each row is written and flushed immediately to avoid buffering
    the entire CSV in memory.
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
        "attachment; filename=%s.csv" % file_name
    )
    return response


def build_csv_file_name(file_name):
    """
    Add application name as prefix of the file name.
    """
    return "kitsu_%s" % slugify(file_name, separator="_")


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
    Build HTTP response headers needed to return CSV content as a file.
    """
    csv_response.headers["Content-Disposition"] = (
        "attachment; filename=%s.csv" % file_name
    )
    csv_response.headers["Content-type"] = "text/csv"
    return csv_response
