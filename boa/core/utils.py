import collections
import sys

from conda.base.context import context
from conda_build import utils
from conda_build.config import get_or_merge_config
from conda_build.variants import find_config_files, parse_config_file
from conda_build import __version__ as cb_version

from rich.console import Console

console = Console()

cb_split_version = tuple(int(x) for x in cb_version.split("."))


if "bsd" in sys.platform:
    shell_path = "/bin/sh"
elif utils.on_win:
    shell_path = "bash"
else:
    shell_path = "/bin/bash"


def get_config(folder, variant=None):
    if not variant:
        variant = {}
    config = get_or_merge_config(None, variant)

    if cb_split_version >= (3, 20, 5):
        config_files = find_config_files(folder, config)
    else:
        config_files = find_config_files(folder)
    console.print(f"\nLoading config files: [green]{', '.join(config_files)}\n")
    parsed_cfg = collections.OrderedDict()

    for f in config_files:
        parsed_cfg[f] = parse_config_file(f, config)

    # TODO just using latest config here, should merge!
    if len(config_files):
        cbc = parsed_cfg[config_files[-1]]
    else:
        cbc = {}

    return cbc, config


def normalize_subdir(subdir):
    if subdir == "noarch":
        subdir = context.subdir
    else:
        return subdir

