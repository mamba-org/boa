import json
import logging
import os
import shutil
import subprocess
import sys
from conda.core.package_cache_data import PackageCacheData
import ruamel
from os.path import isdir, join

from mamba.mamba_api import PrefixData

from conda.gateways.disk.create import mkdir_p
from conda.base.context import context

from conda_build.utils import CONDA_PACKAGE_EXTENSIONS
from conda_build.build import (
    copy_test_source_files,
    create_info_files,
    get_all_replacements,
    log_stats,
)
from conda_build.conda_interface import (
    url_path,
    env_path_backup_var_exists,
    pkgs_dirs,
)
from conda_build.create_test import create_all_test_files
from conda_build.index import update_index
from conda_build.post import post_build
from conda_build.render import bldpkg_path, try_download
from conda_build.utils import shutil_move_more_retrying
from conda_build.variants import set_language_env_vars

from conda_build import environ, utils

from boa.core.utils import shell_path
from boa.core.recipe_output import Output
from boa.core.metadata import MetaData
from boa.core.solver import MambaSolver

log = logging.getLogger("boa")


def get_metadata(yml, config):
    with open(yml, "r") as fi:
        d = ruamel.yaml.safe_load(fi)
    o = Output(d, config)
    return MetaData(os.path.dirname(yml), o)


def _write_test_run_script(
    metadata,
    test_run_script,
    test_env_script,
    py_files,
    pl_files,
    lua_files,
    r_files,
    shell_files,
    trace,
):
    # log = utils.get_logger(__name__)
    with open(test_run_script, "w") as tf:
        tf.write(
            '{source} "{test_env_script}"\n'.format(
                source="call" if utils.on_win else "source",
                test_env_script=test_env_script,
            )
        )
        if utils.on_win:
            tf.write("IF %ERRORLEVEL% NEQ 0 exit /B 1\n")
        else:
            tf.write("set {trace}-e\n".format(trace=trace))
        if py_files:
            test_python = metadata.config.test_python
            # use pythonw for import tests when osx_is_app is set
            if metadata.get_value("build/osx_is_app") and sys.platform == "darwin":
                test_python = test_python + "w"
            tf.write(
                '"{python}" -s "{test_file}"\n'.format(
                    python=test_python,
                    test_file=join(metadata.config.test_dir, "run_test.py"),
                )
            )
            if utils.on_win:
                tf.write("IF %ERRORLEVEL% NEQ 0 exit /B 1\n")
        if pl_files:
            tf.write(
                '"{perl}" "{test_file}"\n'.format(
                    perl=metadata.config.perl_bin(
                        metadata.config.test_prefix, metadata.config.host_platform
                    ),
                    test_file=join(metadata.config.test_dir, "run_test.pl"),
                )
            )
            if utils.on_win:
                tf.write("IF %ERRORLEVEL% NEQ 0 exit /B 1\n")
        if lua_files:
            tf.write(
                '"{lua}" "{test_file}"\n'.format(
                    lua=metadata.config.lua_bin(
                        metadata.config.test_prefix, metadata.config.host_platform
                    ),
                    test_file=join(metadata.config.test_dir, "run_test.lua"),
                )
            )
            if utils.on_win:
                tf.write("IF %ERRORLEVEL% NEQ 0 exit /B 1\n")
        if r_files:
            tf.write(
                '"{r}" "{test_file}"\n'.format(
                    r=metadata.config.rscript_bin(
                        metadata.config.test_prefix, metadata.config.host_platform
                    ),
                    test_file=join(metadata.config.test_dir, "run_test.r"),
                )
            )
            if utils.on_win:
                tf.write("IF %ERRORLEVEL% NEQ 0 exit /B 1\n")
        if shell_files:
            for shell_file in shell_files:
                if utils.on_win:
                    if os.path.splitext(shell_file)[1] == ".bat":
                        tf.write('call "{test_file}"\n'.format(test_file=shell_file))
                        tf.write("IF %ERRORLEVEL% NEQ 0 exit /B 1\n")
                    else:
                        log.warn(
                            "Found sh test file on windows.  Ignoring this for now (PRs welcome)"
                        )
                elif os.path.splitext(shell_file)[1] == ".sh":
                    # TODO: Run the test/commands here instead of in run_test.py
                    tf.write(
                        '"{shell_path}" {trace}-e "{test_file}"\n'.format(
                            shell_path=shell_path, test_file=shell_file, trace=trace
                        )
                    )


