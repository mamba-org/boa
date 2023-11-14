# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import absolute_import, division, print_function, unicode_literals

import collections
import sys
import os
import typing
import json
import urllib.parse

from conda.base.context import context
from conda_build import utils
from conda_build.config import get_or_merge_config
from conda_build.variants import find_config_files, parse_config_file, combine_specs
from conda_build import __version__ as cb_version
from conda.base.constants import ChannelPriority
from conda.gateways.connection.session import CondaHttpAuth
from conda.core.index import check_allowlist
from conda.models.channel import Channel as CondaChannel
from conda.models.records import PackageRecord
from conda.common.url import join_url

from boa.core.config import boa_config
import libmambapy as api


if typing.TYPE_CHECKING:
    from typing import Any
    from conda_build.config import Config as CondaBuildConfig


console = boa_config.console

if "+" in cb_version:
    cb_version = cb_version[: cb_version.index("+")]
cb_split_version = tuple(int(x) for x in cb_version.split("."))


if "bsd" in sys.platform:
    shell_path = "/bin/sh"
elif utils.on_win:
    shell_path = "bash"
else:
    shell_path = "/bin/bash"


def get_config(
    folder,
    variant=None,
    additional_files=None,
    config: "CondaBuildConfig | None" = None,
) -> "tuple[Any, CondaBuildConfig]":
    if not additional_files:
        additional_files = []
    if not variant:
        variant = {}
    config = get_or_merge_config(config, variant)

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


def get_index(
    channel_urls=(),
    prepend=True,
    platform=None,
    use_local=False,
    use_cache=False,
    unknown=None,
    prefix=None,
    repodata_fn="repodata.json",
):
    if isinstance(platform, str):
        platform = [platform, "noarch"]

    all_channels = []
    if use_local:
        all_channels.append("local")
    all_channels.extend(channel_urls)
    if prepend:
        all_channels.extend(context.channels)
    check_allowlist(all_channels)

    # Remove duplicates but retain order
    all_channels = list(collections.OrderedDict.fromkeys(all_channels))

    dlist = api.DownloadTargetList()

    index = []

    def fixup_channel_spec(spec):
        at_count = spec.count("@")
        if at_count > 1:
            first_at = spec.find("@")
            spec = (
                spec[:first_at]
                + urllib.parse.quote(spec[first_at])
                + spec[first_at + 1 :]
            )
        if platform:
            spec = spec + "[" + ",".join(platform) + "]"
        return spec

    all_channels = list(map(fixup_channel_spec, all_channels))
    pkgs_dirs = api.MultiPackageCache(context.pkgs_dirs)
    api.create_cache_dir(str(pkgs_dirs.first_writable_path))

    for channel in api.get_channels(all_channels):
        for channel_platform, url in channel.platform_urls(with_credentials=True):
            full_url = CondaHttpAuth.add_binstar_token(url)

            sd = api.SubdirData(
                channel, channel_platform, full_url, pkgs_dirs, repodata_fn
            )

            index.append(
                (sd, {"platform": channel_platform, "url": url, "channel": channel})
            )
            dlist.add(sd)

    is_downloaded = dlist.download(api.MAMBA_DOWNLOAD_FAILFAST)

    if not is_downloaded:
        raise RuntimeError("Error downloading repodata.")

    return index


def load_channels(
    pool,
    channels,
    repos,
    has_priority=None,
    prepend=True,
    platform=None,
    use_local=False,
    use_cache=True,
    repodata_fn="repodata.json",
):
    index = get_index(
        channel_urls=channels,
        prepend=prepend,
        platform=platform,
        use_local=use_local,
        repodata_fn=repodata_fn,
        use_cache=use_cache,
    )

    if has_priority is None:
        has_priority = context.channel_priority in [
            ChannelPriority.STRICT,
            ChannelPriority.FLEXIBLE,
        ]

    subprio_index = len(index)
    if has_priority:
        # first, count unique channels
        n_channels = len(set([entry["channel"].canonical_name for _, entry in index]))
        current_channel = index[0][1]["channel"].canonical_name
        channel_prio = n_channels

    for subdir, entry in index:
        # add priority here
        if has_priority:
            if entry["channel"].canonical_name != current_channel:
                channel_prio -= 1
                current_channel = entry["channel"].canonical_name
            priority = channel_prio
        else:
            priority = 0
        if has_priority:
            subpriority = 0
        else:
            subpriority = subprio_index
            subprio_index -= 1

        if not subdir.loaded() and entry["platform"] != "noarch":
            # ignore non-loaded subdir if channel is != noarch
            continue

        if context.verbosity != 0 and not context.json:
            print(
                "Channel: {}, platform: {}, prio: {} : {}".format(
                    entry["channel"], entry["platform"], priority, subpriority
                )
            )
            print("Cache path: ", subdir.cache_path())

        repo = subdir.create_repo(pool)
        repo.set_priority(priority, subpriority)
        repos.append(repo)

    return index


