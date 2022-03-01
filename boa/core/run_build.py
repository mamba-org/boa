# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

import os
import glob
import json
import shutil
import pathlib
from collections import OrderedDict

from rich.console import Console
from rich.table import Table
from io import StringIO

from libmambapy import PrefixData
from libmambapy import Context as MambaContext

from boa.core.render import render
from boa.core.utils import get_config
from boa.core.recipe_output import Output
from boa.core.solver import refresh_solvers
from boa.core.build import build, download_source
from boa.core.metadata import MetaData
from boa.core.test import run_test
from boa.core.config import boa_config
from boa.core.validation import validate, ValidationError, SchemaError
from boa.core.variant_arithmetic import get_variants
from boa.tui.exceptions import BoaRunBuildException

from boa.helpers.asciigraph import draw as draw_ascii_graph

from conda_build.utils import rm_rf
from conda.common import toposort
from conda.base.context import context
from conda.gateways.disk.create import mkdir_p
from conda_build.utils import on_win
from conda_build.index import update_index

console = boa_config.console


def find_all_recipes(target, config):
    if os.path.isdir(target):
        cwd = target
    else:
        cwd = os.getcwd()
    yamls = glob.glob(os.path.join(cwd, "recipe.yaml"))
    yamls += glob.glob(os.path.join(cwd, "**", "recipe.yaml"))

    recipes = {}
    for fn in yamls:
        yml = render(fn, config=config)

        try:
            validate(yml)
            console.print("[green]Recipe validation OK[/green]")
        except ValidationError:
            console.print(
                "\n[red]Recipe validation not OK. This is currently [bold]ignored.\n\n"
            )
        except SchemaError:
            console.print(
                "\n[red]Recipe validation not OK. This is currently [bold]ignored.\n\n"
            )

        pkg_name = yml["package"]["name"]
        recipes[pkg_name] = yml
        recipes[pkg_name]["recipe_file"] = fn

        # find all outputs from recipe
        output_names = set([yml["package"]["name"]])
        for output in yml.get("steps", []):
            if "package" in output:
                output_names.add(output["package"]["name"])
            else:
                # support non-package steps
                output_names.add(output["step"]["name"])

        if "static" in [f["name"] for f in yml.get("features", [])]:
            output_names.add(yml["package"]["name"] + "-static")

        recipes[pkg_name]["output_names"] = output_names

    sort_recipes = {}

    def get_all_requirements(x):
        req = x.get("requirements", {}).get("host", [])
        req += x.get("requirements", {}).get("run", [])
        for feat in x.get("features", []):
            req += feat.get("requirements", {}).get("host", [])
            req += feat.get("requirements", {}).get("run", [])
        for o in x.get("steps", []):
            req += get_all_requirements(o)
        return req

    def recursive_add(target):
        all_requirements = {
            x.split(" ")[0] for x in get_all_requirements(recipes[target])
        }
        all_requirements = all_requirements.intersection(recipes.keys())
        sort_recipes[target] = all_requirements
        for req in all_requirements:
            if req not in sort_recipes:
                recursive_add(req)

    if not target or target not in recipes.keys():
        for k in recipes.keys():
            recursive_add(k)
    else:
        recursive_add(target)

    sorted_recipes = toposort.toposort(sort_recipes)
    num_recipes = len(sorted_recipes)
    console.print(f"Found {num_recipes} recipe{'s'[:num_recipes^1]}")
    for rec in sorted_recipes:
        console.print(f" - {rec}")

    return [recipes[x] for x in sorted_recipes]


def to_build_tree(ydoc, variants, config, cbc, selected_features):
    # first we need to perform a topological sort taking into account all the outputs
    outputs = [
        Output(
            o,
            config,
            parent=ydoc,
            conda_build_config=cbc,
            selected_features=selected_features,
        )
        for o in ydoc["steps"]
    ]
    outputs = {o.name: o for o in outputs}

    # inherit all requirements from previous build-only steps
    for _, o in outputs.items():
        o.inherit_requirements(outputs)

    # topological sort of the build steps
    sort_dict = {
        k: [x.name for x in o.all_requirements()] + o.required_steps
        for k, o in outputs.items()
    }
    tsorted = toposort.toposort(sort_dict)
    tsorted = [o for o in tsorted if o in sort_dict.keys()]

    sorted_outputs = OrderedDict((k, outputs[k]) for k in tsorted)
    for _, o in sorted_outputs.items():
        console.print(o)

    variants, final_outputs = get_variants(sorted_outputs, cbc, config)

    for k in variants:
        table = Table(show_header=True, header_style="bold")
        table.title = f"Output: [bold white]{k}[/bold white]"
        table.add_column("Package")
        table.add_column("Variant versions")
        for pkg, var in variants[k].items():
            table.add_row(pkg, "\n".join(var))
        console.print(table)

    edges, vertices = [], []

    for x in final_outputs:
        cc = Console(file=StringIO())
        t = Table(title=x.name)
        t.add_column("Variant")
        for v in x.differentiating_keys:
            t.add_row(f"{v} {x.variant[v]}")
        cc.print(t)

        str_output = cc.file.getvalue()

        vertices.append(str_output)
        for ps in x.parent_steps:
            edges.append([final_outputs.index(ps), final_outputs.index(x)])

    for ascii_graph in draw_ascii_graph(vertices, edges):
        print(ascii_graph)

    return final_outputs


