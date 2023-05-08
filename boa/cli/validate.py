# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

from boa.core.validation import validate, ValidationError, SchemaError
from boa.core.render import render
from boa.core.utils import get_config

from rich.console import Console

console = Console()


def main(recipe):
    cbc, config = get_config(recipe)
    ydoc = render(recipe, config, is_pyproject_recipe=recipe.endswith(".toml"))
    console.print("\n\nNormalized Recipe:\n")
    console.print(ydoc)
    try:
        result = validate(ydoc)
        if result is None:
            console.print("\n[green]Validation OK[/green]")
    except ValidationError:
        exit(1)
    except SchemaError:
        exit(1)
