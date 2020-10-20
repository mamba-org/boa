import argparse
from boa.core.run_build import run_build

from boa.cli import convert
from boa.cli import transmute

from rich.console import Console

console = Console()

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

    subparsers = parser.add_subparsers(help="sub-command help", dest="command")
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("recipe_dir", type=str)
    parent_parser.add_argument("--features", type=str)

    subparsers.add_parser("render", parents=[parent_parser], help="render a recipe")
    subparsers.add_parser(
        "convert",
        parents=[parent_parser],
        help="convert recipe.yaml to old-style meta.yaml",
    )
    subparsers.add_parser("build", parents=[parent_parser], help="build a recipe")

    transmute_parser = subparsers.add_parser(
        "transmute",
        parents=(),
        help="transmute one or many tar.bz2 packages into a conda packages (or vice versa!)",
    )
    transmute_parser.add_argument("files", type=str, nargs="+")
    transmute_parser.add_argument("-o", "--output-directory", type=str, default=".")
    transmute_parser.add_argument("-c", "--compression-level", type=int, default=22)

    args = parser.parse_args()

    command = args.command

    if command == "convert":
        convert.main(args.recipe_dir)
        exit()

    if command == "transmute":
        transmute.main(args)
        exit()

    console.print(banner)

    if command == "build" or command == "render":
        run_build(args)


if __name__ == "__main__":
    main()
