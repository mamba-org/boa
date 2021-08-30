# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import NestedCompleter, PathCompleter

from ruamel.yaml import YAML

from boa.tui import patching

from .exceptions import BoaExitException, BoaRunBuildException

try:
    from watchgod import awatch

    watchgod_available = True
except ImportError:
    watchgod_available = False

import asyncio
import subprocess
import os
import shutil
from pathlib import Path
from glob import glob

from rich.console import Console
from rich.syntax import Syntax
from rich.rule import Rule

yaml = YAML(typ="rt")
yaml.preserve_quotes = True
yaml.default_flow_style = False
yaml.indent(sequence=4, offset=2)
yaml.width = 1000
# yaml.Representer = ruamel.yaml.representer.RoundTripRepresenter
# yaml.Loader = ruamel.yaml.RoundTripLoader

console = Console()

help_text = """
Enter a command:
    glob <host | build>
    edit <recipe | script>
    show <host | build>
    build
"""

build_context = None


def print_help():
    print(help_text)


def _get_prefix(env):
    if env == "host":
        return build_context.config.host_prefix
    if env == "build":
        return build_context.config.build_prefix
    if env == "work":
        return build_context.config.work_dir


def remove_prefix(strings):
    def replace_all(strings, x, r):
        for s in strings:
            res = []
            for s in strings:
                tmp = s.replace(x, r)
                tmp = tmp.replace("//", "/")
                res.append(tmp)
            return res

    res = replace_all(strings, build_context.config.build_prefix, "$BUILD_PREFIX/")
    res = replace_all(res, build_context.config.host_prefix, "$PREFIX/")
    res = replace_all(res, build_context.config.work_dir, "$WORK_DIR/")
    return res


def glob_search(env, search_text):
    p = _get_prefix(env)
    search_result = glob(os.path.join(p, search_text))
    if search_result:
        console.print(remove_prefix(search_result))
    else:
        console.print(f"[red]No results found for glob {search_text}[/red]")


def bottom_toolbar():
    return HTML('Interactive mode is <b><style bg="ansired">experimental</style></b>!')


fh = FileHistory(".boa_tui_history")
session = PromptSession(fh)


def get_completer():
    def get_paths():
        return [build_context.config.work_dir]

    return NestedCompleter.from_nested_dict(
        {
            "help": None,
            "glob": {"build": None, "host": None},
            "exit": None,
            "ls": PathCompleter(get_paths=get_paths),
            "edit": {
                "file": PathCompleter(get_paths=get_paths),
                "script": None,
                "recipe": None,
            },
            "build": None,
            "patch": {"show": None, "save": None},
        }
    )


def generate_patch(args):
    if len(args):
        cmd = args[0]
    else:
        cmd = "show"

    ref_dir = patching.create_reference_dir(build_context)
    patch_contents = patching.create_patch(
        os.path.join(ref_dir, "work"), build_context.config.work_dir
    )
    if patch_contents is None:
        console.print("[red]No difference found![/red]")
    else:
        console.print("\n")
        console.print(Rule("Diff Contents", end="\n\n"))
        console.print(Syntax(patch_contents, "diff"))
        console.print(Rule("", end="\n"))

    if cmd == "save" and patch_contents:
        if len(args) >= 2:
            fn = args[1]
            if not fn.endswith(".patch"):
                fn += ".patch"
            out_fn = Path(build_context.meta_path).parent / fn
            with open(out_fn, "w") as fo:
                fo.write(patch_contents)
            console.print(f"[green]Patch saved under: {out_fn}")

            data = yaml.load(open(build_context.meta_path))
            if "patches" in data["source"][0]:
                data["source"][0]["patches"].append(fn)
            else:
                data["source"][0]["patches"] = [fn]
            fp = open(build_context.meta_path, "w")
            yaml.dump(data, fp)
        else:
            console.print("[red]Please give a patch name as third argument")


cache_editor = None


