# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

import sys
import argparse
from boa.core.monkeypatch import *
from boa.core.config import init_global_config
from boa._version import __version__
from mamba.utils import init_api_context
import libmambapy as api

from conda_build.conda_interface import cc_conda_build

banner = r"""
           _
          | |__   ___   __ _
          | '_ \ / _ \ / _` |
          | |_) | (_) | (_| |
          |_.__/ \___/ \__,_|
"""


def main(config=None):

    parser = argparse.ArgumentParser(
        description="Boa, the fast, mamba powered-build tool for conda packages."
    )
    parser.add_argument("--version", action="version", version=__version__)

    subparsers = parser.add_subparsers(help="sub-command help", dest="command")
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--recipe-dir", type=str)
    parent_parser.add_argument("target", type=str, default="")
    parent_parser.add_argument("--features", type=str)
    parent_parser.add_argument("--offline", action="store_true")
    parent_parser.add_argument("--target-platform", type=str)
    parent_parser.add_argument("--json", action="store_true")
    parent_parser.add_argument("--debug", action="store_true")

    variant_parser = argparse.ArgumentParser(add_help=False)
    variant_parser.add_argument(
        "-m",
        "--variant-config-files",
        action="append",
        help="""Additional variant config files to add.  These yaml files can contain
        keys such as `c_compiler` and `target_platform` to form a build matrix.""",
    )

    subparsers.add_parser(
        "render", parents=[parent_parser, variant_parser], help="render a recipe"
    )
    subparsers.add_parser(
        "convert",
        parents=[parent_parser],
        help="convert old-style meta.yaml to recipe.yaml",
    )
    subparsers.add_parser(
        "validate",
        parents=[parent_parser],
        help="Validate recipe.yaml",
    )

    build_parser = argparse.ArgumentParser(add_help=False)
    build_parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Use interactive mode if build fails",
    )

    build_parser.add_argument(
        "--output-folder",
        help=(
            "folder to dump output package to.  Package are moved here if build or test succeeds."
            "  Destination folder must exist prior to using this."
        ),
        default=cc_conda_build.get("output_folder"),
    )

    build_parser.add_argument(
        "--skip-existing",
        nargs="?",
        default="default",
        const="yes",
    )
    build_parser.add_argument(
        "--no-test",
        action="store_true",
        dest="notest",
        help="Do not test the package.",
    )
    build_parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue building remaining recipes if a recipe fails.",
    )

    subparsers.add_parser(
        "build",
        parents=[parent_parser, build_parser, variant_parser],
        help="build a recipe",
    )

    transmute_parser = subparsers.add_parser(
        "transmute",
        parents=(),
        help="transmute one or many tar.bz2 packages into a conda packages (or vice versa!)",
    )
    transmute_parser.add_argument("files", type=str, nargs="+")
    transmute_parser.add_argument("-o", "--output-folder", type=str, default=".")
    transmute_parser.add_argument("-c", "--compression-level", type=int, default=22)
    transmute_parser.add_argument(
        "-n_jobs",
        "--num_jobs",
        type=int,
        default=1,
        help="the number of parallel processing elements",
    )

    args = parser.parse_args()

    command = args.command

    init_api_context()
    api_ctx = api.Context()
    api_ctx.add_pip_as_python_dependency = False
    init_global_config(args)

    from boa.core.run_build import run_build
    from boa.cli import convert
    from boa.cli import transmute
    from boa.cli import validate

    if command == "convert":
        convert.main(args.target)
        exit()

    if command == "validate":
        validate.main(args.target)
        exit()

    if command == "transmute":
        transmute.main(args)
        exit()

    from boa.core.config import boa_config

    boa_config.console.print(banner)

    if command == "build" or command == "render":
        run_build(args)

    if not command:
        parser.print_help(sys.stdout)


if __name__ == "__main__":
    main()
