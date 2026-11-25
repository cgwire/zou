import functools
import os

import flasgger
import yaml


@functools.cache
def read_specs(path):
    """
    Return the YAML file at the given path as a dict. Each process reads
    the file one time only.
    """
    with open(path, encoding="utf-8") as spec_file:
        return yaml.safe_load(spec_file)


def load_specs(module_file, spec_file):
    """
    Return the OpenAPI specs of a module from the given YAML file, keyed by
    <Class>_<method>. The path of the file is relative to the module folder.
    """
    return read_specs(os.path.join(os.path.dirname(module_file), spec_file))


def swag_from(spec):
    """
    Document the decorated method with the given spec.
    """
    spec = dict(spec)
    summary = spec.pop("summary")

    def decorator(function):
        function = flasgger.swag_from(spec)(function)
        # With a dict, flasgger still reads the summary from the method
        # docstring. If the method has no docstring, flasgger reads the
        # docstring of the parent method.
        function.__doc__ = f"{summary}\n---\n"
        return function

    return decorator