def write_test_scripts(
    metadata, env_vars, py_files, pl_files, lua_files, r_files, shell_files, trace=""
):
    if not metadata.config.activate or metadata.name() == "conda":
        # prepend bin (or Scripts) directory
        env_vars = utils.prepend_bin_path(
            env_vars, metadata.config.test_prefix, prepend_prefix=True
        )
        if utils.on_win:
            env_vars["PATH"] = (
                metadata.config.test_prefix + os.pathsep + env_vars["PATH"]
            )

    # set variables like CONDA_PY in the test environment
    env_vars.update(set_language_env_vars(metadata.config.variant))

    # Python 2 Windows requires that envs variables be string, not unicode
    env_vars = {str(key): str(value) for key, value in env_vars.items()}
    suffix = "bat" if utils.on_win else "sh"
    test_env_script = join(
        metadata.config.test_dir, "conda_test_env_vars.{suffix}".format(suffix=suffix)
    )
    test_run_script = join(
        metadata.config.test_dir, "conda_test_runner.{suffix}".format(suffix=suffix)
    )

    with open(test_env_script, "w") as tf:
        if not utils.on_win:
            tf.write("set {trace}-e\n".format(trace=trace))
        if metadata.config.activate and not metadata.name() == "conda":
            ext = ".bat" if utils.on_win else ""
            tf.write(
                '{source} "{conda_root}activate{ext}" "{test_env}"\n'.format(
                    conda_root=utils.root_script_dir + os.path.sep,
                    source="call" if utils.on_win else "source",
                    ext=ext,
                    test_env=metadata.config.test_prefix,
                )
            )
            if utils.on_win:
                tf.write("IF %ERRORLEVEL% NEQ 0 exit /B 1\n")
        # In-case people source this, it's essential errors are not fatal in an interactive shell.
        if not utils.on_win:
            tf.write("set +e\n")

    _write_test_run_script(
        metadata,
        test_run_script,
        test_env_script,
        py_files,
        pl_files,
        lua_files,
        r_files,
        shell_files,
        trace,
    )
    return test_run_script, test_env_script


def _extract_test_files_from_package(metadata):
    recipe_dir = (
        metadata.config.recipe_dir
        if hasattr(metadata.config, "recipe_dir")
        else metadata.path
    )
    if recipe_dir:
        info_dir = os.path.normpath(os.path.join(recipe_dir, "info"))
        test_files = os.path.join(info_dir, "test")
        if os.path.exists(test_files) and os.path.isdir(test_files):
            # things are re-extracted into the test dir because that's cwd when tests are run,
            #    and provides the most intuitive experience. This is a little
            #    tricky, because SRC_DIR still needs to point at the original
            #    work_dir, for legacy behavior where people aren't using
            #    test/source_files. It would be better to change SRC_DIR in
            #    test phase to always point to test_dir. Maybe one day.
            utils.copy_into(
                test_files,
                metadata.config.test_dir,
                metadata.config.timeout,
                symlinks=True,
                locking=metadata.config.locking,
                clobber=True,
            )
            dependencies_file = os.path.join(test_files, "test_time_dependencies.json")
            test_deps = []
            if os.path.isfile(dependencies_file):
                with open(dependencies_file) as f:
                    test_deps = json.load(f)
            test_section = metadata.meta.get("test", {})
            test_section["requires"] = test_deps
            metadata.meta["test"] = test_section

        else:
            if metadata.meta.get("test", {}).get("source_files"):
                if not metadata.source_provided:
                    try_download(metadata, no_download_source=False)


