# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

from rich.console import Console

boa_config = None


class BoaConfig:
    console = Console()
    json: bool = False
    debug: bool = False
    quiet: bool = False

    def __init__(self, args=None):
        if args and getattr(args, "json", False):
            self.console.quiet = True
            self.json = True

        if args and getattr(args, "quiet", False):
            self.console.quiet = True
            self.quiet = True

        if args and getattr(args, "debug", False):
            self.debug = args.debug


def init_global_config(args=None):
    global boa_config
    boa_config = BoaConfig(args)


if not boa_config:
    init_global_config()
