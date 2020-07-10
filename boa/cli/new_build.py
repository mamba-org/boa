"""
Module that does most of the heavy lifting for the ``conda build`` command.
"""
from __future__ import absolute_import, division, print_function

from collections import deque, OrderedDict
import fnmatch
import glob2
import io
import json
import os
import warnings
from os.path import isdir, isfile, islink, join, dirname
import random
import re
import shutil
import stat
import string
import subprocess
import sys
import time

# this is to compensate for a requests idna encoding error.  Conda is a better place to fix,
#   eventually
# exception is raises: "LookupError: unknown encoding: idna"
#    http://stackoverflow.com/a/13057751/1170370
import encodings.idna  # NOQA

from bs4 import UnicodeDammit
import yaml

import conda_package_handling.api

# used to get version
from conda_build.conda_interface import env_path_backup_var_exists, conda_45, conda_46
from conda_build.conda_interface import PY3
from conda_build.conda_interface import prefix_placeholder
from conda_build.conda_interface import TemporaryDirectory
from conda_build.conda_interface import VersionOrder
from conda_build.conda_interface import text_type
from conda_build.conda_interface import CrossPlatformStLink
from conda_build.conda_interface import PathType, FileMode
from conda_build.conda_interface import EntityEncoder
from conda_build.conda_interface import get_rc_urls
from conda_build.conda_interface import url_path
from conda_build.conda_interface import root_dir
from conda_build.conda_interface import conda_private
from conda_build.conda_interface import MatchSpec
from conda_build.conda_interface import reset_context
from conda_build.conda_interface import context
from conda_build.conda_interface import UnsatisfiableError
from conda_build.conda_interface import NoPackagesFoundError
from conda_build.conda_interface import CondaError
from conda_build.conda_interface import pkgs_dirs
from conda_build.utils import env_var, glob, tmp_chdir, CONDA_TARBALL_EXTENSIONS

from conda_build import environ, source, tarcheck, utils
from conda_build.index import get_build_index, update_index
from conda_build.render import (
    output_yaml,
    bldpkg_path,
    render_recipe,
    reparse,
    distribute_variants,
    expand_outputs,
    try_download,
    execute_download_actions,
    add_upstream_pins,
)
import conda_build.os_utils.external as external
from conda_build.metadata import FIELDS, MetaData, default_structs
from conda_build.post import (
    post_process,
    post_build,
    fix_permissions,
    get_build_metadata,
)

from conda_build.exceptions import (
    indent,
    DependencyNeedsBuildingError,
    CondaBuildException,
)
from conda_build.variants import (
    set_language_env_vars,
    dict_of_lists_to_list_of_dicts,
    get_package_variants,
)
from conda_build.create_test import create_all_test_files

import conda_build.noarch_python as noarch_python

from conda import __version__ as conda_version
from conda_build import __version__ as conda_build_version

if sys.platform == "win32":
    import conda_build.windows as windows

if "bsd" in sys.platform:
    shell_path = "/bin/sh"
elif utils.on_win:
    shell_path = "bash"
else:
    shell_path = "/bin/bash"


from conda_build.build import (
    stats_key,
    seconds_to_text,
    log_stats,
    guess_interpreter,
    have_regex_files,
    have_prefix_files,
    get_bytes_or_text_as_bytes,
    regex_files_rg,
    mmap_or_read,
    regex_files_py,
    regex_matches_tighten_re,
    sort_matches,
    check_matches,
    rewrite_file_with_new_prefix,
    perform_replacements,
    _copy_top_level_recipe,
    sanitize_channel,
    check_external,
    prefix_replacement_excluded,
    chunks,
    _write_sh_activation_text,
    _write_activation_text,
    _copy_output_recipe,
    copy_recipe,
    copy_readme,
    # jsonify_info_yamls,
    copy_license,
    copy_recipe_log,
    copy_test_source_files,
    write_hash_input,
    get_files_with_prefix,
    record_prefix_files,
    write_info_files_file,
    write_link_json,
    write_about_json,
    write_info_json,
    write_no_link,
    get_entry_point_script_names,
    write_run_exports,
    get_short_path,
    has_prefix, is_no_link, get_inode, get_inode_paths,
    create_info_files_json_v1
)

def create_post_scripts(m):
    # TODO (Wolf)
    return

def create_info_files(m, files, prefix):
    """
    Creates the metadata files that will be stored in the built package.

    :param m: Package metadata
    :type m: Metadata
    :param files: Paths to files to include in package
    :type files: list of str
    """
    if utils.on_win:
        # make sure we use '/' path separators in metadata
        files = [_f.replace("\\", "/") for _f in files]

    if m.config.filename_hashing:
        write_hash_input(m)
    write_info_json(m)  # actually index.json
    write_about_json(m)
    write_link_json(m)
    write_run_exports(m)

    # copy_recipe(m)
    # copy_readme(m)
    # copy_license(m)
    # copy_recipe_log(m)
    # files.extend(jsonify_info_yamls(m))

    # create_all_test_files(m, test_dir=join(m.config.info_dir, 'test'))
    # if m.config.copy_test_source_files:
    #     copy_test_source_files(m, join(m.config.info_dir, 'test'))

    # write_info_files_file(m, files)

    files_with_prefix = get_files_with_prefix(m, files, prefix)
    record_prefix_files(m, files_with_prefix)
    checksums = create_info_files_json_v1(
        m, m.config.info_dir, prefix, files, files_with_prefix
    )

    # write_no_link(m, files)

    sources = m.get_section("source")
    if hasattr(sources, "keys"):
        sources = [sources]

    with io.open(join(m.config.info_dir, "git"), "w", encoding="utf-8") as fo:
        for src in sources:
            if src.get("git_url"):
                source.git_info(
                    os.path.join(m.config.work_dir, src.get("folder", "")),
                    verbose=m.config.verbose,
                    fo=fo,
                )

    if m.get_value("app/icon"):
        utils.copy_into(
            join(m.path, m.get_value("app/icon")),
            join(m.config.info_dir, "icon.png"),
            m.config.timeout,
            locking=m.config.locking,
        )
    return checksums

