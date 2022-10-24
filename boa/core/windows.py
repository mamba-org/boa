import os
import sys

from conda_build.utils import (
    check_call_env,
    path_prepended,
)
from conda_build.variants import set_language_env_vars
from conda_build.windows import fix_staged_scripts, write_build_scripts

from boa.core import environ


def build(m, bld_bat, stats, provision_only=False):
    with path_prepended(m.config.host_prefix):
        with path_prepended(m.config.build_prefix):
            env = environ.get_dict(m=m)
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
    #    See note above about inverted logic on "NO" variables
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

    # set variables like CONDA_PY in the test environment
    env.update(set_language_env_vars(m.config.variant))

    for name in "BIN", "INC", "LIB":
        path = env["LIBRARY_" + name]
        if not os.path.isdir(path):
            os.makedirs(path)

    work_script, env_script = write_build_scripts(m, env, bld_bat)

    if not provision_only and os.path.isfile(work_script):
        cmd = ["cmd.exe", "/d", "/c", os.path.basename(work_script)]
        # rewrite long paths in stdout back to their env variables
        if m.config.debug or m.config.no_rewrite_stdout_env:
            rewrite_env = None
        else:
            rewrite_env = {
                k: env[k] for k in ["PREFIX", "BUILD_PREFIX", "SRC_DIR"] if k in env
            }
            print(f"Rewriting env in output: {rewrite_env}", file=sys.stderr)
        check_call_env(
            cmd, cwd=m.config.work_dir, stats=stats, rewrite_stdout_env=rewrite_env
        )
        fix_staged_scripts(
            os.path.join(m.config.host_prefix, "Scripts"), config=m.config
        )
