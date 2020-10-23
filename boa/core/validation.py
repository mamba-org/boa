from jsonschema import validate as json_validate
import json5 as json
import os

from rich.console import Console

console = Console()


def schema_dir():
    return os.path.join(os.path.dirname(__file__), "../../schemas")


def validate(obj):
    with open(os.path.join(schema_dir(), "recipe.v1.json")) as schema_in:
        schema = json.load(schema_in)
    validation_result = json_validate(instance=obj, schema=schema)
    return validation_result
