# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause
from boa.core.run_build import initialize_conda_build_config
from boa.core.test import run_test

from rich.console import Console

console = Console()


def main(args):
    stats = {}
    config = initialize_conda_build_config(args)

    run_test(
        args.target,
        config,
        stats,
        move_broken=False,
        provision_only=False,
        extra_deps=getattr(args, "extra_deps", []),
    )
