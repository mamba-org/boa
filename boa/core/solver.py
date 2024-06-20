# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

import os
import tempfile

from boltons.setutils import IndexedSet

from conda.base.constants import ChannelPriority
from conda.core.solve import diff_for_unlink_link_precs
from conda.common.serialize import json_dump
from conda.models.prefix_graph import PrefixGraph
from conda.core.prefix_data import PrefixData
from conda.models.match_spec import MatchSpec
from conda.common.url import remove_auth, split_anaconda_token
from conda.core.index import _supplement_index_with_system
from conda.base.context import context
from conda.core.package_cache_data import PackageCacheData

import libmambapy

from boa.core.utils import (
    get_index,
    load_channels,
    pkgs_dirs,
    to_package_record_from_subjson,
)
from boa.core.config import boa_config

console = boa_config.console

solver_cache = {}


def refresh_solvers():
    for _, v in solver_cache.items():
        v.replace_channels()


def get_solver(subdir, output_folder="local"):
    pkg_cache = PackageCacheData.first_writable().pkgs_dir
    if subdir == "noarch":
        subdir = context.subdir
    elif subdir != context.subdir:
        pkg_cache = os.path.join(pkg_cache, subdir)
        if not os.path.exists(pkg_cache):
            os.makedirs(pkg_cache, exist_ok=True)

    if not solver_cache.get(subdir):
        solver_cache[subdir] = MambaSolver([], subdir, output_folder)

    return solver_cache[subdir], pkg_cache


def get_url_from_channel(c):
    if c.startswith("file://"):
        # The conda functions (specifically remove_auth) assume the input
        # is a url; a file uri on windows with a drive letter messes them
        # up.
        return c
    else:
        return split_anaconda_token(remove_auth(c))[0]


def to_unlink_link_precs(
    specs_to_add, specs_to_remove, prefix, to_link, to_unlink, index
):
    to_link_records = []

    prefix_data = PrefixData(prefix)
    final_precs = IndexedSet(prefix_data.iter_records())

    lookup_dict = {}
    for _, entry in index:
        lookup_dict[
            entry["channel"].platform_url(entry["platform"], with_credentials=False)
        ] = entry

    assert len(to_unlink) == 0

    for c, pkg, jsn_s in to_link:
        entry = lookup_dict[get_url_from_channel(c)]
        rec = to_package_record_from_subjson(entry, pkg, jsn_s)
        final_precs.add(rec)
        to_link_records.append(rec)

    unlink_precs, link_precs = diff_for_unlink_link_precs(
        prefix,
        final_precs=IndexedSet(PrefixGraph(final_precs).graph),
        specs_to_add=specs_to_add,
    )

    return unlink_precs, link_precs


def get_virtual_packages():
    result = {"packages": {}}

    # add virtual packages as installed packages
    # they are packages installed on the system that conda can do nothing
    # about (e.g. glibc)
    # if another version is needed, installation just fails
    # they don't exist anywhere (they start with __)
    installed = dict()
    _supplement_index_with_system(installed)
    installed = list(installed)

    for prec in installed:
        json_rec = prec.dist_fields_dump()
        json_rec["depends"] = prec.depends
        json_rec["build"] = prec.build
        result["packages"][prec.fn] = json_rec

    installed_json_f = tempfile.NamedTemporaryFile("w", delete=False)
    installed_json_f.write(json_dump(result))
    installed_json_f.flush()
    return installed_json_f


