import sys
import re

from conda.models.match_spec import MatchSpec
from conda.base.context import context

import conda_build.environ
from conda_build import api
from conda_build.config import Config, get_channel_urls
from conda_build.cli.main_build import parse_args
from conda_build.conda_interface import get_rc_urls
from conda_build.index import update_index

from boa.core.solver import MambaSolver

only_dot_or_digit_re = re.compile(r"^[\d\.]+$")

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

    print(f"Updating build index: {(config.output_folder)}\n")
    update_index(config.output_folder, verbose=config.debug, threads=1)

    # setting the repodata timeout to very high for conda
    context.local_repodata_ttl = 100000

    recipe = args["recipe"][0]

    global solver
    solver = MambaSolver(channel_urls, context.subdir)
    solver.replace_channels()
    cbc, _ = conda_build.variants.get_package_combined_spec(recipe, config=config)

    if args["test"]:
        api.test(recipe, config=config)
    else:
        api.build(
            recipe,
            post=args["post"],
            build_only=args["build_only"],
            notest=args["notest"],
            config=config,
            variants=args["variants"],
        )
