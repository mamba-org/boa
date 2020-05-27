import sys, os


from conda.models.match_spec import MatchSpec
from conda.models.channel import Channel
from conda.core.index import calculate_channel_urls, check_whitelist
from conda.core.subdir_data import cache_fn_url, create_cache_dir
import conda_build.api
from conda_build.conda_interface import pkgs_dirs
import conda_build.environ
from conda.core.prefix_data import PrefixData
from conda._vendor.boltons.setutils import IndexedSet

from mamba import mamba_api
from mamba.utils import to_package_record_from_subjson
from conda.core.solve import diff_for_unlink_link_precs
from conda.models.prefix_graph import PrefixGraph
from conda.plan import get_blank_actions
from conda.models.dist import Dist


def to_action(specs_to_add, specs_to_remove, prefix, to_link, to_unlink, index):
    to_link_records, to_unlink_records = [], []

    prefix_data = PrefixData(prefix)
    final_precs = IndexedSet(prefix_data.iter_records())

    lookup_dict = {}
    for _, c in index:
        lookup_dict[str(c)] = c

    for c, pkg in to_unlink:
        for i_rec in installed_pkg_recs:
            if i_rec.fn == pkg:
                final_precs.remove(i_rec)
                to_unlink_records.append(i_rec)
                break
        else:
            print("No package record found!")

    for c, pkg, jsn_s in to_link:
        sdir = lookup_dict[c]
        rec = to_package_record_from_subjson(sdir, pkg, jsn_s)
        final_precs.add(rec)
        to_link_records.append(rec)

    unlink_precs, link_precs = diff_for_unlink_link_precs(prefix,
                                                          final_precs=IndexedSet(PrefixGraph(final_precs).graph),
                                                          specs_to_add=specs_to_add)

    actions = get_blank_actions(prefix)
    actions['UNLINK'].extend(Dist(prec) for prec in unlink_precs)
    actions['LINK'].extend(Dist(prec) for prec in link_precs)
    return actions


def get_index(channel_urls=(), prepend=True, platform=None,
              use_local=False, use_cache=False, unknown=None, prefix=None,
              repodata_fn="repodata.json"):
    """Get an index?
    Function from @wolfv here:
    https://gist.github.com/wolfv/cd12bd4a448c77ff02368e97ffdf495a.
    """
    real_urls = calculate_channel_urls(channel_urls, prepend, platform, use_local)
    check_whitelist(real_urls)

    dlist = mamba_api.DownloadTargetList()

    index = []
    for idx, url in enumerate(real_urls):
        channel = Channel(url)

        full_url = channel.url(with_credentials=True) + '/' + repodata_fn
        full_path_cache = os.path.join(
            create_cache_dir(),
            cache_fn_url(full_url, repodata_fn))

        print("Channel: ", channel.name, channel.subdir)
        sd = mamba_api.SubdirData(channel.name + '/' + channel.subdir,
                            full_url,
                            full_path_cache)

        sd.load()
        index.append((sd, channel))
        dlist.add(sd)

    is_downloaded = dlist.download(True)

    if not is_downloaded:
        raise RuntimeError("Error downloading repodata.")

    return index

class MambaSolver:
    """Run the mamba solver.
    Parameters
    ----------
    channels : list of str
        A list of the channels (e.g., `[conda-forge/linux-64]`, etc.)
    Example
    -------
    >>> solver = MambaSolver(['conda-forge/linux-64', 'conda-forge/noarch'])
    >>> solver.solve(["xtensor 0.18"])
    """
    def __init__(self, channels, platform):
        self.channels = channels
        self.platform = platform
        self.index = get_index(channels, platform=platform)

        self.pool = mamba_api.Pool()
        self.repos = []

        start_prio = len(channels)
        priority = start_prio
        subpriority = 0  # wrong! :)
        for subdir, channel in self.index:
            repo = mamba_api.Repo(
                self.pool,
                str(channel),
                subdir.cache_path(),
                channel.url(with_credentials=True)
            )
            repo.set_priority(start_prio, subpriority)
            start_prio -= 1
            self.repos.append(repo)

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
        print(specs)
        _specs = specs
        # _specs = [s.conda_build_form() for s in specs]

        api_solver.add_jobs(_specs, mamba_api.SOLVER_INSTALL)
        success = api_solver.solve()

        if not success:
            logger.warning(
                "MAMBA failed to solve specs \n\n%s\n\nfor channels "
                "\n\n%s\n\nThe reported errors are:\n\n%s",
                pprint.pformat(_specs),
                pprint.pformat(self.channels),
                api_solver.problems_to_str()
            )
        print(pkgs_dirs)
        package_cache = mamba_api.MultiPackageCache(pkgs_dirs)

        t = mamba_api.Transaction(api_solver, package_cache)
        t.print()
        mmb_specs, to_link, to_unlink = t.to_conda()
        specs_to_add = [MatchSpec(m) for m in mmb_specs[0]]
        specs_to_remove = [MatchSpec(m) for m in mmb_specs[1]]

        return to_action(specs_to_add, specs_to_remove, prefix, to_link, to_unlink, self.index)
        # return success