def init_api_context(use_mamba_experimental=False):
    api_ctx = api.Context()

    api_ctx.json = context.json
    api_ctx.dry_run = context.dry_run
    if context.json:
        context.always_yes = True
        context.quiet = True
        if use_mamba_experimental:
            context.json = False

    api_ctx.verbosity = context.verbosity
    api_ctx.set_verbosity(context.verbosity)
    api_ctx.quiet = context.quiet
    api_ctx.offline = context.offline
    api_ctx.local_repodata_ttl = context.local_repodata_ttl
    api_ctx.use_index_cache = context.use_index_cache
    api_ctx.always_yes = context.always_yes
    api_ctx.channels = context.channels
    api_ctx.platform = context.subdir
    # Conda uses a frozendict here
    api_ctx.proxy_servers = dict(context.proxy_servers)

    if "MAMBA_EXTRACT_THREADS" in os.environ:
        try:
            max_threads = int(os.environ["MAMBA_EXTRACT_THREADS"])
            api_ctx.extract_threads = max_threads
        except ValueError:
            v = os.environ["MAMBA_EXTRACT_THREADS"]
            raise ValueError(
                f"Invalid conversion of env variable 'MAMBA_EXTRACT_THREADS' from value '{v}'"
            )

    def get_base_url(url, name=None):
        tmp = url.rsplit("/", 1)[0]
        if name:
            if tmp.endswith(name):
                return tmp.rsplit("/", 1)[0]
        return tmp

    api_ctx.channel_alias = str(
        get_base_url(context.channel_alias.url(with_credentials=True))
    )

    additional_custom_channels = {}
    for el in context.custom_channels:
        if context.custom_channels[el].canonical_name not in ["local", "defaults"]:
            additional_custom_channels[el] = get_base_url(
                context.custom_channels[el].url(with_credentials=True), el
            )
    api_ctx.custom_channels = additional_custom_channels

    additional_custom_multichannels = {}
    for el in context.custom_multichannels:
        if el not in ["defaults", "local"]:
            additional_custom_multichannels[el] = []
            for c in context.custom_multichannels[el]:
                additional_custom_multichannels[el].append(
                    get_base_url(c.url(with_credentials=True))
                )
    api_ctx.custom_multichannels = additional_custom_multichannels

    api_ctx.default_channels = [
        get_base_url(x.url(with_credentials=True)) for x in context.default_channels
    ]

    if context.ssl_verify is False:
        api_ctx.ssl_verify = "<false>"
    elif context.ssl_verify is not True:
        api_ctx.ssl_verify = context.ssl_verify
    api_ctx.target_prefix = context.target_prefix
    api_ctx.root_prefix = context.root_prefix
    api_ctx.conda_prefix = context.conda_prefix
    api_ctx.pkgs_dirs = context.pkgs_dirs
    api_ctx.envs_dirs = context.envs_dirs

    api_ctx.connect_timeout_secs = int(round(context.remote_connect_timeout_secs))
    api_ctx.max_retries = context.remote_max_retries
    api_ctx.retry_backoff = context.remote_backoff_factor
    api_ctx.add_pip_as_python_dependency = context.add_pip_as_python_dependency
    api_ctx.use_only_tar_bz2 = context.use_only_tar_bz2

    if context.channel_priority is ChannelPriority.STRICT:
        api_ctx.channel_priority = api.ChannelPriority.kStrict
    elif context.channel_priority is ChannelPriority.FLEXIBLE:
        api_ctx.channel_priority = api.ChannelPriority.kFlexible
    elif context.channel_priority is ChannelPriority.DISABLED:
        api_ctx.channel_priority = api.ChannelPriority.kDisabled


def to_conda_channel(channel, platform):
    if channel.scheme == "file":
        return CondaChannel.from_value(
            channel.platform_url(platform, with_credentials=False)
        )

    return CondaChannel(
        channel.scheme,
        channel.auth,
        channel.location,
        channel.token,
        channel.name,
        platform,
        channel.package_filename,
    )


def to_package_record_from_subjson(entry, pkg, jsn_string):
    channel_url = entry["url"]
    info = json.loads(jsn_string)
    info["fn"] = pkg
    info["channel"] = to_conda_channel(entry["channel"], entry["platform"])
    info["url"] = join_url(channel_url, pkg)
    if not info.get("subdir"):
        info["subdir"] = entry["platform"]
    package_record = PackageRecord(**info)
    return package_record
