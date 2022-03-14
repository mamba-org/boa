# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause
import copy

from ruamel.yaml import YAML
import jinja2
from boa.core.jinja_support import jinja_functions
from conda_build.metadata import eval_selector, ns_cfg
from collections.abc import Mapping, Iterable

from boa.core.config import boa_config

console = boa_config.console


class TemplateStr:
    def __init__(self, template, rendered, missing_keys, context_dict):
        self.value = rendered
        self.template = template
        self.context_dict = context_dict
        self.missing_keys = missing_keys

    def split(self, sval=None):
        if sval:
            return self.value.split(sval)
        return self.value.split()

    def render(self, variant_vars):
        # execute render to record missing values!
        jenv = jinja2.Environment()
        cc = copy.copy(self.context_dict)
        cc.update(variant_vars)
        tmpl = jenv.from_string(self.template)
        rendered = tmpl.render(cc)
        return rendered

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return "TS{" + self.value + "} (" + " ".join(self.missing_keys) + ")"

    def to_json(self):
        return self.template


class ContextDictAccessor(jinja2.runtime.Context):

    global_missing = []

    def resolve_or_missing(self, key):
        val = jinja2.runtime.Context.resolve_or_missing(self, key)
        if val is jinja2.utils.missing:
            ContextDictAccessor.global_missing.append(key)
            return f"JINJA[{key}]"
        return val


def render_jinja(value, context_dict, jenv):
    if "{{" in value:
        print(type(value), value)
        tmpl = jenv.from_string(value)
        # execute render to record missing values!
        rendered = tmpl.render(context_dict)
        missing_vals = copy.deepcopy(ContextDictAccessor.global_missing)
        if not missing_vals:
            return rendered
        ContextDictAccessor.global_missing = []
        return TemplateStr(value, rendered, missing_vals, context_dict)

    return value


def render_recursive(dict_or_array, context_dict, jenv, key=None):
    if key is not None:
        das = dict_or_array[key]
        if isinstance(das, str):
            dict_or_array[key] = render_jinja(das, context_dict, jenv)
            return
    else:
        das = dict_or_array

    if isinstance(das, Mapping):
        for key in das.keys():
            render_recursive(das, context_dict, jenv, key=key)
        return

    if isinstance(das, Iterable):
        for i in range(len(das)):
            render_recursive(das, context_dict, jenv, key=i)
        return


def flatten_selectors(ydoc, namespace):
    if isinstance(ydoc, str):
        return ydoc

    if isinstance(ydoc, Mapping):
        has_sel = any(k.startswith("sel(") for k in ydoc.keys())
        if has_sel:
            for k, v in ydoc.items():
                selected = eval_selector(k[3:], namespace, [])
                if selected:
                    return v

            return None

        for k, v in ydoc.items():
            ydoc[k] = flatten_selectors(v, namespace)

    elif isinstance(ydoc, Iterable):
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


def ensure_list(x):
    if not type(x) is list:
        return [x]
    else:
        return x


def normalize_recipe(ydoc):
    # normalizing recipe:
    # sources -> list
    # every output -> to steps list
    if ydoc.get("context"):
        del ydoc["context"]

    if ydoc.get("source"):
        ydoc["source"] = ensure_list(ydoc["source"])

    toplevel_output = None

    if ydoc.get("outputs"):
        ydoc["steps"] = ydoc["outputs"]
        del ydoc["outputs"]

    if not ydoc.get("steps"):
        ydoc["steps"] = [{"package": ydoc["package"]}]
        toplevel_output = ydoc["steps"][0]
    else:
        for o in ydoc["steps"]:
            if "package" not in o:
                continue
            if not toplevel_output and o["package"]["name"] == ydoc["package"]["name"]:
                toplevel_output = o

            # merge version into steps if they don't have one
            if "version" not in o["package"]:
                o["package"]["version"] = ydoc["package"]["version"]

        # how do we handle no-output toplevel?!
        if toplevel_output is None:
            assert not ydoc.get("requirements")

    # move these under toplevel output
    if ydoc.get("requirements"):
        assert not toplevel_output.get("requirements")
        toplevel_output["requirements"] = ydoc["requirements"]
        del ydoc["requirements"]

    # move these under toplevel output
    if ydoc.get("test"):
        assert not toplevel_output.get("test")
        toplevel_output["test"] = ydoc["test"]
        del ydoc["test"]

    def move_to_toplevel(key):
        if ydoc.get("build", {}).get(key):
            if not toplevel_output.get("build"):
                toplevel_output["build"] = {}
            toplevel_output["build"][key] = ydoc["build"][key]
            del ydoc["build"][key]

    move_to_toplevel("run_exports")
    move_to_toplevel("ignore_run_exports")
    return ydoc


def default_jinja_vars(config):
    res = {}
    cfg = ns_cfg(config)

    res["build_platform"] = cfg["build_platform"]
    res["target_platform"] = cfg.get("target_platform", cfg["build_platform"])

    tgp = res["target_platform"]

    if tgp.startswith("win"):
        prefix = "%PREFIX%"
    else:
        prefix = "$PREFIX"

    # this adds PYTHON, R, RSCRIPT ... etc so that they can be used in the
    # recipe script
    for lang in ["python", "lua", "r", "rscript", "perl"]:
        res[lang.upper()] = getattr(config, "_get_" + lang)(prefix, tgp)

    return res


def render(recipe_path, config=None):
    # console.print(f"\n[yellow]Rendering {recipe_path}[/yellow]\n")
    # step 1: parse YAML
    with open(recipe_path) as fi:
        loader = YAML(typ="safe")
        ydoc = loader.load(fi)

    # step 2: fill out context dict
    context_dict = default_jinja_vars(config)
    context_dict.update(ydoc.get("context", {}))

    jenv = jinja2.Environment()
    # use our special context dict accessor to register when we have missing variables
    jenv.context_class = ContextDictAccessor

    for key, value in context_dict.items():
        if isinstance(value, str):
            tmpl = jenv.from_string(value)
            context_dict[key] = tmpl.render(context_dict)

    # step 3: recursively loop over the entire recipe and render jinja with context
    jenv.globals.update(jinja_functions(config, context_dict))
    for key in ydoc:
        render_recursive(ydoc[key], context_dict, jenv)

    flatten_selectors(ydoc, ns_cfg(config))

    # Normalize the entire recipe
    ydoc = normalize_recipe(ydoc)
    console.print("\n[yellow]Normalized recipe[/yellow]\n")
    console.print(ydoc)
    return ydoc