solver = None

        # txn = solver.solve_for_transaction(prune=prune, ignore_pinned=not pinned)
        # prefix_setup = txn.prefix_setups[prefix]
        # actions = get_blank_actions(prefix)
        # actions['UNLINK'].extend(Dist(prec) for prec in prefix_setup.unlink_precs)
        # actions['LINK'].extend(Dist(prec) for prec in prefix_setup.link_precs)


def mamba_get_install_actions(prefix, specs, env, 
                              retries=0, subdir=None,
                              verbose=True, debug=False, locking=True,
                              bldpkgs_dirs=None, timeout=900, disable_pip=False,
                              max_env_retry=3, output_folder=None, channel_urls=None):
    print(specs)
    _specs = [MatchSpec(s).conda_build_form() for s in specs]
    print(channel_urls)
    solution = solver.solve(_specs, prefix)
    return solution

conda_build.environ.get_install_actions = mamba_get_install_actions

import conda_build
from conda_build import api
from conda_build.build import build

from conda_build.config import get_or_merge_config, get_channel_urls

from conda_build.conda_interface import get_rc_urls

def main():
    recipe_dir = sys.argv[1]
    config = get_or_merge_config(None, {})
    config.channel_urls = get_rc_urls() + get_channel_urls({})
    config = conda_build.config.get_or_merge_config(
        None
        # exclusive_config_file=cbc_path
        # platform=platform,
        # arch=arch
    )

    # print(config.platform)

    global solver
    solver = MambaSolver(config.channel_urls, 'linux-64')

    cbc, _ = conda_build.variants.get_package_combined_spec(
        recipe_dir,
        config=config
    )

    # now we render the meta.yaml into an actual recipe
    metas = conda_build.api.render(
        recipe_dir,
        # platform=platform,
        # arch=arch,
        # ignore_system_variants=True,
        # variants=cbc,
        permit_undefined_jinja=True,
        finalize=False,
        bypass_env_check=True,
        # channel_urls=channel_sources,
    )

    stats = {}
    # import IPython; IPython.embed()

    build(metas, stats)
    for m, _, _, in metas:
        stats = {}
        import IPython; IPython.embed()
        print(m.name())
        print("------------")
        print(m.get_value('requirements/host'))
        print(m.get_value('requirements/build'))
        print(m.get_value('requirements/run'))

        # outputs = api.build(args.recipe, post=args.post, test_run_post=args.test_run_post,
        #                     build_only=args.build_only, notest=args.notest, already_built=None, config=config,
        #                     verify=args.verify, variants=args.variants)


        print("BUILDING", m.name())
        build(m, stats, post=False, test_run_post=False, build_only=False, notest=False, verify=True, variants=None)

    exit()
    # import IPython; IPython.embed()

    # now we loop through each one and check if we can solve it
    # we check run and host and ignore the rest
    mamba_solver = _mamba_factory(tuple(channel_sources), "%s-%s" % (platform, arch))

    solvable = True
    for m, _, _ in metas:
        host_req = (
            m.get_value('requirements/host', [])
            or m.get_value('requirements/build', [])
        )
        solvable &= mamba_solver.solve(host_req)

        run_req = m.get_value('requirements/run', [])
        solvable &= mamba_solver.solve(run_req)

        tst_req = (
            m.get_value('test/requires', [])
            + m.get_value('test/requirements', [])
            + run_req
        )
        solvable &= mamba_solver.solve(tst_req)

    # return solvable


    metadata_tuples = api.render(recipe, config=config)
                             # no_download_source=args.no_source,
                             # variants=args.variants)