def build_recipe(
    command,
    recipe_path,
    cbc,
    config,
    selected_features,
    notest: bool = False,
    skip_existing: bool = False,
    interactive: bool = False,
    skip_fast: bool = False,
    continue_on_failure: bool = False,
    rerun_build: bool = False,
):

    ydoc = render(recipe_path, config=config)
    # We need to assemble the variants for each output
    variants = {}
    # if we have a outputs section, use that order the outputs
    for o in ydoc["steps"]:
        # inherit from global package

        if "package" in o:
            pkg_meta = {}
            pkg_meta.update(ydoc["package"])
            pkg_meta.update(o.get("package", {}))
            o["package"] = pkg_meta

        build_meta = {}
        build_meta.update(ydoc.get("build"))
        build_meta.update(o.get("build", {}))
        o["build"] = build_meta

        o["selected_features"] = selected_features

        if "step" not in o:
            o["step"] = {"name": pkg_meta["name"]}

    # this takes in all variants and outputs, builds a dependency tree and returns
    # the final metadata
    sorted_outputs = to_build_tree(ydoc, variants, config, cbc, selected_features)

    # then we need to solve and build from the bottom up
    # we can't first solve all packages without finalizing everything
    #
    # FLOW:
    # =====
    # - solve the package
    #   - solv build, add weak run exports to
    # - add run exports from deps!

    if command == "render":
        if boa_config.json:
            jlist = [o.to_json() for o in sorted_outputs]
            print(json.dumps(jlist, indent=4))
        else:
            for o in sorted_outputs:
                console.print(o)
        return sorted_outputs

    # TODO this should be done cleaner
    top_name = ydoc["package"]["name"]
    o0 = sorted_outputs[0]
    o0.is_first = True
    o0.config.compute_build_id(top_name)

    console.print("\n[yellow]Initializing mamba solver[/yellow]\n")

    if all([o.skip() for o in sorted_outputs]):
        console.print("All outputs skipped.\n")
        return

    full_render = command == "full-render"

    if skip_fast:
        build_pkgs = []

        archs = [o0.variant["target_platform"], "noarch"]
        for arch in archs:
            build_pkgs += [
                os.path.basename(x.rsplit("-", 1)[0])
                for x in glob.glob(
                    os.path.join(o0.config.output_folder, arch, "*.tar.bz2",)
                )
            ]

        del_idx = []
        for i in range(len(sorted_outputs)):
            if f"{sorted_outputs[i].name}-{sorted_outputs[i].version}" in build_pkgs:
                del_idx.append(i)

        for idx in del_idx[::-1]:
            console.print(
                f"[green]Fast skip of {sorted_outputs[idx].name}-{sorted_outputs[idx].version}"
            )
            del sorted_outputs[idx]

    # Do not download source if we might skip
    if not (skip_existing or full_render) and not rerun_build:
        console.print("\n[yellow]Downloading source[/yellow]\n")
        download_source(MetaData(recipe_path, o0), interactive)
        cached_source = o0.sections["source"]
    else:
        cached_source = {}

    failed_outputs = []

    for o in sorted_outputs:
        try:
            console.print(
                f"\n[yellow]Preparing environment for [bold]{o.name}[/bold][/yellow]\n"
            )
            refresh_solvers()

            o.config._build_id = o0.config.build_id

            o.finalize_solve(sorted_outputs)

            meta = MetaData(recipe_path, o)
            o.set_final_build_id(meta)

            if o.skip() or full_render:
                continue

            final_name = meta.dist()

            # TODO this doesn't work for noarch!
            if skip_existing:
                final_name = meta.dist()

                if os.path.exists(
                    os.path.join(
                        o.config.output_folder,
                        o.variant["target_platform"],
                        final_name + ".tar.bz2",
                    )
                ):
                    console.print(f"\n[green]Skipping existing {final_name}\n")
                    continue

            if "build" in o.transactions:
                if os.path.isdir(o.config.build_prefix):
                    rm_rf(o.config.build_prefix)
                mkdir_p(os.path.join(o.config.build_prefix, "conda-meta"))
                try:
                    MambaContext().target_prefix = o.config.build_prefix
                    o.transactions["build"]["transaction"].print()
                    o.transactions["build"]["transaction"].execute(
                        PrefixData(o.config.build_prefix),
                    )
                except Exception:
                    # This currently enables windows-multi-build...
                    print("Could not instantiate build environment")

            if "host" in o.transactions:
                mkdir_p(os.path.join(o.config.host_prefix, "conda-meta"))
                MambaContext().target_prefix = o.config.host_prefix
                o.transactions["host"]["transaction"].print()
                o.transactions["host"]["transaction"].execute(
                    PrefixData(o.config.host_prefix)
                )

            if cached_source != o.sections["source"] and not rerun_build:
                download_source(meta, interactive)
                cached_source = o.sections["source"]

            if o.required_steps:
                console.print(f"\n[red]Reusing steps: {o.required_steps}[/red]")
                for step in o.required_steps:
                    # TODO handle variants
                    for other in sorted_outputs:
                        if other.name == step:
                            shutil.copytree(
                                other.moved_work_dir,
                                o.config.work_dir,
                                dirs_exist_ok=True,
                            )
                            break

            console.print(
                f"\n[yellow]Starting build for [bold]{o.name}[/bold][/yellow]\n"
            )

            final_outputs = build(
                meta,
                None,
                allow_interactive=interactive,
                continue_on_failure=continue_on_failure,
                provision_only=boa_config.debug,
            )

            if boa_config.debug:
                console.print("\n[yellow]Stopping for debugging.\n")

                ext = "bat" if on_win else "sh"
                work_dir = pathlib.Path(meta.config.build_prefix).parent / "work"
                build_cmd = work_dir / f"conda_build.{ext}"

                console.print(f"Work directory: {work_dir}")
                console.print(f"Try building again with {build_cmd}")

                return

            stats = {}
            if final_outputs is not None:
                for final_out in final_outputs:
                    if not notest:
                        run_test(
                            final_out,
                            o.config,
                            stats,
                            move_broken=False,
                            provision_only=False,
                        )

        except Exception as e:
            if continue_on_failure:
                console.print(
                    f"[yellow]Ignoring raised exception when building {o.name} ({e})"
                )
                failed_outputs.append(o)
                pass
            elif isinstance(e, BoaRunBuildException):
                raise e
            else:
                console.print_exception(show_locals=False)
                exit(1)

    for o in sorted_outputs:
        if o in failed_outputs:
            console.print(f"[red]Failed output: {o.name}")
        else:
            print("\n\n")
            console.print(o)

    return sorted_outputs