def post_process_files(m, initial_prefix_files):
    get_build_metadata(m)
    create_post_scripts(m)

    # this is new-style noarch, with a value of 'python'
    if m.noarch != "python":
        utils.create_entry_points(m.get_value("build/entry_points"), config=m.config)
    current_prefix_files = utils.prefix_files(prefix=m.config.host_prefix)

    python = (
        m.config.build_python
        if os.path.isfile(m.config.build_python)
        else m.config.host_python
    )
    post_process(
        m.get_value("package/name"),
        m.get_value("package/version"),
        sorted(current_prefix_files - initial_prefix_files),
        prefix=m.config.host_prefix,
        config=m.config,
        preserve_egg_dir=bool(m.get_value("build/preserve_egg_dir")),
        noarch=m.get_value("build/noarch"),
        skip_compile_pyc=m.get_value("build/skip_compile_pyc"),
    )

    # The post processing may have deleted some files (like easy-install.pth)
    current_prefix_files = utils.prefix_files(prefix=m.config.host_prefix)
    new_files = sorted(current_prefix_files - initial_prefix_files)
    new_files = utils.filter_files(new_files, prefix=m.config.host_prefix)

    host_prefix = m.config.host_prefix
    meta_dir = m.config.meta_dir
    if any(meta_dir in join(host_prefix, f) for f in new_files):
        meta_files = (
            tuple(
                f
                for f in new_files
                if m.config.meta_dir in join(m.config.host_prefix, f)
            ),
        )
        sys.exit(
            indent(
                """Error: Untracked file(s) %s found in conda-meta directory.
This error usually comes from using conda in the build script.  Avoid doing this, as it
can lead to packages that include their dependencies."""
                % meta_files
            )
        )
    post_build(m, new_files, build_python=python)

    entry_point_script_names = get_entry_point_script_names(
        m.get_value("build/entry_points")
    )
    if m.noarch == "python":
        pkg_files = [fi for fi in new_files if fi not in entry_point_script_names]
    else:
        pkg_files = new_files

    # the legacy noarch
    if m.get_value("build/noarch_python"):
        noarch_python.transform(m, new_files, m.config.host_prefix)
    # new way: build/noarch: python
    elif m.noarch == "python":
        noarch_python.populate_files(
            m, pkg_files, m.config.host_prefix, entry_point_script_names
        )

    current_prefix_files = utils.prefix_files(prefix=m.config.host_prefix)
    new_files = current_prefix_files - initial_prefix_files
    fix_permissions(new_files, m.config.host_prefix)

    return new_files


def bundle_conda(metadata, initial_files, env):

    print(len(initial_files))

    files = post_process_files(metadata, initial_files)

    print(files)
    print(len(files))

    # if output.get("name") and output.get("name") != "conda":
    #     assert "bin/conda" not in files and "Scripts/conda.exe" not in files, (
    #         "Bug in conda-build "
    #         "has included conda binary in package. Please report this on the conda-build issue "
    #         "tracker."
    #     )

    # first filter is so that info_files does not pick up ignored files
    files = utils.filter_files(files, prefix=metadata.config.host_prefix)
    # this is also copying things like run_test.sh into info/recipe
    utils.rm_rf(os.path.join(metadata.config.info_dir, "test"))

    output = {}

    with tmp_chdir(metadata.config.host_prefix):
        output["checksums"] = create_info_files(
            metadata, files, prefix=metadata.config.host_prefix
        )

    # here we add the info files into the prefix, so we want to re-collect the files list
    prefix_files = set(utils.prefix_files(metadata.config.host_prefix))
    files = utils.filter_files(
        prefix_files - initial_files, prefix=metadata.config.host_prefix
    )

    # basename = '-'.join([output['name'], metadata.version(), metadata.build_id()])
    basename = metadata.dist()
    tmp_archives = []
    final_outputs = []
    ext = ".tar.bz2"
    if output.get('type') == "conda_v2" or metadata.config.conda_pkg_format == "2":
        ext = ".conda"

    with TemporaryDirectory() as tmp:
        conda_package_handling.api.create(
            metadata.config.host_prefix, files, basename + ext, out_folder=tmp
        )
        tmp_archives = [os.path.join(tmp, basename + ext)]

        # we're done building, perform some checks
        for tmp_path in tmp_archives:
            #     if tmp_path.endswith('.tar.bz2'):
            #         tarcheck.check_all(tmp_path, metadata.config)
            output_filename = os.path.basename(tmp_path)

            #     # we do the import here because we want to respect logger level context
            #     try:
            #         from conda_verify.verify import Verify
            #     except ImportError:
            #         Verify = None
            #         log.warn("Importing conda-verify failed.  Please be sure to test your packages.  "
            #             "conda install conda-verify to make this message go away.")
            #     if getattr(metadata.config, "verify", False) and Verify:
            #         verifier = Verify()
            #         checks_to_ignore = (utils.ensure_list(metadata.config.ignore_verify_codes) +
            #                             metadata.ignore_verify_codes())
            #         try:
            #             verifier.verify_package(path_to_package=tmp_path, checks_to_ignore=checks_to_ignore,
            #                                     exit_on_error=metadata.config.exit_on_verify_error)
            #         except KeyError as e:
            #             log.warn("Package doesn't have necessary files.  It might be too old to inspect."
            #                      "Legacy noarch packages are known to fail.  Full message was {}".format(e))
            try:
                crossed_subdir = metadata.config.target_subdir
            except AttributeError:
                crossed_subdir = metadata.config.host_subdir
            subdir = (
                "noarch"
                if (metadata.noarch or metadata.noarch_python)
                else crossed_subdir
            )
            if metadata.config.output_folder:
                output_folder = os.path.join(metadata.config.output_folder, subdir)
            else:
                output_folder = os.path.join(
                    os.path.dirname(metadata.config.bldpkgs_dir), subdir
                )
            final_output = os.path.join(output_folder, output_filename)
            if os.path.isfile(final_output):
                utils.rm_rf(final_output)

            # disable locking here.  It's just a temp folder getting locked.  Removing it proved to be
            #    a major bottleneck.
            utils.copy_into(
                tmp_path, final_output, metadata.config.timeout, locking=False
            )
            final_outputs.append(final_output)

    update_index(
        os.path.dirname(output_folder), verbose=metadata.config.debug, threads=1
    )

    # clean out host prefix so that this output's files don't interfere with other outputs
    #   We have a backup of how things were before any output scripts ran.  That's
    #   restored elsewhere.

    if metadata.config.keep_old_work:
        print("\n\n\n\Renaming old HOST directory\n\n\n\n")

        prefix = metadata.config.host_prefix
        dest = os.path.join(
            os.path.dirname(prefix),
            "_".join(("_h_env_moved", metadata.dist(), metadata.config.host_subdir)),
        )
        print("Renaming host env directory, ", prefix, " to ", dest)
        if os.path.exists(dest):
            utils.rm_rf(dest)
        shutil.move(prefix, dest)
    else:
        print("\n\n\n\nErasing old HOST directory\n\n\n\n")
        utils.rm_rf(metadata.config.host_prefix)

    return final_outputs


