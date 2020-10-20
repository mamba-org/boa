import os
from os.path import isdir

from ruamel.yaml import YAML
import jinja2
import collections
import argparse

from conda_build.config import get_or_merge_config

from conda.models.match_spec import MatchSpec
from .mambabuild import MambaSolver
import itertools
from conda.common import toposort

from conda_build.metadata import eval_selector, ns_cfg
from conda.core.package_cache_data import PackageCacheData
from conda.base.context import context

from mamba.mamba_api import PrefixData
from conda.gateways.disk.create import mkdir_p
from conda_build.index import update_index
import conda_build
from conda_build.variants import find_config_files, parse_config_file
from conda_build import utils

from boa.core.recipe_output import Output, CondaBuildSpec
from boa.core.build import build, download_source
from boa.core.metadata import MetaData

from rich.console import Console
from rich.table import Table

console = Console()

banner = r"""
           _
          | |__   ___   __ _
          | '_ \ / _ \ / _` |
          | |_) | (_) | (_| |
          |_.__/ \___/ \__,_|
"""


def render_recursive(dict_or_array, context_dict, jenv):
    # check if it's a dict?
    if isinstance(dict_or_array, collections.Mapping):
        for key, value in dict_or_array.items():
            if isinstance(value, str):
                tmpl = jenv.from_string(value)
                dict_or_array[key] = tmpl.render(context_dict)
            elif isinstance(value, collections.Mapping):
                render_recursive(dict_or_array[key], context_dict, jenv)
            elif isinstance(value, collections.Iterable):
                render_recursive(dict_or_array[key], context_dict, jenv)

    elif isinstance(dict_or_array, collections.Iterable):
        for i in range(len(dict_or_array)):
            value = dict_or_array[i]
            if isinstance(value, str):
                tmpl = jenv.from_string(value)
                dict_or_array[i] = tmpl.render(context_dict)
            elif isinstance(value, collections.Mapping):
                render_recursive(value, context_dict, jenv)
            elif isinstance(value, collections.Iterable):
                render_recursive(value, context_dict, jenv)


def pin_subpackage(name, max_pin="x.x.x.x.x", exact=False):
    return f"{name} PIN_SUBPACKAGE[{max_pin},{exact}]"


def pin_compatible(
    name,
    lower_bound=None,
    upper_bound=None,
    min_pin="x.x.x.x.x.x",
    max_pin="x",
    exact=False,
):
    return f"{name} PIN_COMPATIBLE[{lower_bound},{upper_bound},{min_pin},{max_pin},{exact}]"


def compiler(language):
    return f"COMPILER_{language.upper()} {language}"


def jinja_functions(config, context_dict):
    from functools import partial
    from conda_build.jinja_context import cdt

    return {
        "pin_subpackage": pin_subpackage,
        "pin_compatible": pin_compatible,
        "cdt": partial(cdt, config=config, permit_undefined_jinja=False),
        "compiler": compiler,
        "environ": os.environ,
    }


class Recipe:
    def __init__(self, ydoc):
        self.ydoc = ydoc


def get_dependency_variants(requirements, conda_build_config, config, features=()):
    host = requirements.get("host") or []
    build = requirements.get("build") or []
    # run = requirements.get("run") or []

    def get_variants(env):
        specs = {}
        variants = {}

        for s in env:
            spec = CondaBuildSpec(s)
            specs[spec.name] = spec

        for n, cb_spec in specs.items():
            if cb_spec.is_compiler:
                # This is a compiler package
                _, lang = cb_spec.raw.split()
                compiler = conda_build.jinja_context.compiler(lang, config)
                cb_spec.final = compiler
                config_key = f"{lang}_compiler"
                config_version_key = f"{lang}_compiler_version"

                if conda_build_config.get(config_key):
                    variants[config_key] = conda_build_config[config_key]
                if conda_build_config.get(config_version_key):
                    variants[config_version_key] = conda_build_config[
                        config_version_key
                    ]

            variant_key = n.replace("_", "-")
            if variant_key in conda_build_config:
                vlist = conda_build_config[variant_key]
                # we need to check if v matches the spec
                if cb_spec.is_simple:
                    variants[cb_spec.name] = vlist
                elif cb_spec.is_pin:
                    # ignore variants?
                    pass
                else:
                    # check intersection of MatchSpec and variants
                    ms = MatchSpec(cb_spec.raw)
                    filtered = []
                    for var in vlist:
                        vsplit = var.split()
                        if len(vsplit) == 1:
                            p = {
                                "name": n,
                                "version": vsplit[0],
                                "build_number": 0,
                                "build": "",
                            }
                        elif len(vsplit) == 2:
                            p = {
                                "name": n,
                                "version": var.split()[0],
                                "build": var.split()[1],
                                "build_number": 0,
                            }
                        else:
                            raise RuntimeError("Check your conda_build_config")

                        if ms.match(p):
                            filtered.append(var)
                        else:
                            console.print(
                                f"Configured variant ignored because of the recipe requirement:\n  {cb_spec.raw} : {var}"
                            )

                    if len(filtered):
                        variants[cb_spec.name] = filtered

        return variants

    v = get_variants(host + build)
    return v


