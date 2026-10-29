import functools
import os

import flasgger
import yaml


@functools.cache
def read_specs(path):
    with open(path, encoding="utf-8") as spec_file:
        return yaml.safe_load(spec_file)


def load_specs(module_file, spec_file):
    """
    Return the OpenAPI specs of a module, keyed by <Class>_<method>, from
    given YAML file, relative to the module folder.
    """
    return read_specs(os.path.join(os.path.dirname(module_file), spec_file))


def swag_from(spec):
    """
    Document the decorated method with given spec.
    """
    spec = dict(spec)
    summary = spec.pop("summary")

    def decorator(function):
        function = flasgger.swag_from(spec)(function)
        # Given a dict, flasgger still reads the summary from the method
        # docstring, or from the parent method one when it has none.
        function.__doc__ = f"{summary}\n---\n"
        return function

    return decorator