def old_bundle_conda(output, metadata, env, stats, **kw):
    # print("Bundling shwundling")
    # log = utils.get_logger(__name__)
    # log.info("Packaging %s", metadata.dist())

    # files = output.get("files", [])

    # this is because without any requirements at all, we still need to have the host prefix exist
    # try:
    #     os.makedirs(metadata.config.host_prefix)
    # except OSError:
    #     pass

    # Use script from recipe?
    # script = utils.ensure_list(metadata.get_value("build/script", None))

    # # need to treat top-level stuff specially.  build/script in top-level stuff should not be
    # #     re-run for an output with a similar name to the top-level recipe
    # # is_output = 'package:' not in metadata.get_recipe_text()
    # # top_build = metadata.get_top_level_recipe_without_outputs().get('build', {}) or {}
    # activate_script = metadata.activate_build_script
    # # if (script and not output.get('script')) and (is_output or not top_build.get('script')):
    # if False:  # script and not output.get('script'):
    #     # do add in activation, but only if it's not disabled
    #     activate_script = metadata.config.activate
    #     script = "\n".join(script)
    #     suffix = "bat" if utils.on_win else "sh"
    #     script_fn = output.get("script") or "output_script.{}".format(suffix)
    #     with open(os.path.join(metadata.config.work_dir, script_fn), "w") as f:
    #         f.write("\n")
    #         f.write(script)
    #         f.write("\n")
    #     output["script"] = script_fn

    # if output.get("script"):
    #     env = environ.get_dict(m=metadata)

    #     interpreter = output.get("script_interpreter")
    #     if not interpreter:
    #         interpreter_and_args = guess_interpreter(output["script"])
    #         interpreter_and_args[0] = external.find_executable(
    #             interpreter_and_args[0], metadata.config.build_prefix
    #         )
    #         if not interpreter_and_args[0]:
    #             log.error(
    #                 "Did not find an interpreter to run {}, looked for {}".format(
    #                     output["script"], interpreter_and_args[0]
    #                 )
    #             )
    #         if (
    #             "system32" in interpreter_and_args[0]
    #             and "bash" in interpreter_and_args[0]
    #         ):
    #             print(
    #                 "ERROR :: WSL bash.exe detected, this will not work (PRs welcome!). Please\n"
    #                 "         use MSYS2 packages. Add `m2-base` and more (depending on what your"
    #                 "         script needs) to `requirements/build` instead."
    #             )
    #             sys.exit(1)
    #     else:
    #         interpreter_and_args = interpreter.split(" ")

    #     print("I am here!")
    #     initial_files = utils.prefix_files(metadata.config.host_prefix)
    #     env_output = env.copy()
    #     env_output["TOP_PKG_NAME"] = env["PKG_NAME"]
    #     env_output["TOP_PKG_VERSION"] = env["PKG_VERSION"]
    #     env_output["PKG_VERSION"] = metadata.version()
    #     env_output["PKG_NAME"] = metadata.get_value("package/name")
    #     env_output["RECIPE_DIR"] = metadata.path
    #     env_output["MSYS2_PATH_TYPE"] = "inherit"
    #     env_output["CHERE_INVOKING"] = "1"
    #     for var in utils.ensure_list(metadata.get_value("build/script_env")):
    #         if var not in os.environ:
    #             raise ValueError(
    #                 "env var '{}' specified in script_env, but is not set.".format(var)
    #             )
    #         env_output[var] = os.environ[var]
    #     dest_file = os.path.join(metadata.config.work_dir, output["script"])
    #     utils.copy_into(os.path.join(metadata.path, output["script"]), dest_file)
    #     from os import stat

    #     st = stat(dest_file)
    #     os.chmod(dest_file, st.st_mode | 0o200)
    #     if activate_script:
    #         _write_activation_text(dest_file, metadata)

    #     bundle_stats = {}
    #     utils.check_call_env(
    #         interpreter_and_args + [dest_file],
    #         cwd=metadata.config.work_dir,
    #         env=env_output,
    #         stats=bundle_stats,
    #     )
    #     log_stats(bundle_stats, "bundling {}".format(metadata.name()))
    #     if stats is not None:
    #         stats[
    #             stats_key(metadata, "bundle_{}".format(metadata.name()))
    #         ] = bundle_stats
    #     exit()

    # if files:
    #     # Files is specified by the output
    #     # we exclude the list of files that we want to keep, so post-process picks them up as "new"
    #     keep_files = set(
    #         os.path.normpath(pth)
    #         for pth in utils.expand_globs(files, metadata.config.host_prefix)
    #     )
    #     pfx_files = set(utils.prefix_files(metadata.config.host_prefix))
    #     initial_files = set(
    #         item
    #         for item in (pfx_files - keep_files)
    #         if not any(
    #             keep_file.startswith(item + os.path.sep) for keep_file in keep_files
    #         )
    #     )
    # else:
    #     if not metadata.always_include_files():
    #         log.warn(
    #             "No files or script found for output {}".format(output.get("name"))
    #         )
    #         build_deps = metadata.get_value("requirements/build")
    #         host_deps = metadata.get_value("requirements/host")
    #         build_pkgs = [pkg.split()[0] for pkg in build_deps]
    #         host_pkgs = [pkg.split()[0] for pkg in host_deps]
    #         dangerous_double_deps = {"python": "PYTHON", "r-base": "R"}
    #         for dep, env_var_name in dangerous_double_deps.items():
    #             if all(dep in pkgs_list for pkgs_list in (build_pkgs, host_pkgs)):
    #                 raise CondaBuildException(
    #                     "Empty package; {0} present in build and host deps.  "
    #                     "You probably picked up the build environment's {0} "
    #                     " executable.  You need to alter your recipe to "
    #                     " use the {1} env var in your recipe to "
    #                     "run that executable.".format(dep, env_var_name)
    #                 )
    #             elif dep in build_pkgs and metadata.uses_new_style_compiler_activation:
    #                 link = (
    #                     "https://conda.io/docs/user-guide/tasks/build-packages/"
    #                     "define-metadata.html#host"
    #                 )
    #                 raise CondaBuildException(
    #                     "Empty package; {0} dep present in build but not "
    #                     "host requirements.  You need to move your {0} dep "
    #                     "to the host requirements section.  See {1} for more "
    #                     "info.".format(dep, link)
    #                 )
    #     initial_files = set(utils.prefix_files(metadata.config.host_prefix))

    for pat in metadata.always_include_files():
        has_matches = False
        for f in set(initial_files):
            if fnmatch.fnmatch(f, pat):
                print("Including in package existing file", f)
                initial_files.remove(f)
                has_matches = True
        if not has_matches:
            log.warn("Glob %s from always_include_files does not match any files", pat)

    initial_files = set(utils.prefix_files(metadata.config.host_prefix))
    files = post_process_files(metadata, initial_files)

    if output.get("name") and output.get("name") != "conda":
        assert "bin/conda" not in files and "Scripts/conda.exe" not in files, (
            "Bug in conda-build "
            "has included conda binary in package. Please report this on the conda-build issue "
            "tracker."
        )

    # first filter is so that info_files does not pick up ignored files
    files = utils.filter_files(files, prefix=metadata.config.host_prefix)
    # this is also copying things like run_test.sh into info/recipe
    utils.rm_rf(os.path.join(metadata.config.info_dir, "test"))

    with tmp_chdir(metadata.config.host_prefix):
        output["checksums"] = create_info_files(
            metadata, files, prefix=metadata.config.host_prefix
        )

    # here we add the info files into the prefix, so we want to re-collect the files list
    prefix_files = set(utils.prefix_files(metadata.config.host_prefix))
    files = utils.filter_files(
        prefix_files - initial_files, prefix=metadata.config.host_prefix
    )

    # basename = '-'.join([output['name'], metadata.version(), metadata.build_id()])
    basename = metadata.dist()
    tmp_archives = []
    final_outputs = []
    ext = (
        ".conda"
        if (output.get("type") == "conda_v2" or metadata.config.conda_pkg_format == "2")
        else ".tar.bz2"
    )

    with TemporaryDirectory() as tmp:
        conda_package_handling.api.create(
            metadata.config.host_prefix, files, basename + ext, out_folder=tmp
        )
        tmp_archives = [os.path.join(tmp, basename + ext)]

        # we're done building, perform some checks
        for tmp_path in tmp_archives:
            #     if tmp_path.endswith('.tar.bz2'):
            #         tarcheck.check_all(tmp_path, metadata.config)
            output_filename = os.path.basename(tmp_path)

            #     # we do the import here because we want to respect logger level context
            #     try:
            #         from conda_verify.verify import Verify
            #     except ImportError:
            #         Verify = None
            #         log.warn("Importing conda-verify failed.  Please be sure to test your packages.  "
            #             "conda install conda-verify to make this message go away.")
            #     if getattr(metadata.config, "verify", False) and Verify:
            #         verifier = Verify()
            #         checks_to_ignore = (utils.ensure_list(metadata.config.ignore_verify_codes) +
            #                             metadata.ignore_verify_codes())
            #         try:
            #             verifier.verify_package(path_to_package=tmp_path, checks_to_ignore=checks_to_ignore,
            #                                     exit_on_error=metadata.config.exit_on_verify_error)
            #         except KeyError as e:
            #             log.warn("Package doesn't have necessary files.  It might be too old to inspect."
            #                      "Legacy noarch packages are known to fail.  Full message was {}".format(e))
            try:
                crossed_subdir = metadata.config.target_subdir
            except AttributeError:
                crossed_subdir = metadata.config.host_subdir
            subdir = (
                "noarch"
                if (metadata.noarch or metadata.noarch_python)
                else crossed_subdir
            )
            if metadata.config.output_folder:
                output_folder = os.path.join(metadata.config.output_folder, subdir)
            else:
                output_folder = os.path.join(
                    os.path.dirname(metadata.config.bldpkgs_dir), subdir
                )
            final_output = os.path.join(output_folder, output_filename)
            if os.path.isfile(final_output):
                utils.rm_rf(final_output)

            # disable locking here.  It's just a temp folder getting locked.  Removing it proved to be
            #    a major bottleneck.
            utils.copy_into(
                tmp_path, final_output, metadata.config.timeout, locking=False
            )
            final_outputs.append(final_output)
    update_index(
        os.path.dirname(output_folder), verbose=metadata.config.debug, threads=1
    )

    # clean out host prefix so that this output's files don't interfere with other outputs
    #   We have a backup of how things were before any output scripts ran.  That's
    #   restored elsewhere.

    if metadata.config.keep_old_work:
        prefix = metadata.config.host_prefix
        dest = os.path.join(
            os.path.dirname(prefix),
            "_".join(("_h_env_moved", metadata.dist(), metadata.config.host_subdir)),
        )
        print("Renaming host env directory, ", prefix, " to ", dest)
        if os.path.exists(dest):
            utils.rm_rf(dest)
        shutil.move(prefix, dest)
    else:
        utils.rm_rf(metadata.config.host_prefix)

    return final_outputs

