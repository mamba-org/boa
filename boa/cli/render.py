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

        print(variants)

    get_variants(host)
    get_variants(build)

    return 

def main(config=None):

    folder = sys.argv[1]
    config = get_or_merge_config(None, {})
    config_files = find_config_files(folder)
    parsed_cfg = collections.OrderedDict()
    for f in config_files:
        parsed_cfg[f] = parse_config_file(f, config)
        print(parsed_cfg[f])

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

    # We need to assemble the variants for each output

    # if we have a outputs section, use that order the outputs
    if ydoc.get("outputs"):
        if ydoc.get("build"):
            raise InvalidRecipeError("You can either declare outputs, or build?")
        for o in ydoc["outputs"]:
            print(o["name"])
            print("rest not implemented ...")
    else:
        # we only have one output
        get_dependency_variants(ydoc["requirements"], cbc, config)

    loader.dump(ydoc, sys.stdout)

if __name__ == '__main__':
    main()