# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

import os
import re
import time
from os.path import exists, isdir, join
from subprocess import CalledProcessError

import yaml
from bs4 import UnicodeDammit

from conda.gateways.disk.create import mkdir_p
from conda_build import utils
from conda_build.utils import check_output_env, get_logger

from boa import __version__ as boa_version


def get_repository_info(recipe_path):
    """This tries to get information about where a recipe came from.  This is different
    from the source - you can have a recipe in svn that gets source via git."""
    try:
        if exists(join(recipe_path, ".git")):
            origin = check_output_env(
                ["git", "config", "--get", "remote.origin.url"], cwd=recipe_path
            )
            rev = check_output_env(["git", "rev-parse", "HEAD"], cwd=recipe_path)
            return "Origin {}, commit {}".format(origin, rev)
        elif isdir(join(recipe_path, ".hg")):
            origin = check_output_env(["hg", "paths", "default"], cwd=recipe_path)
            rev = check_output_env(["hg", "id"], cwd=recipe_path).split()[0]
            return "Origin {}, commit {}".format(origin, rev)
        elif isdir(join(recipe_path, ".svn")):
            info = check_output_env(["svn", "info"], cwd=recipe_path)
            info = info.decode(
                "utf-8"
            )  # Py3 returns a byte string, but re needs unicode or str.
            server = re.search("Repository Root: (.*)$", info, flags=re.M).group(1)
            revision = re.search("Revision: (.*)$", info, flags=re.M).group(1)
            return "{}, Revision {}".format(server, revision)
        else:
            return "{}, last modified {}".format(
                recipe_path,
                time.ctime(os.path.getmtime(join(recipe_path, "recipe.yaml"))),
            )
    except CalledProcessError:
        get_logger(__name__).debug("Failed to checkout source in " + recipe_path)
        return "{}, last modified {}".format(
            recipe_path, time.ctime(os.path.getmtime(join(recipe_path, "recipe.yaml")))
        )


def _copy_top_level_recipe(path, config, dest_dir, destination_subdir=None):
    files = utils.rec_glob(path, "*")
    file_paths = sorted([f.replace(path + os.sep, "") for f in files])

    # when this actually has a value, we're copying the top-level recipe into a subdirectory,
    #    so that we have record of what parent recipe produced subpackages.
    if destination_subdir:
        dest_dir = join(dest_dir, destination_subdir)
    else:
        # exclude recipe.yaml because the json dictionary captures its content
        file_paths = [
            f
            for f in file_paths
            if not (f == "recipe.yaml" or f == "conda_build_config.yaml")
        ]
    file_paths = utils.filter_files(file_paths, path)
    for f in file_paths:
        utils.copy_into(
            join(path, f),
            join(dest_dir, f),
            timeout=config.timeout,
            locking=config.locking,
            clobber=True,
        )


def _copy_output_recipe(m, dest_dir):
    _copy_top_level_recipe(m.path, m.config, dest_dir, "parent")

    this_output = m.get_rendered_output(m.name()) or {}
    install_script = this_output.get("script")
    build_inputs = []
    inputs = [install_script] + build_inputs
    file_paths = [script for script in inputs if script]
    file_paths = utils.filter_files(file_paths, m.path)

    for f in file_paths:
        utils.copy_into(
            join(m.path, f),
            join(dest_dir, f),
            timeout=m.config.timeout,
            locking=m.config.locking,
            clobber=True,
        )


def output_yaml(metadata, filename=None, suppress_outputs=False):
    local_metadata = metadata.copy()
    if (
        suppress_outputs
        and local_metadata.is_output
        and "outputs" in local_metadata.meta
    ):
        del local_metadata.meta["outputs"]
    output = yaml.dump((local_metadata.meta), default_flow_style=False, indent=4)
    if filename:
        if any(sep in filename for sep in ("\\", "/")):
            mkdir_p(os.path.dirname(filename))
        with open(filename, "w") as f:
            f.write(output)
        return "Wrote yaml to %s" % filename
    else:
        return output


def copy_recipe(m):
    if m.config.include_recipe and m.include_recipe():
        # store the rendered recipe.yaml file, plus information about where it came from
        #    and what version of conda-build created it
        recipe_dir = join(m.config.info_dir, "recipe")
        mkdir_p(recipe_dir)

        original_recipe = ""

        if m.is_output:
            _copy_output_recipe(m, recipe_dir)
        else:
            _copy_top_level_recipe(m.path, m.config, recipe_dir)
            original_recipe = m.meta_path

        output_metadata = m.copy()
        # hard code the build string, so that tests don't get it mixed up
        build = output_metadata.meta.get("build", {})
        build["string"] = output_metadata.build_id()
        output_metadata.meta["build"] = build

        # just for lack of confusion, don't show outputs in final rendered recipes
        if "outputs" in output_metadata.meta:
            del output_metadata.meta["outputs"]
        if "parent_recipe" in output_metadata.meta.get("extra", {}):
            del output_metadata.meta["extra"]["parent_recipe"]

        utils.sort_list_in_nested_structure(
            output_metadata.meta, ("build/script", "test/commands")
        )

        rendered = output_yaml(output_metadata)

        if original_recipe:
            with open(original_recipe, "rb") as f:
                original_recipe_text = UnicodeDammit(f.read()).unicode_markup

        if not original_recipe or not original_recipe_text == rendered:
            with open(join(recipe_dir, "recipe.yaml"), "w") as f:
                f.write("# This file created by boa {}\n".format(boa_version))
                if original_recipe:
                    f.write("# recipe.yaml template originally from:\n")
                    f.write("# " + get_repository_info(m.path) + "\n")
                f.write("# ------------------------------------------------\n\n")
                f.write(rendered)
            if original_recipe:
                utils.copy_into(
                    original_recipe,
                    os.path.join(recipe_dir, "recipe.yaml.template"),
                    timeout=m.config.timeout,
                    locking=m.config.locking,
                    clobber=True,
                )

        # dump the full variant in use for this package to the recipe folder
        with open(os.path.join(recipe_dir, "conda_build_config.yaml"), "w") as f:
            yaml.dump(m.config.variant, f)
