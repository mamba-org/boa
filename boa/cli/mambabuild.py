# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

import os
import sys
import re
from glob import glob

from conda.models.match_spec import MatchSpec
from conda.gateways.disk.create import mkdir_p

import conda_build.environ
from conda_build import api
from conda_build.config import Config, get_channel_urls
from conda_build.cli.main_build import parse_args
from conda_build.exceptions import DependencyNeedsBuildingError
from conda_index.index import update_index

from conda.base.context import context

from boa.core.solver import MambaSolver
from boa.core.utils import normalize_subdir
from boa.core.utils import init_api_context
from boa.core.config import boa_config

only_dot_or_digit_re = re.compile(r"^[\d\.]+$")

solver_map = {}

# e.g. package-1.2.3-h5487548_0
dashed_spec_pattern = r"([^ ]+)-([^- ]+)-([^- ]+)"
# e.g. package 1.2.8.*
conda_build_spec_pattern = r"([^ ]+)(?:\ ([^ ]+))?(?:\ ([^ ]+))?"

problem_re = re.compile(
    rf"""
        ^(?:\ *-\ +)+
        (?:
            (?:
                package
                \ {dashed_spec_pattern}
                \ requires
                \ {conda_build_spec_pattern}
                ,\ but\ none\ of\ the\ providers\ can\ be\ installed
            ) | (?:
                package
                \ {dashed_spec_pattern}
                \ has\ constraint
                \ .*
                \ conflicting\ with
                \ {dashed_spec_pattern}
            ) | (?:
                nothing\ provides
                \ {conda_build_spec_pattern}
                \ needed\ by
                \ {dashed_spec_pattern}
            ) | (?:
                nothing\ provides(?:\ requested)?
                \ {conda_build_spec_pattern}
            )
        )
    """,
    re.VERBOSE,
)


def parse_problems(problems):
    conflicts = {}
    for line in problems.splitlines():
        match = problem_re.match(line)
        if not match:
            continue
        # All capture groups in problem_re only come from dashed_spec_pattern
        # and conda_build_spec_pattern and thus are always multiples of 3.
        for name, version, build in zip(*([iter(match.groups())] * 3)):
            if name is None:
                continue
            kwargs = {"name": name}
            if version is not None:
                kwargs["version"] = version
            if build is not None:
                kwargs["build"] = build
            conflicts[name] = MatchSpec(**kwargs)
    return set(conflicts.values())


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
            if re.match(only_dot_or_digit_re, vspec):
                n = s.conda_build_form()
                sn = n.split()
                if vspec.count(".") <= 1:
                    sn[1] = vspec + ".*"
                else:
                    sn[1] = vspec + "*"
                _specs[idx] = MatchSpec(" ".join(sn))

    _specs = [s.conda_build_form() for s in _specs]
    try:
        solution = solver.solve_for_action(_specs, prefix)
    except RuntimeError as e:
        conflict_packages = parse_problems(str(e))

        # we need to throw this exception for conda-build so it continues to search
        # the build tree
        err = DependencyNeedsBuildingError(packages=[str(x) for x in conflict_packages])
        err.matchspecs = conflict_packages
        err.subdir = subdir
        raise err

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
        print("\n".join(sorted(result)))
    elif action == "test":
        failed_recipes = []
        recipes = [
            item
            for sublist in [
                glob(os.path.abspath(recipe)) if "*" in recipe else [recipe]
                for recipe in config.recipe
            ]
            for item in sublist
        ]
        for recipe in recipes:
            try:
                result = api.test(recipe, config=config, **kwargs)
            except Exception:
                failed_recipes.append(recipe)
                continue
        if failed_recipes:
            print("Failed recipes:")
            for recipe in failed_recipes:
                print("  - %s" % recipe)
            sys.exit(len(failed_recipes))
        else:
            print("All tests passed")
        result = []

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
    boa_config.is_mambabuild = True
    _, args = parse_args(sys.argv[1:])

    config = prepare(**args.__dict__)

    if args.test:
        action = "test"
    elif args.output:
        action = "output"
    else:
        action = "build"

    call_conda_build(action, config)