def _construct_metadata_for_test_from_package(package, config):
    recipe_dir, need_cleanup = utils.get_recipe_abspath(package)
    config.need_cleanup = need_cleanup
    config.recipe_dir = recipe_dir
    hash_input = {}

    info_dir = os.path.normpath(os.path.join(recipe_dir, "info"))
    with open(os.path.join(info_dir, "index.json")) as f:
        package_data = json.load(f)

    if package_data["subdir"] != "noarch":
        config.host_subdir = package_data["subdir"]
    # We may be testing an (old) package built without filename hashing.
    hash_input = os.path.join(info_dir, "hash_input.json")
    if os.path.isfile(hash_input):
        with open(os.path.join(info_dir, "hash_input.json")) as f:
            hash_input = json.load(f)
    else:
        config.filename_hashing = False
        hash_input = {}
    # not actually used as a variant, since metadata will have been finalized.
    #    This is still necessary for computing the hash correctly though
    config.variant = hash_input
    log = utils.get_logger(__name__)

    # get absolute file location
    local_pkg_location = os.path.normpath(os.path.abspath(os.path.dirname(package)))

    # get last part of the path
    last_element = os.path.basename(local_pkg_location)
    is_channel = False
    for platform in ("win-", "linux-", "osx-", "noarch"):
        if last_element.startswith(platform):
            is_channel = True

    if not is_channel:
        log.warn(
            "Copying package to conda-build croot.  No packages otherwise alongside yours will"
            " be available unless you specify -c local.  To avoid this warning, your package "
            "must reside in a channel structure with platform-subfolders.  See more info on "
            "what a valid channel is at "
            "https://conda.io/docs/user-guide/tasks/create-custom-channels.html"
        )

        local_dir = os.path.join(config.croot, config.host_subdir)
        mkdir_p(local_dir)
        local_pkg_location = os.path.join(local_dir, os.path.basename(package))
        utils.copy_into(package, local_pkg_location)
        local_pkg_location = local_dir

    local_channel = os.path.dirname(local_pkg_location)

    # update indices in the channel
    update_index(local_channel, verbose=config.debug, threads=1)

    try:
        # raise IOError()
        # metadata = render_recipe(
        #     os.path.join(info_dir, "recipe"), config=config, reset_build_id=False
        # )[0][0]

        metadata = get_metadata(os.path.join(info_dir, "recipe", "recipe.yaml"), config)
        # with open(os.path.join(info_dir, "recipe", "recipe.yaml")) as fi:
        # metadata = yaml.load(fi)
    # no recipe in package.  Fudge metadata
    except SystemExit:
        # force the build string to line up - recomputing it would
        #    yield a different result
        metadata = MetaData.fromdict(
            {
                "package": {
                    "name": package_data["name"],
                    "version": package_data["version"],
                },
                "build": {
                    "number": int(package_data["build_number"]),
                    "string": package_data["build"],
                },
                "requirements": {"run": package_data["depends"]},
            },
            config=config,
        )
    # HACK: because the recipe is fully baked, detecting "used" variables no longer works.  The set
    #     of variables in the hash_input suffices, though.

    if metadata.noarch:
        metadata.config.variant["target_platform"] = "noarch"

    metadata.config.used_vars = list(hash_input.keys())
    urls = list(utils.ensure_list(metadata.config.channel_urls))
    local_path = url_path(local_channel)
    # replace local with the appropriate real channel.  Order is maintained.
    urls = [url if url != "local" else local_path for url in urls]
    if local_path not in urls:
        urls.insert(0, local_path)
    metadata.config.channel_urls = urls
    utils.rm_rf(metadata.config.test_dir)
    return metadata, hash_input


def construct_metadata_for_test(recipedir_or_package, config):
    if (
        os.path.isdir(recipedir_or_package)
        or os.path.basename(recipedir_or_package) == "meta.yaml"
    ):
        raise NotImplementedError("Not yet implemented.")
        # m, hash_input = _construct_metadata_for_test_from_recipe(
        #     recipedir_or_package, config
        # )
    else:
        m, hash_input = _construct_metadata_for_test_from_package(
            recipedir_or_package, config
        )
    return m, hash_input