bundlers = {
    "conda": bundle_conda,
    "conda_v2": bundle_conda,
    # "wheel": bundle_wheel,
}


def write_build_scripts(m, script, build_file):
    print("SCRIPT: ", script, " build file: ", build_file)
    with utils.path_prepended(m.config.host_prefix):
        with utils.path_prepended(m.config.build_prefix):
            env = environ.get_dict(m=m, variant={'no': 'variant'})

    env["CONDA_BUILD_STATE"] = "BUILD"

    # hard-code this because we never want pip's build isolation
    #    https://github.com/conda/conda-build/pull/2972#discussion_r198290241
    #
    # Note that pip env "NO" variables are inverted logic.
    #      PIP_NO_BUILD_ISOLATION=False means don't use build isolation.
    #
    env["PIP_NO_BUILD_ISOLATION"] = 'False'
    # some other env vars to have pip ignore dependencies.
    # we supply them ourselves instead.
    env["PIP_NO_DEPENDENCIES"] = True
    env["PIP_IGNORE_INSTALLED"] = True
    # pip's cache directory (PIP_NO_CACHE_DIR) should not be
    # disabled as this results in .egg-info rather than
    # .dist-info directories being created, see gh-3094

    # set PIP_CACHE_DIR to a path in the work dir that does not exist.
    env['PIP_CACHE_DIR'] = m.config.pip_cache_dir

    # tell pip to not get anything from PyPI, please.  We have everything we need
    # locally, and if we don't, it's a problem.
    env["PIP_NO_INDEX"] = True

    if m.noarch == "python":
        env["PYTHONDONTWRITEBYTECODE"] = True

    work_file = join(m.config.work_dir, 'conda_build.sh')
    env_file = join(m.config.work_dir, 'build_env_setup.sh')

    with open(env_file, 'w') as bf:
        for k, v in env.items():
            if v != '' and v is not None:
                bf.write('export {0}="{1}"\n'.format(k, v))

        if m.activate_build_script:
            _write_sh_activation_text(bf, m)

    with open(work_file, 'w') as bf:
        # bf.write('set -ex\n')
        bf.write('if [ -z ${CONDA_BUILD+x} ]; then\n')
        bf.write("    source {}\n".format(env_file))
        bf.write("fi\n")

        if isfile(build_file):
            bf.write(open(build_file).read())
        elif script:
            bf.write(script)


    print("BUILD FILE: ", build_file)

    os.chmod(work_file, 0o766)
    return work_file, env_file


