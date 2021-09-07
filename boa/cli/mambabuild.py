# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

import os
import sys
import re

from conda.models.match_spec import MatchSpec
from conda.gateways.disk.create import mkdir_p

import conda_build.environ
from conda_build import api
from conda_build.config import Config, get_channel_urls
from conda_build.cli.main_build import parse_args
from conda_build.index import update_index

from conda.base.context import context

from boa.core.solver import MambaSolver
from boa.core.utils import normalize_subdir
from mamba.utils import init_api_context
from boa.core.config import boa_config

only_dot_or_digit_re = re.compile(r"^[\d\.]+$")

solver_map = {}


def suppress_stdout():
    context.quiet = True
    init_api_context()
    boa_config.quiet = True
    boa_config.console.quiet = True


def _get_solver(channel_urls, subdir, output_folder):
    """Gets a solver from cache or creates a new one if needed."""
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


def prepare(**kwargs):
    """
    Prepare and configure the stage for mambabuild to run.

    The given **kwargs are passed to conda-build's Config which
    is the value returned by this function.
    """
    config = Config(**kwargs)
    config.channel_urls = get_channel_urls(kwargs)

    init_api_context()

    config.output_folder = os.path.abspath(config.output_folder)
    if not os.path.exists(config.output_folder):
        mkdir_p(config.output_folder)

    print(f"Updating build index: {(config.output_folder)}\n")
    update_index(config.output_folder, verbose=config.debug, threads=1)

    return config


def call_conda_build(action, config, **kwargs):
    """
    After having set up the stage for boa's mambabuild to
    use the mamba solver, we delegate the work of building
    the conda package back to conda-build.

    Args:
        action: "build" or "test"
        config: conda-build's Config

    Kwargs:
        additional keyword arguments are passed to conda-build

    Return:
        The result of conda-build's build: the built packages
    """
    recipe = config.recipe[0]

    if action == "output":
        suppress_stdout()
        result = api.get_output_file_paths(recipe, config=config, **kwargs)
        print(result)
    elif action == "test":
        result = api.test(recipe, config=config, **kwargs)
    elif action == "build":
        result = api.build(
            recipe,
            post=config.post,
            build_only=config.build_only,
            notest=config.notest,
            config=config,
            variants=config.variants,
            **kwargs,
        )
    else:
        raise ValueError("action should be 'build' or 'test', got: %r" % action)

    return result


def main():
    _, args = parse_args(sys.argv[1:])

    config = prepare(**args.__dict__)

    if args.test:
        action = "test"
    elif args.output:
        action = "output"
    else:
        action = "build"

    call_conda_build(action, config)
