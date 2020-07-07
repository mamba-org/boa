import os, sys
from ruamel.yaml import YAML
import jinja2, json
import collections
import re

from conda_build.config import get_or_merge_config
from dataclasses import dataclass

from conda.models.match_spec import MatchSpec
from .build import MambaSolver
import itertools
from conda.common import toposort

from conda_build.utils import apply_pin_expressions

import copy
from conda_build.metadata import eval_selector, ns_cfg
from conda.core.package_cache_data import PackageCacheData

from pprint import pprint

from colorama import Fore, Style
import colorama

colorama.init()

banner = """
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


deferred_parse = []


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


import conda_build
from conda_build.variants import find_config_files, parse_config_file
from conda_build.conda_interface import MatchSpec

from typing import Tuple


@dataclass
class CondaBuildSpec:
    name: str
    raw: str
    splitted: Tuple[str]
    is_pin: bool = False
    is_pin_compatible: bool = False
    is_compiler: bool = False

    # final: String

    from_run_export: bool = False
    from_pinnings: bool = False

    def __init__(self, ms):
        self.raw = ms
        self.splitted = ms.split()
        self.name = self.splitted[0]
        if len(self.splitted) > 1:
            self.is_pin = self.splitted[1].startswith("PIN_")
            self.is_pin_compatible = self.splitted[1].startswith("PIN_COMPATIBLE")
            self.is_compiler = self.splitted[0].startswith("COMPILER_")

        self.is_simple = len(self.splitted) == 1
        self.final = self.raw

        if self.is_pin_compatible:
            self.final[len("PIN_COMPATIBLE") + 1 : -1]

    @property
    def final_name(self):
        return self.final.split(" ")[0]

    def loosen_spec(self):
        if self.is_compiler or self.is_pin:
            return

        if len(self.splitted) == 1:
            return

        if re.search(r"[^0-9\.]+", self.splitted[1]) is not None:
            return

        dot_c = self.splitted[1].count(".")

        app = "*" if dot_c >= 2 else ".*"

        if len(self.splitted) == 3:
            self.final = (
                f"{self.splitted[0]} {self.splitted[1]}{app} {self.splitted[2]}"
            )
        else:
            self.final = f"{self.splitted[0]} {self.splitted[1]}{app}"

    def __repr__(self):
        self.loosen_spec()
        return self.final

    def eval_pin_subpackage(self, all_outputs):
        if not self.splitted[1].startswith("PIN_SUBPACKAGE"):
            return
        pkg_name = self.name
        max_pin, exact = self.splitted[1][len("PIN_SUBPACKAGE") + 1 : -1].split(",")
        exact = exact == "True"

        for o in all_outputs:
            if o.name == pkg_name:
                output = o
                break

        if not output:
            raise RuntimeError(f"Could not find output with name {pkg_name}")
        version = output.version
        build_string = output.build_string

        if exact:
            self.final = f"{pkg_name} {version} {build_string}"
        else:
            version_parts = version.split(".")
            count_pin = max_pin.count(".")
            version_pin = ".".join(version_parts[: count_pin + 1])
            version_pin += ".*"
            self.final = f"{pkg_name} {version_pin}"

    def eval_pin_compatible(self, build, host):

        lower_bound, upper_bound, min_pin, max_pin, exact = self.splitted[1][
            len("PIN_COMPATIBLE") + 1 : -1
        ].split(",")
        if lower_bound == "None":
            lower_bound = None
        if upper_bound == "None":
            upper_bound = None
        exact = exact == "True"

        versions = {b.name: b for b in build}
        versions.update({h.name: h for h in host})

        if versions:
            if exact and versions.get(self.name):
                compatibility = " ".join(versions[self.name].final_version)
            else:
                version = lower_bound or versions.get(self.name).final_version[0]
                if version:
                    if upper_bound:
                        if min_pin or lower_bound:
                            compatibility = ">=" + str(version) + ","
                        compatibility += "<{upper_bound}".format(
                            upper_bound=upper_bound
                        )
                    else:
                        compatibility = apply_pin_expressions(version, min_pin, max_pin)

        self.final = (
            " ".join((self.name, compatibility))
            if compatibility is not None
            else self.name
        )

    # def eval_compiler(self, compiler):


class Recipe:
    def __init__(self, ydoc):
        self.ydoc = ydoc


def get_dependency_variants(requirements, conda_build_config, config):
    host = requirements.get("host") or []
    build = requirements.get("build") or []
    run = requirements.get("run") or []

    used_vars = {}

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
                # print("COMPILER: ", compiler)
                config_key = f"{lang}_compiler"
                config_version_key = f"{lang}_compiler_version"

                variants[config_key] = conda_build_config[config_key]
                variants[config_version_key] = conda_build_config[config_version_key]

            if n in conda_build_config:
                vlist = conda_build_config[n]
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
                            raise InvalidRecipeError("Check your conda_build_config")

                        if ms.match(p):
                            filtered.append(var)
                        else:
                            print(
                                f"Configured variant ignored because of the recipe requirement:\n  {cb_spec.raw} : {var}"
                            )

                    if len(filtered):
                        variants[cb_spec.name] = filtered

        return variants

    v = get_variants(host + build)
    # v = get_variants(build)
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
            if res == None:
                to_delete.append(idx)
            else:
                ydoc[idx] = res

        if len(to_delete):
            ydoc = [ydoc[idx] for idx in range(len(ydoc)) if idx not in to_delete]

    return ydoc


class Output:
    def __init__(self, d, config, parent=None):
        self.data = d
        self.config = config

        self.name = d["package"]["name"]
        self.version = d["package"]["version"]
        self.build_string = d["package"].get("build_string")
        self.build_number = d["package"].get("build_number") or 0

        self.requirements = copy.copy(d.get("requirements"))
        self.parent = parent

        for section in ("build", "host", "run"):
            self.requirements[section] = [
                CondaBuildSpec(r) for r in (self.requirements.get(section) or [])
            ]

    def all_requirements(self):
        requirements = (
            self.requirements.get("build")
            + self.requirements.get("host")
            + self.requirements.get("run")
        )
        return requirements

    def apply_variant(self, variant):
        copied = copy.deepcopy(self)
        # # insert compiler_cxx, compiler_c and compiler_fortran
        # variant['COMPILER_C'] = conda_build.jinja_context.compiler('c', self.config)
        # variant['COMPILER_CXX'] = conda_build.jinja_context.compiler('cxx', self.config)
        # variant['COMPILER_FORTRAN'] = conda_build.jinja_context.compiler('fortran', self.config)

        copied.variant = variant
        for idx, r in enumerate(self.requirements["build"]):
            if r.name in variant:
                copied.requirements["build"][idx] = CondaBuildSpec(
                    r.name + " " + variant[r.name]
                )
                copied.requirements["build"][idx].from_pinnings = True
        for idx, r in enumerate(self.requirements["host"]):
            if r.name in variant:
                copied.requirements["host"][idx] = CondaBuildSpec(
                    r.name + " " + variant[r.name]
                )
                copied.requirements["host"][idx].from_pinnings = True

        # todo figure out if we should pin like that in the run reqs as well?
        for idx, r in enumerate(self.requirements["run"]):
            if r.name in variant:
                copied.requirements["run"][idx] = CondaBuildSpec(
                    r.name + " " + variant[r.name]
                )
                copied.requirements["run"][idx].from_pinnings = True

        for idx, r in enumerate(self.requirements["build"]):
            if r.name.startswith("COMPILER_"):
                lang = r.splitted[1].lower()
                version = variant[lang + "_compiler_version"]
                compiler = conda_build.jinja_context.compiler(lang, self.config)
                copied.requirements["build"][idx].final = f"{compiler} {version}*"
                copied.requirements["build"][idx].from_pinnings = True

        for idx, r in enumerate(self.requirements["host"]):
            if r.name.startswith("COMPILER_"):
                raise RuntimeError("Compiler should be in build section")

        return copied

    def __repr__(self):
        s = f"Output: {self.name}\n"
        s += "Build:\n"

        def format(x):
            version, fv = " ", " "
            if len(x.final.split(" ")) > 1:
                version = " ".join(r.final.split(" ")[1:])
            if hasattr(x, "final_version"):
                fv = x.final_version
            color = Fore.WHITE
            if x.from_run_export:
                color = Fore.BLUE
            if x.from_pinnings:
                color = Fore.GREEN
            if x.is_pin:
                if x.is_pin_compatible:
                    version = "PC " + version
                else:
                    version = "PS " + version
                color = Fore.CYAN

            if len(fv) >= 2:
                return f" - {r.final_name:<30} {color}{version:<20}{Style.RESET_ALL} {fv[0]:<10} {fv[1]:<10}\n"
            else:
                return f" - {r.final_name:<30} {color}{version:<20}{Style.RESET_ALL} {fv[0]:<10}\n"

        for r in self.requirements["build"]:
            s += format(r)
        s += "Host:\n"
        for r in self.requirements["host"]:
            s += format(r)
        s += "Run:\n"
        for r in self.requirements["run"]:
            s += format(r)
        return s

    def propagate_run_exports(self, env):
        # find all run exports
        collected_run_exports = []
        for s in self.requirements[env]:
            if hasattr(s, "final_version"):
                final_triple = (
                    f"{s.final_name}-{s.final_version[0]}-{s.final_version[1]}"
                )
            else:
                print(f"{s} has no final version")
                continue
            path = os.path.join(
                PackageCacheData.first_writable().pkgs_dir,
                final_triple,
                "info/run_exports.json",
            )
            if os.path.exists(path):
                with open(path) as fi:
                    run_exports_info = json.load(fi)
                    s.run_exports_info = run_exports_info
                    collected_run_exports.append(run_exports_info)
            else:
                s.run_exports_info = None

        def append_or_replace(env, spec):
            spec = CondaBuildSpec(spec)
            name = spec.name
            spec.from_run_export = True
            for idx, r in enumerate(self.requirements[env]):
                if r.final_name == name:
                    self.requirements[env][idx] = spec
                    return
            self.requirements[env].append(spec)

        if env == "build":
            for rex in collected_run_exports:
                if "strong" in rex:
                    for r in rex["strong"]:
                        append_or_replace("host", r)
                        append_or_replace("run", r)
                if "weak" in rex:
                    for r in rex["weak"]:
                        append_or_replace("host", r)

        if env == "host":
            for rex in collected_run_exports:
                if "strong" in rex:
                    for r in rex["strong"]:
                        append_or_replace("run", r)
                if "weak" in rex:
                    for r in rex["weak"]:
                        append_or_replace("run", r)

    def _solve_env(self, env, all_outputs, solver):
        if self.requirements.get(env):
            print(f"Finalizing {Fore.YELLOW}{env}{Style.RESET_ALL} for {self.name}")
            specs = self.requirements[env]
            for idx, s in enumerate(specs):
                if s.is_pin:
                    s.eval_pin_subpackage(all_outputs)
                if env == "run" and s.is_pin_compatible:
                    s.eval_pin_compatible(
                        self.requirements["build"], self.requirements["host"]
                    )

            spec_map = {s.final_name: s for s in specs}
            specs = [str(x) for x in specs]
            t = solver.solve(specs, "")

            _, install_pkgs, _ = t.to_conda()
            for _, _, p in install_pkgs:
                p = json.loads(p)
                if p["name"] in spec_map:
                    spec_map[p["name"]].final_version = (
                        p["version"],
                        p["build_string"],
                    )

            downloaded = t.fetch_extract_packages(
                PackageCacheData.first_writable().pkgs_dir, solver.repos
            )
            if not downloaded:
                raise RuntimeError("Did not succeed in downloading packages.")

            if env in ("build", "host"):
                self.propagate_run_exports(env)

    def finalize_solve(self, all_outputs, solver):
        print("\n")
        self._solve_env("build", all_outputs, solver)
        # TODO run_exports
        self._solve_env("host", all_outputs, solver)
        self._solve_env("run", all_outputs, solver)


def to_build_tree(ydoc, variants, config):
    print("\nVARIANTS:")
    for k in variants:
        print(f"Output: {k}\n----------------------------\n")
        pprint(variants[k])
        print("\n")

    # first we need to perform a topological sort taking into account all the outputs
    if ydoc.get("outputs"):
        outputs = [Output(o, config, parent=None) for o in ydoc["outputs"]]
        outputs = {o.name: o for o in outputs}
    else:
        outputs = [Output(ydoc, config, parent=None)]
        outputs = {o.name: o for o in outputs}

    final_outputs = []

    if len(outputs) > 1:
        sort_dict = {
            k: [x.name for x in o.all_requirements()] for k, o in outputs.items()
        }
        tsorted = toposort.toposort(sort_dict)
        tsorted = [o for o in tsorted if o in sort_dict.keys()]

    for name, output in outputs.items():
        if variants.get(output.name):
            v = variants[output.name]
            combos = []
            for k in v:
                combos.append([(k, x) for x in v[k]])
            all_combinations = tuple(itertools.product(*combos))
            all_combinations = [dict(x) for x in all_combinations]

            for c in all_combinations:
                final_outputs.append(output.apply_variant(c))

        else:
            final_outputs.append(output)

    return final_outputs


def main(config=None):
    print(banner)
    folder = sys.argv[1]
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

    # We need to assemble the variants for each output

    variants = {}
    # if we have a outputs section, use that order the outputs
    if ydoc.get("outputs"):

        # if ydoc.get("build"):
        #     raise InvalidRecipeError("You can either declare outputs, or build?")
        for o in ydoc["outputs"]:

            # inherit from global package
            pkg_meta = {}
            pkg_meta.update(ydoc["package"])
            pkg_meta.update(o["package"])
            o["package"] = pkg_meta

            build_meta = {}
            build_meta.update(ydoc.get("build"))
            build_meta.update(o.get("build"))
            o["build"] = build_meta
            variants[o["package"]["name"]] = get_dependency_variants(
                o["requirements"], cbc, config
            )
    else:
        # we only have one output
        variants[ydoc["package"]["name"]] = get_dependency_variants(
            ydoc["requirements"], cbc, config
        )

    # this takes in all variants and outputs, builds a dependency tree and returns
    # the final metadata
    sorted_outputs = to_build_tree(ydoc, variants, config)

    solver = MambaSolver(["conda-forge"], "linux-64")
    for o in sorted_outputs:
        o.finalize_solve(sorted_outputs, solver)

    # then we need to solve and build from the bottom up
    # we can't first solve all packages without finalizing everything

    # - solve the package
    #   - solv build, add weak run exports to
    # - add run exports from deps!
    # -

    for o in sorted_outputs:
        print("\n")
        print(o)

    # loader.dump(ydoc, sys.stdout)


if __name__ == "__main__":
    main()