def extract_features(feature_string):
    if feature_string and len(feature_string):
        assert feature_string.startswith("[") and feature_string.endswith("]")
        features = [f.strip() for f in feature_string[1:-1].split(",")]
    else:
        features = []

    selected_features = {}
    for f in features:
        if f.startswith("~"):
            selected_features[f[1:]] = False
        else:
            selected_features[f] = True
    return selected_features


def run_build(args):
    if getattr(args, "json", False):
        global console
        console.quiet = True

    selected_features = extract_features(args.features)

    folder = args.recipe_dir or os.path.dirname(args.target)
    variant = {"target_platform": args.target_platform or context.subdir}
    cbc, config = get_config(folder, variant, args.variant_config_files)
    cbc["target_platform"] = [variant["target_platform"]]

    if not os.path.exists(config.output_folder):
        mkdir_p(config.output_folder)

    console.print(f"Updating build index: {(config.output_folder)}\n")
    update_index(config.output_folder, verbose=config.debug, threads=1)

    all_recipes = find_all_recipes(args.target, config)  # [noqa]

    console.print("\n[yellow]Assembling all recipes and variants[/yellow]\n")

    rerun_build = False
    for recipe in all_recipes:
        while True:
            try:
                build_recipe(
                    args.command,
                    recipe["recipe_file"],
                    cbc,
                    config,
                    selected_features=selected_features,
                    notest=getattr(args, "notest", False),
                    skip_existing=getattr(args, "skip_existing", False) != "default",
                    interactive=getattr(args, "interactive", False),
                    skip_fast=getattr(args, "skip_existing", "default") == "fast",
                    continue_on_failure=getattr(args, "continue_on_failure", False),
                    rerun_build=rerun_build,
                )
                rerun_build = False
            except BoaRunBuildException:
                rerun_build = True
            except Exception as e:
                raise e
            else:
                break
