import os, sys
from ruamel.yaml import YAML
import jinja2
import collections

from conda_build.config import get_or_merge_config
from dataclasses import dataclass

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

def pin_subpackage(name, max_pin='x.x.x.x.x', exact=False):
    return f"{name} PIN_SUBPACKAGE[{max_pin}, {exact}]"

def pin_compatible(name, max_pin='x.x.x.x.x', exact=False):
    return f"{name} PIN_COMPATIBLE[{max_pin}, {exact}]"

def compiler(language):
    return f"COMPILER_{language.upper()} {language}"

def jinja_functions(config, context_dict):
    from functools import partial
    from conda_build.jinja_context import cdt

    return {
        'pin_subpackage': pin_subpackage,
        'pin_compatible': pin_compatible,
        'cdt': partial(cdt, config=config, permit_undefined_jinja=False),
        'compiler': compiler,
        'environ': os.environ
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
    is_pin: bool

    def __init__(self, ms):
        self.raw = ms
        self.splitted = ms.split()
        self.name = self.splitted[0]
        self.is_pin = len(self.splitted) > 1 and self.splitted[1].startswith("PIN_")
        self.is_simple = len(self.splitted) == 1

    def __repr__(self):
        return self.raw

class Recipe:

    def __init__(self, ydoc):
        self.ydoc = ydoc



def get_dependency_variants(requirements, conda_build_config, config):
    host = requirements.get("host") or []
    build = requirements.get("build") or []
    run = requirements.get("run") or []

    print(host)
    print(build)
    print(run)
    used_vars = {}

    def get_variants(env):
        specs = {}
        variants = {}

        for s in env:
            spec = CondaBuildSpec(s)
            specs[spec.name] = spec

        for n, cb_spec in specs.items():
            if cb_spec.raw.startswith("COMPILER_"):
                print(n)
                # This is a compiler package
                _, lang = cb_spec.raw.split()
                compiler = conda_build.jinja_context.compiler(lang, config)

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
                            p = {"name": n, "version": vsplit[0], 'build_number': 0}
                        elif len(vsplit) == 2:
                            p = {"name": n, "version": var.split()[0], "build": var.split()[1], 'build_number': 0}
                        else:
                            raise InvalidRecipeError("Check your conda_build_config")

                        if ms.match(p):
                            filtered.append(var)
                        else:
                            print(f"Configured variant ignored because of the recipe requirement:\n  {cb_spec.raw} : {var}")

                    if len(filtered):
                        variants[cb_spec.name] = filtered

        return variants

    v = get_variants(host)
    # get_variants(build)
    return v

from conda_build.metadata import eval_selector, ns_cfg
def flatten_selectors(ydoc, namespace):
    if isinstance(ydoc, str):
        return ydoc

    if isinstance(ydoc, collections.Mapping):
        has_sel = any(k.startswith('sel(') for k in ydoc.keys())
        # print(f"Has sel: {has_sel}")
        if has_sel:
            for k, v in ydoc.items():
                selected = eval_selector(k[3:], namespace, [])
                if selected:
                    return v

            return None

        for k, v in ydoc.items():
            # print(f"Checking {k}: {v}")
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

import copy

class Output:

    def __init__(self, d, config, parent=None):
        self.data = d
        self.config = config
        self.name = d["package"]["name"]
        self.requirements = copy.copy(d.get("requirements"))
        self.parent = parent

        for section in ('build', 'host', 'run'):
            self.requirements[section] = [CondaBuildSpec(r) for r in (self.requirements.get(section) or [])]

    def all_requirements(self):
        requirements = self.requirements.get("build") + \
                       self.requirements.get("host") + \
                       self.requirements.get("run")
        return requirements

    def apply_variant(self, variant):
        copied = copy.copy(self)

        for idx, r in enumerate(self.requirements['build']):
            if r.name.startswith('COMPILER_'):
                self.requirements['build'][idx] = CondaBuildSpec(conda_build.jinja_context.compiler(r.splitted[1].lower(), self.config))
        for idx, r in enumerate(self.requirements['host']):
            if r.name.startswith('COMPILER_'):
                self.requirements['host'][idx] = CondaBuildSpec(conda_build.jinja_context.compiler(r.splitted[1].lower(), self.config))

        # # insert compiler_cxx, compiler_c and compiler_fortran
        # variant['COMPILER_C'] = conda_build.jinja_context.compiler('c', self.config)
        # variant['COMPILER_CXX'] = conda_build.jinja_context.compiler('cxx', self.config)
        # variant['COMPILER_FORTRAN'] = conda_build.jinja_context.compiler('fortran', self.config)

        copied.variant = variant
        for idx, r in enumerate(self.requirements['build']):
            if r.name in variant:
                copied.requirements['build'][idx] = CondaBuildSpec(r.name + ' ' + variant[r.name])
        for idx, r in enumerate(self.requirements['host']):
            if r.name in variant:
                copied.requirements['host'][idx] = CondaBuildSpec(r.name + ' ' + variant[r.name])

        # todo figure out if we should pin like that in the run reqs as well?
        for idx, r in enumerate(self.requirements['run']):
            if r.name in variant:
                copied.requirements['run'][idx] = CondaBuildSpec(r.name + ' ' + variant[r.name])
        return copied

    # def apply_pinnings()

    def __repr__(self):
        s = f"Output: {self.name}\n"
        s += "Build:\n"
        for r in self.requirements["build"]:
            s += f" - {r}\n"
        s += "Host:\n"
        for r in self.requirements["host"]:
            s += f" - {r}\n"
        s += "Run:\n"
        for r in self.requirements["run"]:
            s += f" - {r}\n"
        return s

import itertools
from conda.common import toposort
def to_build_tree(ydoc, variants, config):
    # first we need to perform a topological sort taking into account all the outputs
    if ydoc.get("outputs"):
        outputs = [Output(o, config, parent=None) for o in ydoc["outputs"]]
        outputs = {o.name: o for o in outputs}
    else:
        outputs = [Output(ydoc, config, parent=None)]
        outputs = {o.name: o for o in outputs}

    final_outputs = []
    if len(outputs) > 1:
        sort_dict = {k: [x.name for x in o.all_requirements()] for k, o in outputs.items()}
        tsorted = toposort.toposort(sort_dict)
        tsorted = [o for o in tsorted if o in sort_dict.keys()]
        print(tsorted)

    for name, output in outputs.items():
        if variants.get(output.name):
            v = variants[output.name]
            print(v)
            combos = []
            for k in v:
                combos.append([(k, x) for x in v[k]])
            print(combos)
            all_combinations = tuple(itertools.product(*combos))
            all_combinations = [dict(x) for x in all_combinations]

            for c in all_combinations:
                final_outputs.append(output.apply_variant(c))

    for x in final_outputs:
        print("FINAL OUTPUT:")
        print(x)

    return final_outputs

def main(config=None):

    folder = sys.argv[1]
    config = get_or_merge_config(None, {})
    config_files = find_config_files(folder)
    parsed_cfg = collections.OrderedDict()
    for f in config_files:
        parsed_cfg[f] = parse_config_file(f, config)
        print(parsed_cfg[f])
        normalized = {}
        for k in parsed_cfg[f].keys():
            if '_' in k:
                n = k.replace('_', '-')
                normalized[n] =  parsed_cfg[f][k]
        parsed_cfg[f].update(normalized)
        print(parsed_cfg[f].keys())
    # TODO just using latest config here, should merge!
    cbc = parsed_cfg[config_files[-1]]

    recipe_path = os.path.join(folder, "recipe.yaml")

    # step 1: parse YAML
    with open(recipe_path) as fi:
        loader = YAML(typ='safe')
        ydoc = loader.load(fi)
    print(ydoc)

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
            variants[o["package"]["name"]] = get_dependency_variants(o["requirements"], cbc, config)
    else:
        # we only have one output
        variants[ydoc["package"]["name"]] = get_dependency_variants(ydoc["requirements"], cbc, config)

    # this takes in all variants and outputs, builds a dependency tree and returns 
    # the final metadata
    sorted_outputs = to_build_tree(ydoc, variants, config)

    # then we need to solve and build from the bottom up
    # we can't first solve all packages without finalizing everything

    # - solve the package
    #   - solv build, add weak run exports to 
    # - add run exports from deps!
    # - 
    # loader.dump(ydoc, sys.stdout)

if __name__ == '__main__':
    main()