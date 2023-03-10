# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

import sys
import argparse

from boa.core import monkey_patch_emscripten

if any("emscripten" in arg for arg in sys.argv):
    print("Monkeypatching emscripten")
    monkey_patch_emscripten.patch()

from boa.core.config import init_global_config
from boa._version import __version__
from mamba.utils import init_api_context

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

    test_parser = argparse.ArgumentParser(add_help=False)
    test_parser.add_argument(
        "--extra-deps",
        action="append",
        help="Extra dependencies to add to all test environment creation steps.",
    )
    subparsers.add_parser(
        "test",
        parents=[parent_parser, test_parser],
        help="test an already built package (include_recipe of the package must be true)",
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
    # The following arguments are taken directly from conda-build
    conda_build_parser = build_parser.add_argument_group("special conda-build flags")
    conda_build_parser.add_argument(
        "--build-id-pat",
        default=False,
        dest="conda_build_build_id_pat",
        help="""\
            specify a templated pattern to use as build folder names.  Use if having issues with
            paths being too long, or to ensure a particular build folder name.
            When not specified, the default is to use the pattern {n}_{t}.
            Template variables are: n: package name, t: timestamp, v: package_version""",
    )
    conda_build_parser.add_argument(
        "--no-remove-work-dir",
        dest="conda_build_remove_work_dir",
        default=True,
        action="store_false",
        help="""\
            Disable removal of the work dir before testing.  Be careful using this option, as
            you package may depend on files that are not included in the package, and may pass
            tests, but ultimately fail on installed systems.""",
    )
    conda_build_parser.add_argument(
        "--keep-old-work",
        action="store_true",
        dest="conda_build_keep_old_work",
        help="Do not remove anything from environment, even after successful build and test.",
    )
    conda_build_parser.add_argument(
        "--prefix-length",
        dest="conda_build_prefix_length",
        help="""\
            length of build prefix.  For packages with binaries that embed the path, this is
            critical to ensuring that your package can run as many places as possible.  Note
            that this value can be altered by the OS below boa (e.g. encrypted
            filesystems on Linux), and you should prefer to set --croot to a non-encrypted
            location instead, so that you maintain a known prefix length.""",
        default=255,
        type=int,
    )
    conda_build_parser.add_argument(
        "--croot",
        dest="conda_build_croot",
        help="Build root folder.  Equivalent to CONDA_BLD_PATH, but applies only to this call of `boa build`.",
    )
    build_parser.add_argument(
        "--pkg-format",
        dest="conda_pkg_format",
        choices=["1", "2"],
        default="1",
        help="Package format version.  Version 1 is the standard .tar.bz2 format.  Version 2 is the new .conda format.",
    )
    conda_build_parser.add_argument(
        "--zstd-compression-level",
        help="""\
            When building v2 packages, set the compression level used by
            conda-package-handling. Defaults to the maximum.""",
        type=int,
        choices=range(1, 22),
        default=22,
    )

    for k in ("perl", "lua", "python", "numpy", "r_base"):
        conda_build_parser.add_argument(
            "--{}".format(k),
            dest="{}_variant".format(k),
            help="Set the {} variant used by conda build.".format(k),
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
    init_global_config(args)

    from boa.core.run_build import run_build
    from boa.cli import convert
    from boa.cli import transmute
    from boa.cli import validate
    from boa.cli import test

    if command == "convert":
        convert.main(args.target)
        exit()

    if command == "validate":
        validate.main(args.target)
        exit()

    if command == "test":
        test.main(args)
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