def flatten_selectors(ydoc, namespace):
    if isinstance(ydoc, str):
        return ydoc

    if isinstance(ydoc, collections.Mapping):
        has_sel = any(k.startswith("sel(") for k in ydoc.keys())
        if has_sel:
            for k, v in ydoc.items():
                selected = eval_selector(k[3:], namespace, [])
                if selected:
                    return v

            return None

        for k, v in ydoc.items():
            ydoc[k] = flatten_selectors(v, namespace)

    elif isinstance(ydoc, collections.Iterable):
        to_delete = []
        for idx, el in enumerate(ydoc):
            res = flatten_selectors(el, namespace)
            if res is None:
                to_delete.append(idx)
            else:
                ydoc[idx] = res

        if len(to_delete):
            ydoc = [ydoc[idx] for idx in range(len(ydoc)) if idx not in to_delete]

        # flatten lists if necessary
        if any([isinstance(x, list) for x in ydoc]):
            final_list = []
            for x in ydoc:
                if isinstance(x, list):
                    final_list += x
                else:
                    final_list.append(x)
            ydoc = final_list

    return ydoc


def to_build_tree(ydoc, variants, config, selected_features):
    for k in variants:
        table = Table(show_header=True, header_style="bold")
        table.title = f"Output: [bold white]{k}[/bold white]"
        table.add_column("Package")
        table.add_column("Variant versions")
        for pkg, var in variants[k].items():
            table.add_row(pkg, "\n".join(var))
        console.print(table)

    # first we need to perform a topological sort taking into account all the outputs
    if ydoc.get("outputs"):
        outputs = [
            Output(o, config, parent=ydoc, selected_features=selected_features)
            for o in ydoc["outputs"]
        ]
        outputs = {o.name: o for o in outputs}
    else:
        outputs = [Output(ydoc, config, selected_features=selected_features)]
        outputs = {o.name: o for o in outputs}

    if len(outputs) > 1:
        sort_dict = {
            k: [x.name for x in o.all_requirements()] for k, o in outputs.items()
        }
        tsorted = toposort.toposort(sort_dict)
        tsorted = [o for o in tsorted if o in sort_dict.keys()]
    else:
        tsorted = [o for o in outputs.keys()]

    final_outputs = []

    for name in tsorted:
        output = outputs[name]
        if variants.get(output.name):
            v = variants[output.name]
            combos = []

            differentiating_keys = []
            for k in v:
                if len(v[k]) > 1:
                    differentiating_keys.append(k)
                combos.append([(k, x) for x in v[k]])

            all_combinations = tuple(itertools.product(*combos))
            all_combinations = [dict(x) for x in all_combinations]
            for c in all_combinations:
                x = output.apply_variant(c, differentiating_keys)
                final_outputs.append(x)
        else:
            x = output.apply_variant({})
            final_outputs.append(x)

    temp = final_outputs
    final_outputs = []
    has_intermediate = False
    for o in temp:
        if o.sections["build"].get("intermediate"):
            if has_intermediate:
                raise RuntimeError(
                    "Already found an intermediate build. There can be only one!"
                )
            final_outputs.insert(0, o)
            has_intermediate = True
        else:
            final_outputs.append(o)

    # Note: maybe this should happen _before_ apply variant?!
    if has_intermediate:
        # inherit dependencies
        def merge_requirements(a, b):
            b_names = [x.name for x in b]
            for r in a:
                if r.name in b_names:
                    continue
                else:
                    b.append(r)

        intermediate = final_outputs[0]
        for o in final_outputs[1:]:
            merge_requirements(
                intermediate.requirements["host"], o.requirements["host"]
            )
            merge_requirements(
                intermediate.requirements["build"], o.requirements["build"]
            )
            merged_variant = {}
            merged_variant.update(intermediate.config.variant)
            merged_variant.update(o.config.variant)
            o.config.variant = merged_variant

    return final_outputs


def get_config(folder):
    config = get_or_merge_config(None, {})
    config_files = find_config_files(folder)
    parsed_cfg = collections.OrderedDict()
    for f in config_files:
        parsed_cfg[f] = parse_config_file(f, config)
        normalized = {}
        for k in parsed_cfg[f].keys():
            if "_" in k:
                n = k.replace("_", "-")
                normalized[n] = parsed_cfg[f][k]
        parsed_cfg[f].update(normalized)

    # TODO just using latest config here, should merge!
    if len(config_files):
        cbc = parsed_cfg[config_files[-1]]
    else:
        cbc = {}

    return cbc, config