def execute_build_script(m, src_dir, env, provision_only=False):

    script = utils.ensure_list(m.get_value("build/script", None))
    if script:
        script = "\n".join(script)

    if isdir(src_dir):
        build_stats = {}
        if utils.on_win:
            build_file = join(m.path, "bld.bat")
            if script:
                build_file = join(src_dir, "bld.bat")
                import codecs

                with codecs.getwriter("utf-8")(open(build_file, "wb")) as bf:
                    bf.write(script)
            windows.build(
                m, build_file, stats=build_stats, provision_only=provision_only
            )
        else:
            build_file = join(m.path, "build.sh")
            if isfile(build_file) and script:
                raise CondaBuildException(
                    "Found a build.sh script and a build/script section "
                    "inside meta.yaml. Either remove the build.sh script "
                    "or remove the build/script section in meta.yaml."
                )
            # There is no sense in trying to run an empty build script.
            if isfile(build_file) or script:
                if (isinstance(script, str) and script.endswith('.sh')):
                    build_file = os.path.join(m.path, script)

                work_file, _ = write_build_scripts(m, script, build_file)

                if not provision_only:
                    cmd = (
                        [shell_path]
                        + (["-x"] if m.config.debug else [])
                        + ["-o", "errexit", work_file]
                    )

                    # rewrite long paths in stdout back to their env variables
                    # if m.config.debug or m.config.no_rewrite_stdout_env:
                    if False:
                        rewrite_env = None
                    else:
                        rewrite_vars = ["PREFIX", "SRC_DIR"]
                        if not m.build_is_host:
                            rewrite_vars.insert(1, "BUILD_PREFIX")
                        rewrite_env = {k: env[k] for k in rewrite_vars if k in env}
                        for k, v in rewrite_env.items():
                            print(
                                "{0} {1}={2}".format(
                                    "set" if build_file.endswith(".bat") else "export",
                                    k,
                                    v,
                                )
                            )

                    print("Rewrite vars: ", rewrite_env)
                    # clear this, so that the activate script will get run as necessary
                    del env["CONDA_BUILD"]
                    # TODO fix the pakcage/name!!!
                    env["PKG_NAME"] = m.get_value('package/name')
                    print(f"\n\n\n\n\nPKG NAME ::::: {env['PKG_NAME']}\n\n\n\n\n\n")
                    # this should raise if any problems occur while building
                    print(env)
                    utils.check_call_env(
                        cmd,
                        env=env,
                        rewrite_stdout_env=rewrite_env,
                        cwd=src_dir,
                        stats=build_stats,
                    )
                    utils.remove_pycache_from_scripts(m.config.host_prefix)

        # if build_stats and not provision_only:
        #     log_stats(build_stats, "building {}".format(m.name()))
        #     if stats is not None:

def download_source(m):
    # Download all the stuff that's necessary
    with utils.path_prepended(m.config.build_prefix):
        try_download(m, no_download_source=False)


def build(m, stats={}):

    if m.skip():
        print(utils.get_skip_message(m))
        return {}

    log = utils.get_logger(__name__)

    with utils.path_prepended(m.config.build_prefix):
        env = environ.get_dict(m=m)

    env["CONDA_BUILD_STATE"] = "BUILD"
    if env_path_backup_var_exists:
        env["CONDA_PATH_BACKUP"] = os.environ["CONDA_PATH_BACKUP"]

    m.output.sections["package"]["name"] = m.output.name
    env["PKG_NAME"] = m.get_value('package/name')

    print("\n\n\n\n\n\nPKG_NAME == ", env["PKG_NAME"])
    # return

    src_dir = m.config.work_dir
    if isdir(src_dir):
        if m.config.verbose:
            print("source tree in:", src_dir)
    else:
        if m.config.verbose:
            print("no source - creating empty work folder")
        os.makedirs(src_dir)

    utils.rm_rf(m.config.info_dir)
    files_before_script = utils.prefix_files(prefix=m.config.host_prefix)

    with open(join(m.config.build_folder, "prefix_files.txt"), "w") as f:
        f.write("\n".join(sorted(list(files_before_script))))
        f.write("\n")

    execute_build_script(m, src_dir, env)

    files_after_script = utils.prefix_files(prefix=m.config.host_prefix)

    files_difference = files_after_script - files_before_script
    print(len(files_difference))
    # def bundle_conda(output, metadata, initial_files, env):

    bundle_conda(m, files_before_script, env)

    print(f"New files: {files_difference}")
    # bundle_conda()












