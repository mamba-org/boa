import warnings
import os
import sys

from conda_build.environ import (
    conda_build_vars,
    python_vars,
    perl_vars,
    lua_vars,
    r_vars,
    system_vars,
    feature_list,
    LANGUAGES,
)
from conda_build.os_utils import external
from conda_build.environ import get_git_info, get_hg_build_info, verify_git_repo
from conda_build import utils


def meta_vars(meta, skip_build_id=False):
    d = {}
    for key, value in meta.get_value("build/script_env", {}).items():
        if not value:
            warnings.warn(
                f"The environment variable '{key}' is undefined.",
                UserWarning,
                stacklevel=1,
            )
        else:
            d[key] = value

    folder = meta.get_value("source/0/folder", "")
    repo_dir = os.path.join(meta.config.work_dir, folder)
    git_dir = os.path.join(repo_dir, ".git")
    hg_dir = os.path.join(repo_dir, ".hg")

    if not isinstance(git_dir, str):
        # On Windows, subprocess env can't handle unicode.
        git_dir = git_dir.encode(sys.getfilesystemencoding() or "utf-8")

    git_exe = external.find_executable("git", meta.config.build_prefix)
    if git_exe and os.path.exists(git_dir):
        # We set all 'source' metavars using the FIRST source entry in meta.yaml.
        git_url = meta.get_value("source/0/git_url")

        if os.path.exists(git_url):
            if sys.platform == "win32":
                git_url = utils.convert_unix_path_to_win(git_url)
            # If git_url is a relative path instead of a url, convert it to an abspath
            git_url = os.path.normpath(os.path.join(meta.path, git_url))

        _x = False

        if git_url:
            _x = verify_git_repo(
                git_exe,
                git_dir,
                git_url,
                meta.config.git_commits_since_tag,
                meta.config.debug,
                meta.get_value("source/0/git_rev", "HEAD"),
            )

        if _x or meta.get_value("source/0/path"):
            d.update(get_git_info(git_exe, git_dir, meta.config.debug))

    elif external.find_executable("hg", meta.config.build_prefix) and os.path.exists(
        hg_dir
    ):
        d.update(get_hg_build_info(hg_dir))

    # use `get_value` to prevent early exit while name is still unresolved during rendering
    d["PKG_NAME"] = meta.get_value("package/name")
    d["PKG_VERSION"] = meta.version()
    d["PKG_BUILDNUM"] = str(meta.build_number())
    if meta.final and not skip_build_id:
        d["PKG_BUILD_STRING"] = str(meta.build_id())
        d["PKG_HASH"] = meta.hash_dependencies()
    else:
        d["PKG_BUILD_STRING"] = "placeholder"
        d["PKG_HASH"] = "1234567"
    d["RECIPE_DIR"] = meta.path
    return d


def get_dict(
    m,
    prefix=None,
    for_env=True,
    skip_build_id=False,
    escape_backslash=False,
    variant=None,
):
    if not prefix:
        prefix = m.config.host_prefix

    m.config._merge_build_host = m.build_is_host

    # conda-build specific vars
    d = conda_build_vars(prefix, m.config)

    # languages
    d.update(python_vars(m, prefix, escape_backslash))
    d.update(perl_vars(m, prefix, escape_backslash))
    d.update(lua_vars(m, prefix, escape_backslash))
    d.update(r_vars(m, prefix, escape_backslash))

    if m:
        d.update(meta_vars(m, skip_build_id=skip_build_id))

    # system
    d.update(system_vars(d, m, prefix))

    # features
    d.update({feat.upper(): str(int(value)) for feat, value in feature_list})

    variant = variant or m.config.variant
    for k, v in variant.items():
        if not for_env or (k.upper() not in d and k.upper() not in LANGUAGES):
            d[k] = v
    return d
