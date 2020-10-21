"""
Module that does most of the heavy lifting for the ``conda build`` command.
"""
from __future__ import absolute_import, division, print_function

import fnmatch
import io
import os
from os.path import isdir, isfile, join
import shutil
import sys
import pathlib
import subprocess

# this is to compensate for a requests idna encoding error.  Conda is a better place to fix,
#   eventually
# exception is raises: "LookupError: unknown encoding: idna"
#    http://stackoverflow.com/a/13057751/1170370
import encodings.idna  # NOQA

import conda_package_handling.api

# used to get version
from conda_build.conda_interface import env_path_backup_var_exists, TemporaryDirectory
from conda_build.utils import tmp_chdir

from conda_build import environ, source, utils
from conda_build.index import update_index
from conda_build.render import try_download
from conda_build.post import (
    post_process,
    post_build,
    fix_permissions,
    get_build_metadata,
)

from conda_build.exceptions import indent

import conda_build.noarch_python as noarch_python

if sys.platform == "win32":
    import conda_build.windows as windows

if "bsd" in sys.platform:
    shell_path = "/bin/sh"
elif utils.on_win:
    shell_path = "bash"
else:
    shell_path = "/bin/bash"


from conda_build.build import (
    _write_sh_activation_text,
    copy_readme,
    copy_license,
    copy_recipe_log,
    write_hash_input,
    get_files_with_prefix,
    record_prefix_files,
    write_info_files_file,
    write_link_json,
    write_about_json,
    write_info_json,
    get_entry_point_script_names,
    write_run_exports,
    create_info_files_json_v1,
)

from rich.console import Console

console = Console()


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

    # TODO
    # copy_recipe(m)
    copy_readme(m)
    copy_license(m)
    copy_recipe_log(m)
    # files.extend(jsonify_info_yamls(m))

    # create_all_test_files(m, test_dir=join(m.config.info_dir, 'test'))
    # if m.config.copy_test_source_files:
    #     copy_test_source_files(m, join(m.config.info_dir, 'test'))

    write_info_files_file(m, files)

    files_with_prefix = get_files_with_prefix(m, [], files, prefix)
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


def select_files(files, include_files, exclude_files):
    to_include, to_exclude = set(), set()
    if include_files:
        for f in include_files:
            to_include |= set(fnmatch.filter(files, f))
    else:
        to_include = set(files)
    if exclude_files:
        for f in exclude_files:
            to_exclude |= set(fnmatch.filter(to_include, f))

    final_files = to_include - to_exclude
    return final_files


def bundle_conda(metadata, initial_files, env, files_selector=None):

    files = post_process_files(metadata, initial_files)

    # first filter is so that info_files does not pick up ignored files
    files = utils.filter_files(files, prefix=metadata.config.host_prefix)
    if files_selector:
        files = select_files(
            files, files_selector.get("include"), files_selector.get("exclude")
        )

    console.print(
        f"\nAdding files for {metadata.name()}\n{'=' * (len(metadata.name()) + 20)}\n"
    )
    for f in sorted(files):
        console.print(f"- {f}")
    console.print("\n")

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
    if files_selector:
        include_files = files_selector.get("include")
        if include_files:
            include_files += ["info/*"]
        files = select_files(files, include_files, files_selector.get("exclude"))

    basename = metadata.dist()
    tmp_archives = []
    final_outputs = []
    ext = ".tar.bz2"
    if output.get("type") == "conda_v2" or metadata.config.conda_pkg_format == "2":
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

            # disable locking here. It's just a temp folder getting locked.
            # Having it proved a major bottleneck.
            utils.copy_into(
                tmp_path, final_output, metadata.config.timeout, locking=False
            )
            final_outputs.append(final_output)

    update_index(
        os.path.dirname(output_folder), verbose=metadata.config.debug, threads=1
    )

    # clean out host prefix so that this output's files don't interfere with other outputs
    # We have a backup of how things were before any output scripts ran.  That's
    # restored elsewhere.
    if metadata.config.keep_old_work:
        prefix = metadata.config.host_prefix
        dest = os.path.join(
            os.path.dirname(prefix),
            "_".join(("_h_env_moved", metadata.dist(), metadata.config.host_subdir)),
        )
        console.print("Renaming host env directory, ", prefix, " to ", dest)
        if os.path.exists(dest):
            utils.rm_rf(dest)
        shutil.move(prefix, dest)
    else:
        utils.rm_rf(metadata.config.host_prefix)

    return final_outputs


