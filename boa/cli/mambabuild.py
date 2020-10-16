import sys
import os
import re

from conda.models.match_spec import MatchSpec
import conda_build.api
from conda_build.conda_interface import pkgs_dirs
import conda_build.environ
from conda.core.prefix_data import PrefixData
from conda._vendor.boltons.setutils import IndexedSet

from mamba import mamba_api
from mamba.utils import get_index, to_package_record_from_subjson
from conda.core.solve import diff_for_unlink_link_precs
from conda.models.prefix_graph import PrefixGraph
from conda.plan import get_blank_actions
from conda.models.dist import Dist

import conda_build
from conda_build import api

from conda_build.config import Config, get_channel_urls
from conda_build.cli.main_build import parse_args

from conda_build.conda_interface import get_rc_urls
from conda.base.context import context

only_dot_or_digit_re = re.compile(r"^[\d\.]+$")


def to_action(specs_to_add, specs_to_remove, prefix, to_link, to_unlink, index):
    to_link_records = []

    prefix_data = PrefixData(prefix)
    final_precs = IndexedSet(prefix_data.iter_records())

    lookup_dict = {}
    for _, c in index:
        lookup_dict[str(c)] = c

    assert len(to_unlink) == 0

    for c, pkg, jsn_s in to_link:
        sdir = lookup_dict[c]
        rec = to_package_record_from_subjson(sdir, pkg, jsn_s)
        final_precs.add(rec)
        to_link_records.append(rec)

    unlink_precs, link_precs = diff_for_unlink_link_precs(
        prefix,
        final_precs=IndexedSet(PrefixGraph(final_precs).graph),
        specs_to_add=specs_to_add,
    )

    actions = get_blank_actions(prefix)
    actions["UNLINK"].extend(Dist(prec) for prec in unlink_precs)
    actions["LINK"].extend(Dist(prec) for prec in link_precs)
    return actions


class MambaSolver:
    def __init__(self, channels, platform):

        api_ctx = mamba_api.Context()
        api_ctx.conda_prefix = context.conda_prefix

        self.channels = channels
        self.platform = platform
        self.index = get_index(channels, platform=platform)
        self.local_index = []
        self.pool = mamba_api.Pool()
        self.repos = []

        start_prio = len(channels)
        subpriority = 0  # wrong! :)
        for subdir, channel in self.index:
            repo = mamba_api.Repo(
                self.pool,
                str(channel),
                subdir.cache_path(),
                channel.url(with_credentials=True),
            )
            repo.set_priority(start_prio, subpriority)
            start_prio -= 1
            self.repos.append(repo)

        self.local_repos = {}

    def replace_channels(self):
        self.local_index = get_index(("local",), platform=self.platform, prepend=False)

        for _, v in self.local_repos.items():
            v.clear(True)

        start_prio = len(self.channels) + len(self.index)
        for subdir, channel in self.local_index:
            if not subdir.loaded():
                continue

            cp = subdir.cache_path()
            if cp.endswith(".solv"):
                os.remove(subdir.cache_path())
                cp = cp.replace(".solv", ".json")

            self.local_repos[str(channel)] = mamba_api.Repo(
                self.pool, str(channel), cp, channel.url(with_credentials=True)
            )
            self.local_repos[str(channel)].set_priority(start_prio, 0)
            start_prio -= 1

    def solve(self, specs, prefix):
        """Solve given a set of specs.
        Parameters
        ----------
        specs : list of str
            A list of package specs. You can use `conda.models.match_spec.MatchSpec`
            to get them to the right form by calling
            `MatchSpec(mypec).conda_build_form()`
        Returns
        -------
        solvable : bool
            True if the set of specs has a solution, False otherwise.
        """
        solver_options = [(mamba_api.SOLVER_FLAG_ALLOW_DOWNGRADE, 1)]
        api_solver = mamba_api.Solver(self.pool, solver_options)
        _specs = specs

        api_solver.add_jobs(_specs, mamba_api.SOLVER_INSTALL)
        success = api_solver.solve()

        if not success:
            error_string = "Mamba failed to solve:\n"
            for s in _specs:
                error_string += f" - {s}\n"
            error_string += "\nwith channels:\n"
            for c in self.channels:
                error_string += f" - {c}\n"
            pstring = api_solver.problems_to_str()
            pstring = "\n".join(["   " + el for el in pstring.split("\n")])
            error_string += f"\nThe reported errors are:\n⇟{pstring}"
            print(error_string)
            exit(1)

        package_cache = mamba_api.MultiPackageCache(pkgs_dirs)

        t = mamba_api.Transaction(api_solver, package_cache)
        return t

    def solve_for_action(self, specs, prefix):
        t = self.solve(specs, prefix)
        t.print()

        mmb_specs, to_link, to_unlink = t.to_conda()
        specs_to_add = [MatchSpec(m) for m in mmb_specs[0]]
        specs_to_remove = [MatchSpec(m) for m in mmb_specs[1]]

        return to_action(
            specs_to_add,
            specs_to_remove,
            prefix,
            to_link,
            to_unlink,
            self.index + self.local_index,
        )


solver = None


def mamba_get_install_actions(
    prefix,
    specs,
    env,
    retries=0,
    subdir=None,
    verbose=True,
    debug=False,
    locking=True,
    bldpkgs_dirs=None,
    timeout=900,
    disable_pip=False,
    max_env_retry=3,
    output_folder=None,
    channel_urls=None,
):
    print("Specs to install: ", specs)
    print("Channel urls: ", channel_urls)
    _specs = [MatchSpec(s) for s in specs]
    for idx, s in enumerate(_specs):
        if s.version:
            vspec = str(s.version)
            if re.match(only_dot_or_digit_re, vspec) and vspec.count(".") <= 1:
                n = s.conda_build_form()
                sn = n.split()
                sn[1] = vspec + ".*"
                _specs[idx] = MatchSpec(" ".join(sn))

    _specs = [s.conda_build_form() for s in _specs]

    solver.replace_channels()
    solution = solver.solve_for_action(_specs, prefix)
    return solution


conda_build.environ.get_install_actions = mamba_get_install_actions


def main():
    _, args = parse_args(sys.argv[1:])
    args = args.__dict__

    config = Config(**args)
    channel_urls = get_rc_urls() + get_channel_urls({})

    # setting the repodata timeout to very high for conda
    context.local_repodata_ttl = 100000

    recipe = args["recipe"][0]

    global solver
    solver = MambaSolver(channel_urls, context.subdir)
    solver.replace_channels()
    cbc, _ = conda_build.variants.get_package_combined_spec(recipe, config=config)

    api.build(recipe)
