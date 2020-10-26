from ruamel.yaml import YAML
import jinja2
from boa.core.jinja_support import jinja_functions
from conda_build.metadata import eval_selector, ns_cfg
import collections

from rich.console import Console

console = Console()


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


def ensure_list(x):
    if not type(x) is list:
        return [x]
    else:
        return x


def normalize_recipe(ydoc):
    # normalizing recipe:
    # sources -> list
    # every output -> to outputs list
    if ydoc.get("context"):
        del ydoc["context"]

    if ydoc.get("source"):
        ydoc["source"] = ensure_list(ydoc["source"])

    if not ydoc.get("outputs"):
        ydoc["outputs"] = [{"package": ydoc["package"]}]

        toplevel_output = ydoc["outputs"][0]
    else:
        for o in ydoc["outputs"]:
            if o["package"]["name"] == ydoc["package"]["name"]:
                toplevel_output = o
                break
        else:
            # how do we handle no-output toplevel?!
            toplevel_output = None
            assert not ydoc["requirements"]

    if ydoc.get("requirements"):
        # move these under toplevel output
        assert not toplevel_output.get("requirements")
        toplevel_output["requirements"] = ydoc["requirements"]
        del ydoc["requirements"]

    if ydoc.get("test"):
        # move these under toplevel output
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


def render(recipe_path, config=None):
    # console.print(f"\n[yellow]Rendering {recipe_path}[/yellow]\n")
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

    # step 3: recursively loop over the entire recipe and render jinja with context
    jenv.globals.update(jinja_functions(config, context_dict))
    for key in ydoc:
        render_recursive(ydoc[key], context_dict, jenv)

    flatten_selectors(ydoc, ns_cfg(config))

    ydoc = normalize_recipe(ydoc)
    # console.print("\n[yellow]Normalized recipe[/yellow]\n")
    # console.print(ydoc)
    return ydoc
