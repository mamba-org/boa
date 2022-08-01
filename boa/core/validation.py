# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause
from .monkeypatch import *
from jsonschema import validate as json_validate
import json5 as json
from jsonschema.exceptions import ValidationError, SchemaError
from pathlib import Path
from rich.console import Console

console = Console()


def schema_dir():
    return Path(__file__).parent / ".." / "schemas"


def validate(obj):
    with open(schema_dir() / "recipe.v1.json") as schema_in:
        schema = json.load(schema_in)
    try:
        validation_result = json_validate(instance=obj, schema=schema)
    except ValidationError as e:
        console.print("\n[red]Recipe validation error\n")
        console.print(e)
        raise e
    except SchemaError as e:
        console.print("\n[red]Recipe schema validation error\n")
        console.print(e)
        raise e
    return validation_result
