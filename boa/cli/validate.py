# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

from boa.core.validation import validate
from boa.core.render import render
from boa.core.utils import get_config

from rich.console import Console

console = Console()


def main(recipe):
    cbc, config = get_config(recipe)
    ydoc = render(recipe, config)
    result = validate(ydoc)

    if result is None:
        console.print("[green]Validation OK[/green]")