def run_test(
    recipedir_or_package_or_metadata,
    config,
    stats,
    move_broken=True,
    provision_only=False,
    solver=None,
):
    """
    Execute any test scripts for the given package.

    :param m: Package's metadata.
    :type m: Metadata
    """

    # we want to know if we're dealing with package input.  If so, we can move the input on success.
    hash_input = {}

    # store this name to keep it consistent.  By changing files, we change the hash later.
    #    It matches the build hash now, so let's keep it around.
    test_package_name = (
        recipedir_or_package_or_metadata.dist()
        if hasattr(recipedir_or_package_or_metadata, "dist")
        else recipedir_or_package_or_metadata
    )

    if not provision_only:
        print("TEST START:", test_package_name)

    if hasattr(recipedir_or_package_or_metadata, "config"):
        metadata = recipedir_or_package_or_metadata
        utils.rm_rf(metadata.config.test_dir)
    else:
        metadata, hash_input = construct_metadata_for_test(
            recipedir_or_package_or_metadata, config
        )

    trace = "-x " if metadata.config.debug else ""

    # Must download *after* computing build id, or else computing build id will change
    #     folder destination
    _extract_test_files_from_package(metadata)

    # When testing a .tar.bz2 in the pkgs dir, clean_pkg_cache() will remove it.
    # Prevent this. When https://github.com/conda/conda/issues/5708 gets fixed
    # I think we can remove this call to clean_pkg_cache().
    in_pkg_cache = (
        not hasattr(recipedir_or_package_or_metadata, "config")
        and os.path.isfile(recipedir_or_package_or_metadata)
        and recipedir_or_package_or_metadata.endswith(CONDA_PACKAGE_EXTENSIONS)
        and os.path.dirname(recipedir_or_package_or_metadata) in pkgs_dirs[0]
    )
    if not in_pkg_cache:
        environ.clean_pkg_cache(metadata.dist(), metadata.config)

    copy_test_source_files(metadata, metadata.config.test_dir)
    # this is also copying tests/source_files from work_dir to testing workdir

    _, pl_files, py_files, r_files, lua_files, shell_files = create_all_test_files(
        metadata
    )

    if (
        not any([py_files, shell_files, pl_files, lua_files, r_files])
        and not metadata.config.test_run_post
    ):
        print("Nothing to test for:", test_package_name)
        return True

    if metadata.config.remove_work_dir:
        for name, prefix in (
            ("host", metadata.config.host_prefix),
            ("build", metadata.config.build_prefix),
        ):
            if os.path.isdir(prefix):
                # move host folder to force hardcoded paths to host env to break during tests
                #    (so that they can be properly addressed by recipe author)
                dest = os.path.join(
                    os.path.dirname(prefix),
                    "_".join(
                        (
                            "%s_prefix_moved" % name,
                            metadata.dist(),
                            getattr(metadata.config, "%s_subdir" % name),
                        )
                    ),
                )
                # Needs to come after create_files in case there's test/source_files
                shutil_move_more_retrying(prefix, dest, "{} prefix".format(prefix))

        # nested if so that there's no warning when we just leave the empty workdir in place
        if metadata.source_provided:
            dest = os.path.join(
                os.path.dirname(metadata.config.work_dir),
                "_".join(("work_moved", metadata.dist(), metadata.config.host_subdir)),
            )
            # Needs to come after create_files in case there's test/source_files
            shutil_move_more_retrying(config.work_dir, dest, "work")
    else:
        log.warn(
            "Not moving work directory after build.  Your package may depend on files "
            "in the work directory that are not included with your package"
        )

    # looks like a dead function to me
    # get_build_metadata(metadata)

    specs = metadata.get_test_deps(py_files, pl_files, lua_files, r_files)

    with utils.path_prepended(metadata.config.test_prefix):
        env = dict(os.environ.copy())
        env.update(environ.get_dict(m=metadata, prefix=config.test_prefix))
        env["CONDA_BUILD_STATE"] = "TEST"
        env["CONDA_BUILD"] = "1"
        if env_path_backup_var_exists:
            env["CONDA_PATH_BACKUP"] = os.environ["CONDA_PATH_BACKUP"]

    if not metadata.config.activate or metadata.name() == "conda":
        # prepend bin (or Scripts) directory
        env = utils.prepend_bin_path(
            env, metadata.config.test_prefix, prepend_prefix=True
        )

    if utils.on_win:
        env["PATH"] = metadata.config.test_prefix + os.pathsep + env["PATH"]

    env["PREFIX"] = metadata.config.test_prefix
    if "BUILD_PREFIX" in env:
        del env["BUILD_PREFIX"]

    # In the future, we will need to support testing cross compiled
    #     packages on physical hardware. until then it is expected that
    #     something like QEMU or Wine will be used on the build machine,
    #     therefore, for now, we use host_subdir.

    # ensure that the test prefix isn't kept between variants
    utils.rm_rf(metadata.config.test_prefix)

    if solver is None:
        solver = MambaSolver([], context.subdir)

    solver.replace_channels()
    transaction = solver.solve(specs, "")

    downloaded = transaction.fetch_extract_packages(
        PackageCacheData.first_writable().pkgs_dir,
        solver.repos + list(solver.local_repos.values()),
    )
    if not downloaded:
        raise RuntimeError("Did not succeed in downloading packages.")

    mkdir_p(metadata.config.test_prefix)
    transaction.execute(
        PrefixData(metadata.config.test_prefix),
        PackageCacheData.first_writable().pkgs_dir,
    )

    with utils.path_prepended(metadata.config.test_prefix):
        env = dict(os.environ.copy())
        env.update(environ.get_dict(m=metadata, prefix=metadata.config.test_prefix))
        env["CONDA_BUILD_STATE"] = "TEST"
        if env_path_backup_var_exists:
            env["CONDA_PATH_BACKUP"] = os.environ["CONDA_PATH_BACKUP"]

    if config.test_run_post:
        from conda_build.utils import get_installed_packages

        installed = get_installed_packages(metadata.config.test_prefix)
        files = installed[metadata.meta["package"]["name"]]["files"]
        replacements = get_all_replacements(metadata.config)
        try_download(metadata, False, True)
        create_info_files(metadata, replacements, files, metadata.config.test_prefix)
        post_build(metadata, files, None, metadata.config.test_prefix, True)

    # when workdir is removed, the source files are unavailable.  There's the test/source_files
    #    entry that lets people keep these files around.  The files are copied into test_dir for
    #    intuitive relative path behavior, though, not work_dir, so we need to adjust where
    #    SRC_DIR points.  The initial CWD during tests is test_dir.
    if metadata.config.remove_work_dir:
        env["SRC_DIR"] = metadata.config.test_dir

    test_script, _ = write_test_scripts(
        metadata, env, py_files, pl_files, lua_files, r_files, shell_files, trace
    )

    if utils.on_win:
        cmd = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", test_script]
    else:
        cmd = (
            [shell_path]
            + (["-x"] if metadata.config.debug else [])
            + ["-o", "errexit", test_script]
        )
    try:
        test_stats = {}
        if not provision_only:
            # rewrite long paths in stdout back to their env variables
            if metadata.config.debug or metadata.config.no_rewrite_stdout_env:
                rewrite_env = None
            else:
                rewrite_env = {k: env[k] for k in ["PREFIX", "SRC_DIR"] if k in env}
                if metadata.config.verbose:
                    for k, v in rewrite_env.items():
                        print(
                            "{0} {1}={2}".format(
                                "set" if test_script.endswith(".bat") else "export",
                                k,
                                v,
                            )
                        )
            utils.check_call_env(
                cmd,
                env=env,
                cwd=metadata.config.test_dir,
                stats=test_stats,
                rewrite_stdout_env=rewrite_env,
            )
            log_stats(test_stats, "testing {}".format(metadata.name()))
            # TODO need to implement metadata.get_used_loop_vars
            # if stats is not None and metadata.config.variants:
            #     stats[
            #         stats_key(metadata, "test_{}".format(metadata.name()))
            #     ] = test_stats
            if os.path.exists(join(metadata.config.test_dir, "TEST_FAILED")):
                raise subprocess.CalledProcessError(-1, "")
            print("TEST END:", test_package_name)

    except subprocess.CalledProcessError as _:  # noqa
        tests_failed(
            metadata,
            move_broken=move_broken,
            broken_dir=metadata.config.broken_dir,
            config=metadata.config,
        )
        raise

    if config.need_cleanup and config.recipe_dir is not None and not provision_only:
        utils.rm_rf(config.recipe_dir)

    return True


def tests_failed(package_or_metadata, move_broken, broken_dir, config):
    """
    Causes conda to exit if any of the given package's tests failed.

    :param m: Package's metadata
    :type m: Metadata
    """
    if not isdir(broken_dir):
        os.makedirs(broken_dir)

    if hasattr(package_or_metadata, "config"):
        pkg = bldpkg_path(package_or_metadata)
    else:
        pkg = package_or_metadata
    dest = join(broken_dir, os.path.basename(pkg))

    if move_broken:
        log = utils.get_logger(__name__)
        try:
            shutil.move(pkg, dest)
            log.warn(
                "Tests failed for %s - moving package to %s"
                % (os.path.basename(pkg), broken_dir)
            )
        except OSError:
            pass
        update_index(
            os.path.dirname(os.path.dirname(pkg)), verbose=config.debug, threads=1
        )
    sys.exit("TESTS FAILED: " + os.path.basename(pkg))