def main(config=None):

    parser = argparse.ArgumentParser(
        description="Boa, the fast, mamba powered-build tool for conda packages."
    )

    subparsers = parser.add_subparsers(help="sub-command help", dest="command")
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("recipe_dir", type=str)
    parent_parser.add_argument("--features", type=str)

    subparsers.add_parser("render", parents=[parent_parser], help="render a recipe")
    subparsers.add_parser(
        "convert",
        parents=[parent_parser],
        help="convert recipe.yaml to old-style meta.yaml",
    )
    subparsers.add_parser("build", parents=[parent_parser], help="build a recipe")

    transmute_parser = subparsers.add_parser(
        "transmute",
        parents=(),
        help="transmute one or many tar.bz2 packages into a conda packages (or vice versa!)",
    )
    transmute_parser.add_argument("files", type=str, nargs="+")
    transmute_parser.add_argument("-o", "--output-directory", type=str, default=".")
    transmute_parser.add_argument("-c", "--compression-level", type=int, default=22)

    args = parser.parse_args()

    command = args.command

    if command == "convert":
        from boa.cli import convert

        convert.main(args.recipe_dir)
        exit()

    if command == "transmute":
        from boa.cli import transmute

        transmute.main(args)
        exit()

    console.print(banner)

    folder = args.recipe_dir
    cbc, config = get_config(folder)

    if not os.path.exists(config.output_folder):
        mkdir_p(config.output_folder)
    console.print(f"Updating build index: {(config.output_folder)}\n")

    update_index(config.output_folder, verbose=config.debug, threads=1)

    recipe_path = os.path.join(folder, "recipe.yaml")

    # step 1: parse YAML
    with open(recipe_path) as fi:
        loader = YAML(typ="safe")
        ydoc = loader.load(fi)

    # step 2: fill out context dict
    context_dict = ydoc.get("context") or {}
    jenv = jinja2.Environment()
    for key, value in context_dict.items():
        if isinstance(value, str):
            tmpl = jenv.from_string(value)
            context_dict[key] = tmpl.render(context_dict)

    if ydoc.get("context"):
        del ydoc["context"]

    # step 3: recursively loop over the entire recipe and render jinja with context
    jenv.globals.update(jinja_functions(config, context_dict))
    for key in ydoc:
        render_recursive(ydoc[key], context_dict, jenv)

    flatten_selectors(ydoc, ns_cfg(config))

    if args.features:
        assert args.features.startswith("[") and args.features.endswith("]")
        features = [f.strip() for f in args.features[1:-1].split(",")]
    else:
        features = []

    selected_features = {}
    for f in features:
        if f.startswith("~"):
            selected_features[f[1:]] = False
        else:
            selected_features[f] = True

    # We need to assemble the variants for each output
    variants = {}
    # if we have a outputs section, use that order the outputs
    if ydoc.get("outputs"):
        for o in ydoc["outputs"]:
            # inherit from global package
            pkg_meta = {}
            pkg_meta.update(ydoc["package"])
            pkg_meta.update(o["package"])
            o["package"] = pkg_meta

            build_meta = {}
            build_meta.update(ydoc.get("build"))
            build_meta.update(o.get("build") or {})
            o["build"] = build_meta

            o["features"] = selected_features

            variants[o["package"]["name"]] = get_dependency_variants(
                o.get("requirements", {}), cbc, config, features
            )
    else:
        # we only have one output
        variants[ydoc["package"]["name"]] = get_dependency_variants(
            ydoc.get("requirements", {}), cbc, config, features
        )

    # this takes in all variants and outputs, builds a dependency tree and returns
    # the final metadata
    sorted_outputs = to_build_tree(ydoc, variants, config, selected_features)

    # then we need to solve and build from the bottom up
    # we can't first solve all packages without finalizing everything
    #
    # FLOW:
    # =====
    # - solve the package
    #   - solv build, add weak run exports to
    # - add run exports from deps!

    print("\n")
    if command == "render":
        for o in sorted_outputs:
            console.print(o)
        exit()

    # TODO this should be done cleaner
    top_name = ydoc["package"]["name"]
    o0 = sorted_outputs[0]
    o0.is_first = True
    o0.config.compute_build_id(top_name)

    solver = MambaSolver(["conda-forge"], context.subdir)
    print("\n")

    download_source(MetaData(recipe_path, o0))
    cached_source = o0.sections["source"]

    for o in sorted_outputs:
        solver.replace_channels()
        o.finalize_solve(sorted_outputs, solver)

        o.config._build_id = o0.config.build_id

        if "build" in o.transactions:
            if isdir(o.config.build_prefix):
                utils.rm_rf(o.config.build_prefix)
            mkdir_p(o.config.build_prefix)
            try:
                o.transactions["build"].execute(
                    PrefixData(o.config.build_prefix),
                    PackageCacheData.first_writable().pkgs_dir,
                )
            except Exception:
                # This currently enables windows-multi-build...
                print("Could not instantiate build environment")

        if "host" in o.transactions:
            mkdir_p(o.config.host_prefix)
            o.transactions["host"].execute(
                PrefixData(o.config.host_prefix),
                PackageCacheData.first_writable().pkgs_dir,
            )

        meta = MetaData(recipe_path, o)
        o.final_build_id = meta.build_id()

        if cached_source != o.sections["source"]:
            download_source(meta)

        build(meta, None)

    for o in sorted_outputs:
        console.print(o)


if __name__ == "__main__":
    main()