# def build(
#     m,
#     stats,
#     post=None,
#     need_source_download=True,
#     need_reparse_in_env=False,
#     built_packages=None,
#     notest=False,
#     provision_only=False,
# ):
#     """
#     Build the package with the specified metadata.

#     :param m: Package metadata
#     :type m: Metadata
#     :type post: bool or None. None means run the whole build. True means run
#     post only. False means stop just before the post.
#     :type need_source_download: bool: if rendering failed to download source
#     (due to missing tools), retry here after build env is populated
#     """
#     print("Metadata path: ", m.path)

#     default_return = {}
#     if not built_packages:
#         built_packages = {}

#     if m.skip():
#         print(utils.get_skip_message(m))
#         return default_return

#     log = utils.get_logger(__name__)
#     # host_actions = []
#     # build_actions = []
#     # output_metas = []

#     with utils.path_prepended(m.config.build_prefix):
#         # TODO!
#         # env = environ.get_dict(m=m)
#         env = {"CONDA_BUILD": "TODO"}
#     env["CONDA_BUILD_STATE"] = "BUILD"
#     if env_path_backup_var_exists:
#         env["CONDA_PATH_BACKUP"] = os.environ["CONDA_PATH_BACKUP"]

#     env["PKG_NAME"] = m.get_value('package/name')
#     print("GOT PACKAGE ANAME:")
#     print(env)
#     # this should be a no-op if source is already here
#     # if m.needs_source_for_render:
#     #     try_download(m, no_download_source=False)

#     # if post in [False, None]:
#     # output_metas = expand_outputs([(m, need_source_download, need_reparse_in_env)])

#     # skipped = []
#     # package_locations = []
#     # # TODO: should we check both host and build envs?  These are the same, except when
#     # #    cross compiling.
#     # top_level_pkg = m
#     # top_level_needs_finalizing = True
#     # for _, om in output_metas:
#     #     if om.skip() or (m.config.skip_existing and is_package_built(om, 'host')):
#     #         skipped.append(bldpkg_path(om))
#     #     else:
#     #         package_locations.append(bldpkg_path(om))
#     #     if om.name() == m.name():
#     #         top_level_pkg = om
#     #         top_level_needs_finalizing = False
#     # if not package_locations:
#     #     print("Packages for ", m.path or m.name(), "with variant {} "
#     #           "are already built and available from your configured channels "
#     #           "(including local) or are otherwise specified to be skipped."
#     #           .format(m.get_hash_contents()))
#     #     return default_return

#     # if not provision_only:
#     #     printed_fns = []
#     #     for pkg in package_locations:
#     #         if (os.path.splitext(pkg)[1] and any(
#     #                 os.path.splitext(pkg)[1] in ext for ext in CONDA_TARBALL_EXTENSIONS)):
#     #             printed_fns.append(os.path.basename(pkg))
#     #         else:
#     #             printed_fns.append(pkg)
#     #     print("BUILD START:", printed_fns)

#     # environ.remove_existing_packages([m.config.bldpkgs_dir],
#     #         [pkg for pkg in package_locations if pkg not in built_packages], m.config)

#     # specs = [ms.spec for ms in m.ms_depends('build')]

#     # if any(out.get('type') == 'wheel' for out in m.meta.get('outputs', [])):
#     #     specs.extend(['pip', 'wheel'])

#     # if top_level_needs_finalizing:
#     #     utils.insert_variant_versions(
#     #         top_level_pkg.meta.get('requirements', {}), top_level_pkg.config.variant, 'build')
#     #     utils.insert_variant_versions(
#     #         top_level_pkg.meta.get('requirements', {}), top_level_pkg.config.variant, 'host')

#     #     exclude_pattern = None
#     #     excludes = set(top_level_pkg.config.variant.get('ignore_version', []))
#     #     for key in top_level_pkg.config.variant.get('pin_run_as_build', {}).keys():
#     #         if key in excludes:
#     #             excludes.remove(key)
#     #     if excludes:
#     #         exclude_pattern = re.compile(r'|'.join(r'(?:^{}(?:\s|$|\Z))'.format(exc)
#     #                                         for exc in excludes))
#     #     add_upstream_pins(m, False, exclude_pattern)

#     # create_build_envs(top_level_pkg, notest)

#     # this check happens for the sake of tests, but let's do it before the build so we don't
#     #     make people wait longer only to see an error
#     # warn_on_use_of_SRC_DIR(m)

#     # Execute any commands fetching the source (e.g., git) in the _build environment.
#     # This makes it possible to provide source fetchers (eg. git, hg, svn) as build
#     # dependencies.
#     with utils.path_prepended(m.config.build_prefix):
#         try_download(m, no_download_source=False)

#     # if need_source_download and not m.final:
#     #     m.parse_until_resolved(allow_no_other_outputs=True)
#     # elif need_reparse_in_env:
#     #     m = reparse(m)

#     # Write out metadata for `conda debug`, making it obvious that this is what it is, must be done
#     # after try_download()
#     # output_yaml(m, os.path.join(m.config.work_dir, 'metadata_conda_debug.yaml'))

#     # get_dir here might be just work, or it might be one level deeper,
#     #    dependening on the source.
#     src_dir = m.config.work_dir
#     if isdir(src_dir):
#         if m.config.verbose:
#             print("source tree in:", src_dir)
#     else:
#         if m.config.verbose:
#             print("no source - creating empty work folder")
#         os.makedirs(src_dir)

#     utils.rm_rf(m.config.info_dir)
#     files1 = utils.prefix_files(prefix=m.config.host_prefix)
#     with open(join(m.config.build_folder, "prefix_files.txt"), "w") as f:
#         f.write("\n".join(sorted(list(files1))))
#         f.write("\n")

#     # Use script from recipe?
#     script = utils.ensure_list(m.get_value("build/script", None))
#     if script:
#         script = "\n".join(script)

#     if isdir(src_dir):
#         build_stats = {}
#         if utils.on_win:
#             build_file = join(m.path, "bld.bat")
#             if script:
#                 build_file = join(src_dir, "bld.bat")
#                 import codecs

