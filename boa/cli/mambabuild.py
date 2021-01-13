import os
import sys
import re

from conda.models.match_spec import MatchSpec
from conda.gateways.disk.create import mkdir_p

import conda_build.environ
from conda_build import api
from conda_build.config import Config
from conda_build.cli.main_build import parse_args
from conda_build.index import update_index

from boa.core.solver import MambaSolver
from boa.core.utils import normalize_subdir
from mamba.utils import init_api_context

only_dot_or_digit_re = re.compile(r"^[\d\.]+$")

solver_map = {}


def _get_solver(channel_urls, subdir, output_folder):
    """ Gets a solver from cache or creates a new one if needed.
    """
    subdir = normalize_subdir(subdir)

    if subdir in solver_map:
        solver = solver_map[subdir]
        solver.replace_channels()
    else:
        solver = MambaSolver(channel_urls, subdir, output_folder)
        solver_map[subdir] = solver

    return solver


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
    solver = _get_solver(channel_urls, subdir, output_folder)

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

    solution = solver.solve_for_action(_specs, prefix)
    return solution


conda_build.environ.get_install_actions = mamba_get_install_actions


def main():
    _, args = parse_args(sys.argv[1:])
    args = args.__dict__

    config = Config(**args)

    init_api_context()

    config.output_folder = os.path.abspath(config.output_folder)
    if not os.path.exists(config.output_folder):
        mkdir_p(config.output_folder)

    print(f"Updating build index: {(config.output_folder)}\n")
    update_index(config.output_folder, verbose=config.debug, threads=1)

    recipe = args["recipe"][0]

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