def get_editor():
    global cache_editor

    if os.environ.get("EDITOR"):
        return os.environ["EDITOR"]
    elif cache_editor:
        return cache_editor
    else:
        for e in ["subl", "code", "vim", "emacs", "nano"]:
            cmd = shutil.which(e)
            if cmd:
                cache_editor = cmd
                break
    return cache_editor


def execute_tokens(token):
    if token[0] == "help":
        print_help()
    elif token[0] == "patch":
        generate_patch(token[1:])
    elif token[0] == "glob":
        glob_search(*token[1:])
    elif token[0] == "edit":
        if token[1] == "recipe":
            subprocess.call([get_editor(), build_context.meta_path])
        if token[1] == "script":
            subprocess.call(
                [get_editor(), os.path.join(build_context.path, "build.sh")]
            )
        elif token[1] == "file":
            if len(token) == 3:
                file = os.path.join(build_context.config.work_dir, token[2])
            else:
                file = build_context.config.work_dir
            subprocess.call([get_editor(), file])

    elif token[0] == "ls":
        # TODO add autocomplete
        out = subprocess.check_output(
            [
                "ls",
                "-l",
                "-a",
                "--color=always",
                os.path.join(build_context.config.work_dir, *token[1:]),
            ]
        )
        print(out.decode("utf-8", errors="ignore"))
    elif token[0] == "build":
        console.print("[yellow]Running build![/yellow]")
        raise BoaRunBuildException()
    elif token[0] == "exit":
        print("Exiting.")
        raise BoaExitException()
    else:
        console.print(f'[red]Could not understand command "{token[0]}"[/red]')


async def input_coroutine():
    completer = get_completer()
    while True:
        with patch_stdout(raw=True):
            text = await session.prompt_async(
                "> ", bottom_toolbar=bottom_toolbar, completer=completer
            )
            token = text.split()

            if len(token) == 0:
                continue

            try:
                execute_tokens(token)
            except KeyboardInterrupt:
                pass
            except BoaExitException as e:
                raise e
            except BoaRunBuildException as e:
                raise e
            except Exception as e:
                console.print(e)


async def watch_files_coroutine():
    if not watchgod_available:
        await asyncio.Future()

    async for changes in awatch(Path(build_context.meta_path).parent):
        console.print(
            "\n[green]recipe.yaml changed: rebuild by entering [/green][white]> [italic]build[/italic][/white]\n"
        )


async def prompt_coroutine():
    result = "exit"
    exit_tui = False

    watch_files_task = asyncio.create_task(watch_files_coroutine())
    while not exit_tui:
        try:
            await input_coroutine()
        except EOFError:
            text = await session.prompt_async(
                "Do you really want to exit ([y]/n)? ", bottom_toolbar=bottom_toolbar
            )
            if text == "y" or text == "":
                exit_tui = True
        except BoaExitException:
            exit_tui = True
        except BoaRunBuildException:
            exit_tui = True
            result = "run_build"
        except KeyboardInterrupt:
            print("CTRL+C pressed. Use CTRL-D to exit.")

    watch_files_task.cancel()
    console.print("[yellow]Goodbye![/yellow]")

    return result


async def enter_tui(context):
    global build_context
    build_context = context

    return await prompt_coroutine()


async def main():
    class Bunch(object):
        def __init__(self, adict):
            self.__dict__.update(adict)

    meta = Bunch(
        {
            "meta_path": "/home/wolfv/Programs/recipes/micromamba-feedstock/recipe/recipe.yaml",
            "config": Bunch(
                {
                    "work_dir": "/home/wolfv/miniconda3/conda-bld/micromamba_1603476359590/work/",
                    "host_prefix": "/home/wolfv/miniconda3/conda-bld/micromamba_1603476359590/_h_env_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_placehold_/",
                    "build_prefix": "/home/wolfv/miniconda3/conda-bld/micromamba_1603476359590/_build_env/",
                    "recipe_dir": "/home/wolfv/Programs/recipes/micromamba-feedstock/recipe/",
                }
            ),
        }
    )
    return await enter_tui(meta)


if __name__ == "__main__":
    asyncio.run(main())