#                 with codecs.getwriter("utf-8")(open(build_file, "wb")) as bf:
#                     bf.write(script)
#             windows.build(
#                 m, build_file, stats=build_stats, provision_only=provision_only
#             )
#         else:
#             build_file = join(m.path, "build.sh")
#             if isfile(build_file) and script:
#                 raise CondaBuildException(
#                     "Found a build.sh script and a build/script section "
#                     "inside meta.yaml. Either remove the build.sh script "
#                     "or remove the build/script section in meta.yaml."
#                 )
#             # There is no sense in trying to run an empty build script.
#             if isfile(build_file) or script:
#                 if (isinstance(script, str) and script.endswith('.sh')):
#                     build_file = os.path.join(m.path, script)

#                 work_file, _ = write_build_scripts(m, script, build_file)

#                 if not provision_only:
#                     cmd = (
#                         [shell_path]
#                         + (["-x"] if m.config.debug else [])
#                         + ["-o", "errexit", work_file]
#                     )

#                     # rewrite long paths in stdout back to their env variables
#                     if m.config.debug or m.config.no_rewrite_stdout_env:
#                         rewrite_env = None
#                     else:
#                         rewrite_vars = ["PREFIX", "SRC_DIR"]
#                         if not m.build_is_host:
#                             rewrite_vars.insert(1, "BUILD_PREFIX")
#                         rewrite_env = {k: env[k] for k in rewrite_vars if k in env}
#                         for k, v in rewrite_env.items():
#                             print(
#                                 "{0} {1}={2}".format(
#                                     "set" if build_file.endswith(".bat") else "export",
#                                     k,
#                                     v,
#                                 )
#                             )

#                     # clear this, so that the activate script will get run as necessary
#                     del env["CONDA_BUILD"]
#                     env["PKG_NAME"] = m.get_value('package/name')
#                     # this should raise if any problems occur while building
#                     utils.check_call_env(
#                         cmd,
#                         env=env,
#                         rewrite_stdout_env=rewrite_env,
#                         cwd=src_dir,
#                         stats=build_stats,
#                     )
#                     utils.remove_pycache_from_scripts(m.config.host_prefix)
#         # if build_stats and not provision_only:
#         #     log_stats(build_stats, "building {}".format(m.name()))
#         #     if stats is not None:
#         #         stats[stats_key(m, 'build')] = build_stats

#     print("\n\n\n\n\n\nBUILD FINISHED, NOW BUNDLING")

#     prefix_file_list = join(m.config.build_folder, "prefix_files.txt")
#     initial_files = set()
#     if os.path.isfile(prefix_file_list):
#         with open(prefix_file_list) as f:
#             initial_files = set(f.read().splitlines())
#     new_prefix_files = utils.prefix_files(prefix=m.config.host_prefix) - initial_files

#     output = {}
#     output["files"] = new_prefix_files
#     # output['script'] = script
#     newly_built_packages = bundle_conda(output, m, env, stats)

#     # new_pkgs = default_return
#     # print("provision_only ", provision_only, "POST: ", post)
#     # if not provision_only and post in [True, None]:
#     #     outputs = output_metas or m.get_output_metadata_set(permit_unsatisfiable_variants=False)
#     #     print(outputs)
#     #     # import IPython; IPython.embed()
#     #     top_level_meta = m

#     #     # this is the old, default behavior: conda package, with difference between start
#     #     #    set of files and end set of files
#     #     prefix_file_list = join(m.config.build_folder, 'prefix_files.txt')
#     #     if os.path.isfile(prefix_file_list):
#     #         with open(prefix_file_list) as f:
#     #             initial_files = set(f.read().splitlines())
#     #     else:
#     #         initial_files = set()

#     #     # subdir needs to always be some real platform - so ignore noarch.
#     #     subdir = (m.config.host_subdir if m.config.host_subdir != 'noarch' else
#     #                 m.config.subdir)

#     #     with TemporaryDirectory() as prefix_files_backup:
#     #         # back up new prefix files, because we wipe the prefix before each output build
#     #         for f in new_prefix_files:
#     #             utils.copy_into(os.path.join(m.config.host_prefix, f),
#     #                             os.path.join(prefix_files_backup, f),
#     #                             symlinks=True)

#     #         # this is the inner loop, where we loop over any vars used only by
#     #         # outputs (not those used by the top-level recipe). The metadata
#     #         # objects here are created by the m.get_output_metadata_set, which
#     #         # is distributing the matrix of used variables.

#     #         for (output_d, m) in outputs:
#     #             if m.skip():
#     #                 print(utils.get_skip_message(m))
#     #                 continue

#     #             # TODO: should we check both host and build envs?  These are the same, except when
#     #             #    cross compiling
#     #             if m.config.skip_existing and is_package_built(m, 'host'):
#     #                 print(utils.get_skip_message(m))
#     #                 new_pkgs[bldpkg_path(m)] = output_d, m
#     #                 continue

#     #             if (top_level_meta.name() == output_d.get('name') and not (output_d.get('files') or
#     #                                                                        output_d.get('script'))):
#     #                 output_d['files'] = (utils.prefix_files(prefix=m.config.host_prefix) -
#     #                                      initial_files)

#     #             # ensure that packaging scripts are copied over into the workdir
#     #             if 'script' in output_d:
#     #                 utils.copy_into(os.path.join(m.path, output_d['script']), m.config.work_dir)

#     #             # same thing, for test scripts
#     #             test_script = output_d.get('test', {}).get('script')
#     #             if test_script:
#     #                 if not os.path.isfile(os.path.join(m.path, test_script)):
#     #                     raise ValueError("test script specified as {} does not exist.  Please "
#     #                                      "check for typos or create the file and try again."
#     #                                      .format(test_script))
#     #                 utils.copy_into(os.path.join(m.path, test_script),
#     #                                 os.path.join(m.config.work_dir, test_script))

