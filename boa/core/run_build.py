import os
import glob
import itertools

from mamba.mamba_api import PrefixData
from conda.core.package_cache_data import PackageCacheData

from boa.core.render import render
from boa.core.utils import get_config
from boa.core.recipe_output import Output, CondaBuildSpec
from boa.core.solver import MambaSolver
from boa.core.build import build, download_source
from boa.core.metadata import MetaData
from boa.core.test import run_test

from conda_build.utils import rm_rf
import conda_build.jinja_context
from conda.common import toposort
from conda.models.match_spec import MatchSpec
from conda.base.context import context
from conda.gateways.disk.create import mkdir_p
from conda_build.variants import get_default_variant

from conda_build.index import update_index

from rich.console import Console
from rich.table import Table

console = Console()


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
        pkg_name = yml["package"]["name"]
        recipes[pkg_name] = yml
        recipes[pkg_name]["recipe_file"] = fn
        # find all outputs from recipe
        output_names = set([yml["package"]["name"]])
        for output in yml.get("outputs", []):
            output_names.add(output["package"]["name"])

        if "static" in [f["name"] for f in yml.get("features", [])]:
            output_names.add(yml["package"]["name"] + "-static")

        recipes[pkg_name]["output_names"] = output_names

    sort_recipes = {}

    def get_all_requirements(x):
        req = x.get("requirements", {}).get("host", [])
        for feat in x.get("features", []):
            req += feat.get("requirements", {}).get("host", [])
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

    if target == "" or target not in recipes.keys():
        keys = list(recipes.keys())
        if len(keys) > 1:
            console.print(
                f"[red]Warning, multiple recipes found. Selecting {keys[0]}.[/red]"
            )
        target = keys[0]

    recursive_add(target)

    sorted_recipes = toposort.toposort(sort_recipes)

    return [recipes[x] for x in sorted_recipes]


def get_dependency_variants(requirements, conda_build_config, config, features=()):
    host = requirements.get("host") or []
    build = requirements.get("build") or []
    # run = requirements.get("run") or []

    variants = {}
    default_variant = get_default_variant(config)

    variants["target_platform"] = conda_build_config.get(
        "target_platform", [default_variant["target_platform"]]
    )
    config.variant["target_platform"] = variants["target_platform"][0]

    def get_variants(env):
        specs = {}

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

            variant_key = n.replace("-", "_")
            vlist = None
            if variant_key in conda_build_config:
                vlist = conda_build_config[variant_key]
            elif variant_key in default_variant:
                vlist = [default_variant[variant_key]]
            if vlist:
                # we need to check if v matches the spec
                if cb_spec.is_simple:
                    variants[variant_key] = vlist
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
                                f"Configured variant ignored because of the recipe requirement:\n  {cb_spec.raw} : {var}\n"
                            )

                    if len(filtered):
                        variants[variant_key] = filtered

        return variants

    v = get_variants(host + build)
    return v


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


def build_recipe(args, recipe_path, cbc, config):

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

    ydoc = render(recipe_path, config=config)
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

            o["selected_features"] = selected_features

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

    if args.command == "render":
        for o in sorted_outputs:
            console.print(o)
        exit()

    # TODO this should be done cleaner
    top_name = ydoc["package"]["name"]
    o0 = sorted_outputs[0]
    o0.is_first = True
    o0.config.compute_build_id(top_name)

    console.print("\n[yellow]Initializing mamba solver[/yellow]\n")
    solver = MambaSolver([], context.subdir)

    console.print("\n[yellow]Downloading source[/yellow]\n")
    download_source(MetaData(recipe_path, o0), args.interactive)
    cached_source = o0.sections["source"]

    for o in sorted_outputs:
        console.print(
            f"\n[yellow]Preparing environment for [bold]{o.name}[/bold][/yellow]\n"
        )
        solver.replace_channels()
        o.finalize_solve(sorted_outputs, solver)

        o.config._build_id = o0.config.build_id

        if "build" in o.transactions:
            if os.path.isdir(o.config.build_prefix):
                rm_rf(o.config.build_prefix)
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
        o.set_final_build_id(meta)

        if cached_source != o.sections["source"]:
            download_source(meta, args.interactive)

        console.print(f"\n[yellow]Starting build for [bold]{o.name}[/bold][/yellow]\n")

        build(meta, None, allow_interactive=args.interactive)

        stats = {}
        run_test(meta, o.config, stats, move_broken=False, provision_only=False)
        print(stats)

    for o in sorted_outputs:
        print("\n\n")
        console.print(o)


def run_build(args):

    folder = args.recipe_dir
    cbc, config = get_config(folder)

    # target = os.path.dirname(args.target)

    if not os.path.exists(config.output_folder):
        mkdir_p(config.output_folder)

    console.print(f"Updating build index: {(config.output_folder)}\n")
    update_index(config.output_folder, verbose=config.debug, threads=1)

    all_recipes = find_all_recipes(args.target, config)  # [noqa]

    console.print("\n[yellow]Assembling all recipes and variants[/yellow]\n")

    for recipe in all_recipes:
        build_recipe(args, recipe["recipe_file"], cbc, config)