def write_build_scripts(m, script, build_file):

    with utils.path_prepended(m.config.host_prefix):
        with utils.path_prepended(m.config.build_prefix):
            env = environ.get_dict(m=m, variant={"no": "variant"})

    env.update(m.build_features())

    env["CONDA_BUILD_STATE"] = "BUILD"

    # hard-code this because we never want pip's build isolation
    #    https://github.com/conda/conda-build/pull/2972#discussion_r198290241
    #
    # Note that pip env "NO" variables are inverted logic.
    #      PIP_NO_BUILD_ISOLATION=False means don't use build isolation.
    #
    env["PIP_NO_BUILD_ISOLATION"] = "False"
    # some other env vars to have pip ignore dependencies.
    # we supply them ourselves instead.
    env["PIP_NO_DEPENDENCIES"] = True
    env["PIP_IGNORE_INSTALLED"] = True
    # pip's cache directory (PIP_NO_CACHE_DIR) should not be
    # disabled as this results in .egg-info rather than
    # .dist-info directories being created, see gh-3094

    # set PIP_CACHE_DIR to a path in the work dir that does not exist.
    env["PIP_CACHE_DIR"] = m.config.pip_cache_dir

    # tell pip to not get anything from PyPI, please.  We have everything we need
    # locally, and if we don't, it's a problem.
    env["PIP_NO_INDEX"] = True

    if m.noarch == "python":
        env["PYTHONDONTWRITEBYTECODE"] = True

    work_file = join(m.config.work_dir, "conda_build.sh")
    env_file = join(m.config.work_dir, "build_env_setup.sh")

    with open(env_file, "w") as bf:
        for k, v in env.items():
            if v != "" and v is not None:
                bf.write('export {0}="{1}"\n'.format(k, v))
                # console.print('export {0}="{1}"\n'.format(k, v))

        if m.activate_build_script:
            _write_sh_activation_text(bf, m)

        # add the feature function
        bf.write(
            """
function feature()
{
    if [[ $1 != "0" ]]
    then
        echo $2
    else
        echo $3
    fi
}
"""
        )

    with open(work_file, "w") as bf:
        # bf.write('set -ex\n')
        bf.write("if [ -z ${CONDA_BUILD+x} ]; then\n")
        bf.write("    source {}\n".format(env_file))
        bf.write("fi\n")

        if isfile(build_file):
            bf.write(open(build_file).read())
        elif script:
            bf.write(script)

    os.chmod(work_file, 0o766)
    return work_file, env_file


def execute_build_script(m, src_dir, env, provision_only=False):

    script = utils.ensure_list(m.get_value("build/script", None))
    if script:
        script = "\n".join(script)

    if not m.output.is_first and not script:
        console.print("No build script found and not top-level build")
        return

    if isdir(src_dir):
        build_stats = {}
        if utils.on_win:
            build_file = join(m.path, "bld.bat")
            if isfile(build_file) or script:
                if isinstance(script, str) and script.endswith(".bat"):
                    build_file = os.path.join(m.path, script)
            windows.build(
                m, build_file, stats=build_stats, provision_only=provision_only
            )
        else:
            build_file = join(m.path, "build.sh")
            # if isfile(build_file) and script:
            #     raise CondaBuildException(
            #         "Found a build.sh script and a build/script section "
            #         "inside meta.yaml. Either remove the build.sh script "
            #         "or remove the build/script section in meta.yaml."
            #     )
            # There is no sense in trying to run an empty build script.
            if isfile(build_file) or script:
                if isinstance(script, str) and script.endswith(".sh"):
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
                            console.print(
                                "{0} {1}={2}".format(
                                    "set" if build_file.endswith(".bat") else "export",
                                    k,
                                    v,
                                )
                            )

                    # clear this, so that the activate script will get run as necessary
                    del env["CONDA_BUILD"]
                    env["PKG_NAME"] = m.get_value("package/name")

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
        try_download(m, no_download_source=False, raise_error=False)


def build(m, stats=None):
    try:
        if not stats:
            stats = {}

        if m.skip():
            console.print(utils.get_skip_message(m))
            return {}

        with utils.path_prepended(m.config.build_prefix):
            env = environ.get_dict(m=m)

        env["CONDA_BUILD_STATE"] = "BUILD"
        if env_path_backup_var_exists:
            env["CONDA_PATH_BACKUP"] = os.environ["CONDA_PATH_BACKUP"]

        m.output.sections["package"]["name"] = m.output.name
        env["PKG_NAME"] = m.get_value("package/name")

        src_dir = m.config.work_dir
        if isdir(src_dir):
            if m.config.verbose:
                console.print("source tree in:", src_dir)
        else:
            if m.config.verbose:
                console.print("no source - creating empty work folder")
            os.makedirs(src_dir)

        utils.rm_rf(m.config.info_dir)
        files_before_script = utils.prefix_files(prefix=m.config.host_prefix)

        with open(join(m.config.build_folder, "prefix_files.txt"), "w") as f:
            f.write("\n".join(sorted(list(files_before_script))))
            f.write("\n")

        execute_build_script(m, src_dir, env)

        if m.output.sections["build"].get("intermediate"):
            utils.rm_rf(m.config.host_prefix)
            return

        bundle_conda(m, files_before_script, env, m.output.sections["files"])
    except subprocess.CalledProcessError:
        console.print("[red]BUILD ERROR: [/red]", sys.exc_info()[1])

        ext = "bat" if utils.on_win else "sh"
        build_cmd = str(
            pathlib.Path(m.config.build_prefix).parent / "work" / f"conda_build.{ext}"
        )
        console.print(f"Try building again with {build_cmd}")

        exit(1)
