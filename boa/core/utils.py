import collections
import sys
import os

from conda.base.context import context
from conda_build import utils
from conda_build.config import get_or_merge_config
from conda_build.variants import find_config_files, parse_config_file, combine_specs
from conda_build import __version__ as cb_version

from boa.core.config import boa_config

console = boa_config.console


cb_split_version = tuple(int(x) for x in cb_version.split("."))


if "bsd" in sys.platform:
    shell_path = "/bin/sh"
elif utils.on_win:
    shell_path = "bash"
else:
    shell_path = "/bin/bash"


def get_config(folder, variant=None, additional_files=None):
    if not additional_files:
        additional_files = []
    if not variant:
        variant = {}
    config = get_or_merge_config(None, variant)

    if cb_split_version >= (3, 20, 5):
        config_files = find_config_files(folder, config)
    else:
        config_files = find_config_files(folder)

    all_files = [os.path.abspath(p) for p in config_files + additional_files]

    # reverse files an uniquify
    def make_unique_list(lx):
        seen = set()
        return [x for x in lx if not (x in seen or seen.add(x))]

    # we reverse the order so that command line can overwrite the hierarchy
    all_files = make_unique_list(all_files[::-1])[::-1]

    console.print(f"\nLoading config files: [green]{', '.join(all_files)}\n")
    parsed_cfg = collections.OrderedDict()

    for f in all_files:
        parsed_cfg[f] = parse_config_file(f, config)

    # this merges each of the specs, providing a debug message when a given setting is overridden
    #      by a later spec
    combined_spec = combine_specs(parsed_cfg, log_output=config.verbose)
    # console.print(combined_spec)

    return combined_spec, config


def normalize_subdir(subdir):
    if subdir == "noarch":
        subdir = context.subdir
    else:
        return subdir


def get_sys_vars_stubs(target_platform):
    res = ["CONDA_BUILD_SYSROOT"]
    if sys.platform == "win32":
        res += [
            "SCRIPTS",
            "LIBRARY_PREFIX",
            "LIBRARY_BIN",
            "LIBRARY_INC",
            "LIBRARY_LIB",
            "CYGWIN_PREFIX",
            "ALLUSERSPROFILE",
            "APPDATA",
            "CommonProgramFiles",
            "CommonProgramFiles(x86)",
            "CommonProgramW6432",
            "COMPUTERNAME",
            "ComSpec",
            "HOMEDRIVE",
            "HOMEPATH",
            "LOCALAPPDATA",
            "LOGONSERVER",
            "NUMBER_OF_PROCESSORS",
            "PATHEXT",
            "ProgramData",
            "ProgramFiles",
            "ProgramFiles(x86)",
            "ProgramW6432",
            "PROMPT",
            "PSModulePath",
            "PUBLIC",
            "SystemDrive",
            "SystemRoot",
            "TEMP",
            "TMP",
            "USERDOMAIN",
            "USERNAME",
            "USERPROFILE",
            "windir",
            "PROCESSOR_ARCHITEW6432",
            "PROCESSOR_ARCHITECTURE",
            "PROCESSOR_IDENTIFIER",
            "BUILD",
        ]
    else:
        res += ["HOME", "PKG_CONFIG_PATH", "CMAKE_GENERATOR", "SSL_CERT_FILE"]

    if target_platform.startswith("osx"):
        res += [
            "OSX_ARCH",
            "MACOSX_DEPLOYMENT_TARGET",
            "BUILD",
            "macos_machine",
            "macos_min_version",
        ]
    elif target_platform.startswith("linux"):
        res += [
            "CFLAGS",
            "CXXFLAGS",
            "LDFLAGS",
            "QEMU_LD_PREFIX",
            "QEMU_UNAME",
            "DEJAGNU",
            "DISPLAY",
            "LD_RUN_PATH",
            "BUILD",
        ]
    return res