#     #             assert output_d.get('type') != 'conda' or m.final, (
#     #                 "output metadata for {} is not finalized".format(m.dist()))
#     #             pkg_path = bldpkg_path(m)
#     #             if pkg_path not in built_packages and pkg_path not in new_pkgs:
#     #                 log.info("Packaging {}".format(m.name()))
#     #                 # for more than one output, we clear and rebuild the environment before each
#     #                 #    package.  We also do this for single outputs that present their own
#     #                 #    build reqs.
#     #                 if not (m.is_output or
#     #                         (os.path.isdir(m.config.host_prefix) and
#     #                          len(os.listdir(m.config.host_prefix)) <= 1)):
#     #                     # This log message contradicts both the not (m.is_output or ..) check above
#     #                     # and also the comment "For more than one output, ..."
#     #                     log.debug('Not creating new env for output - already exists from top-level')
#     #                 else:
#     #                     m.config._merge_build_host = m.build_is_host

#     #                     utils.rm_rf(m.config.host_prefix)
#     #                     utils.rm_rf(m.config.build_prefix)
#     #                     utils.rm_rf(m.config.test_prefix)

#     #                     host_ms_deps = m.ms_depends('host')
#     #                     sub_build_ms_deps = m.ms_depends('build')
#     #                     if m.is_cross and not m.build_is_host:
#     #                         host_actions = environ.get_install_actions(m.config.host_prefix,
#     #                                                 tuple(host_ms_deps), 'host',
#     #                                                 subdir=m.config.host_subdir,
#     #                                                 debug=m.config.debug,
#     #                                                 verbose=m.config.verbose,
#     #                                                 locking=m.config.locking,
#     #                                                 bldpkgs_dirs=tuple(m.config.bldpkgs_dirs),
#     #                                                 timeout=m.config.timeout,
#     #                                                 disable_pip=m.config.disable_pip,
#     #                                                 max_env_retry=m.config.max_env_retry,
#     #                                                 output_folder=m.config.output_folder,
#     #                                                 channel_urls=tuple(m.config.channel_urls))
#     #                         environ.create_env(m.config.host_prefix, host_actions, env='host',
#     #                                            config=m.config, subdir=subdir, is_cross=m.is_cross,
#     #                                            is_conda=m.name() == 'conda')
#     #                     else:
#     #                         # When not cross-compiling, the build deps aggregate 'build' and 'host'.
#     #                         sub_build_ms_deps.extend(host_ms_deps)
#     #                     build_actions = environ.get_install_actions(m.config.build_prefix,
#     #                                                 tuple(sub_build_ms_deps), 'build',
#     #                                                 subdir=m.config.build_subdir,
#     #                                                 debug=m.config.debug,
#     #                                                 verbose=m.config.verbose,
#     #                                                 locking=m.config.locking,
#     #                                                 bldpkgs_dirs=tuple(m.config.bldpkgs_dirs),
#     #                                                 timeout=m.config.timeout,
#     #                                                 disable_pip=m.config.disable_pip,
#     #                                                 max_env_retry=m.config.max_env_retry,
#     #                                                 output_folder=m.config.output_folder,
#     #                                                 channel_urls=tuple(m.config.channel_urls))
#     #                     environ.create_env(m.config.build_prefix, build_actions, env='build',
#     #                                        config=m.config, subdir=m.config.build_subdir,
#     #                                        is_cross=m.is_cross,
#     #                                        is_conda=m.name() == 'conda')

#     #                 to_remove = set()
#     #                 for f in output_d.get('files', []):
#     #                     if f.startswith('conda-meta'):
#     #                         to_remove.add(f)

#     #                 # This is wrong, files has not been expanded at this time and could contain
#     #                 # wildcards.  Also well, I just do not understand this, because when this
#     #                 # does contain wildcards, the files in to_remove will slip back in.
#     #                 if 'files' in output_d:
#     #                     output_d['files'] = set(output_d['files']) - to_remove

#     #                 # copies the backed-up new prefix files into the newly created host env
#     #                 for f in new_prefix_files:
#     #                     utils.copy_into(os.path.join(prefix_files_backup, f),
#     #                                     os.path.join(m.config.host_prefix, f),
#     #                                     symlinks=True)

#     #                 # we must refresh the environment variables because our env for each package
#     #                 #    can be different from the env for the top level build.
#     #                 with utils.path_prepended(m.config.build_prefix):
#     #                     env = environ.get_dict(m=m)
#     #                 pkg_type = 'conda' if not hasattr(m, 'type') else m.type
#     #                 newly_built_packages = bundlers[pkg_type](output_d, m, env, stats)
#     #                 # warn about overlapping files.
#     #                 if 'checksums' in output_d:
#     #                     for file, csum in output_d['checksums'].items():
#     #                         for _, prev_om in new_pkgs.items():
#     #                             prev_output_d, _ = prev_om
#     #                             if file in prev_output_d.get('checksums', {}):
#     #                                 prev_csum = prev_output_d['checksums'][file]
#     #                                 nature = 'Exact' if csum == prev_csum else 'Inexact'
#     #                                 log.warn("{} overlap between {} in packages {} and {}"
#     #                                          .format(nature, file, output_d['name'],
#     #                                                  prev_output_d['name']))
#     #                 for built_package in newly_built_packages:
#     #                     new_pkgs[built_package] = (output_d, m)

#     #                 # must rebuild index because conda has no way to incrementally add our last
#     #                 #    package to the index.

#     #                 subdir = ('noarch' if (m.noarch or m.noarch_python)
#     #                           else m.config.host_subdir)
#     #                 if m.is_cross:
#     #                     get_build_index(subdir=subdir, bldpkgs_dir=m.config.bldpkgs_dir,
#     #                                     output_folder=m.config.output_folder, channel_urls=m.config.channel_urls,
#     #                                     debug=m.config.debug, verbose=m.config.verbose, locking=m.config.locking,
#     #                                     timeout=m.config.timeout, clear_cache=True)
#     #                 get_build_index(subdir=subdir, bldpkgs_dir=m.config.bldpkgs_dir,
#     #                                 output_folder=m.config.output_folder, channel_urls=m.config.channel_urls,
#     #                                 debug=m.config.debug, verbose=m.config.verbose, locking=m.config.locking,
#     #                                 timeout=m.config.timeout, clear_cache=True)
#     # else:
#     #     if not provision_only:
#     #         print("STOPPING BUILD BEFORE POST:", m.dist())

#     # # return list of all package files emitted by this build
#     # return new_pkgs