class MambaSolver:
    def __init__(self, channels, platform, output_folder=None):
        self.channels = channels
        self.platform = platform
        self.output_folder = output_folder or "local"
        self.pool = libmambapy.Pool()
        self.repos = []

        self.index = load_channels(
            self.pool, self.channels, self.repos, platform=platform
        )

        # if platform == context.subdir:
        installed_json_f = get_virtual_packages()
        repo = libmambapy.Repo(self.pool, "installed", installed_json_f.name, "")
        repo.set_installed()
        self.repos.append(repo)

        self.local_index = []
        self.local_repos = {}
        # load local repo, too
        self.replace_channels()

    def replace_installed(self, prefix):
        prefix_data = libmambapy.PrefixData(prefix)
        vp = libmambapy.get_virtual_packages()
        prefix_data.add_virtual_packages(vp)
        prefix_data.load()
        repo = libmambapy.Repo(self.pool, prefix_data)
        repo.set_installed()

    def replace_channels(self):
        console.print(f"[blue]Reloading output folder: {self.output_folder}")
        self.local_index = get_index(
            (self.output_folder,), platform=self.platform, prepend=False
        )

        for _, v in self.local_repos.items():
            v.clear(True)

        start_prio = len(self.channels) + len(self.index)
        for subdir, channel in self.local_index:
            if not subdir.loaded():
                continue

            # support new mamba
            if isinstance(channel, dict):
                channelstr = channel["url"]
                channelurl = channel["url"]
            else:
                channelstr = str(channel)
                channelurl = channel.url(with_credentials=True)

            cp = subdir.cache_path()
            if cp.endswith(".solv"):
                os.remove(subdir.cache_path())
                cp = cp.replace(".solv", ".json")

            self.local_repos[channelstr] = libmambapy.Repo(
                self.pool, channelstr, cp, channelurl
            )

            self.local_repos[channelstr].set_priority(start_prio, 0)
            start_prio -= 1

    def solve(self, specs, pkg_cache_path=None):
        """Solve given a set of specs.
        Parameters
        ----------
        specs : list of str
            A list of package specs. You can use `conda.models.match_spec.MatchSpec`
            to get them to the right form by calling
            `MatchSpec(mypec).conda_build_form()`
        Returns
        -------
        transaction : libmambapy.Transaction
            The mamba transaction.
        Raises
        ------
        RuntimeError :
            If the solver did not find a solution.
        """
        solver_options = [(libmambapy.SOLVER_FLAG_ALLOW_DOWNGRADE, 1)]

        if context.channel_priority is ChannelPriority.STRICT:
            solver_options.append((libmambapy.SOLVER_FLAG_STRICT_REPO_PRIORITY, 1))

        api_solver = libmambapy.Solver(self.pool, solver_options)
        _specs = specs

        api_solver.add_jobs(_specs, libmambapy.SOLVER_INSTALL)
        success = api_solver.solve()

        if not success:
            error_string = "Mamba failed to solve:\n"
            for s in _specs:
                error_string += f" - {s}\n"
            error_string += "\nwith channels:\n"
            for c in self.channels:
                error_string += f" - {c}\n"
            pstring = api_solver.problems_to_str()

            pstring = "\n".join(["- " + el for el in pstring.split("\n")])
            error_string += f"\nThe reported errors are:\n{pstring}"

            if (
                hasattr(api_solver, "explain_problems")
                # can cause errors in explain_problems
                and "unsupported request" not in pstring
            ):
                error_string += f"\n\n{api_solver.explain_problems()}"

            print(error_string)
            raise RuntimeError("Solver could not find solution." + error_string)

        if pkg_cache_path is None:
            # use values from conda
            pkg_cache_path = pkgs_dirs

        package_cache = libmambapy.MultiPackageCache(pkg_cache_path)
        return libmambapy.Transaction(api_solver, package_cache)

    def solve_for_unlink_link_precs(self, specs, prefix):
        t = self.solve(specs)
        if not boa_config.quiet and not boa_config.is_mambabuild:
            t.print()

        mmb_specs, to_link, to_unlink = t.to_conda()
        specs_to_add = [MatchSpec(m) for m in mmb_specs[0]]
        specs_to_remove = [MatchSpec(m) for m in mmb_specs[1]]

        return to_unlink_link_precs(
            specs_to_add,
            specs_to_remove,
            prefix,
            to_link,
            to_unlink,
            self.index + self.local_index,
        )
