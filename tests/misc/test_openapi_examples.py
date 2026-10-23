import uuid

from tests.base import ApiDBTestCase


def walk(node, path=()):
    """
    Yield (path, schema) for every dict in the document.
    """
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from walk(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, path + (index,))


class OpenApiExamplesTestCase(ApiDBTestCase):
    def test_uuid_examples_are_uuids(self):
        """
        A client generated from the spec validates format: uuid; an
        example that is not one breaks it. The examples used to be
        thirty-five characters long, or carry letters beyond f.
        """
        spec = self.app.get("/openapi-raw.json").json
        bad = []
        for path, schema in walk(spec):
            if schema.get("format") != "uuid":
                continue
            examples = []
            if "example" in schema:
                examples.append(schema["example"])
            if isinstance(schema.get("examples"), list):
                examples.extend(schema["examples"])
            for example in examples:
                values = example if isinstance(example, list) else [example]
                for value in values:
                    if value is None:
                        # A nullable id whose example is the null case.
                        continue
                    try:
                        uuid.UUID(str(value))
                    except ValueError:
                        bad.append((path, value))
        # Array items declared as uuids with the example on the array.
        for path, schema in walk(spec):
            items = schema.get("items")
            if (
                isinstance(items, dict)
                and items.get("format") == "uuid"
                and isinstance(schema.get("example"), list)
            ):
                for value in schema["example"]:
                    try:
                        uuid.UUID(str(value))
                    except ValueError:
                        bad.append((path, value))
        self.assertEqual(bad, [])
