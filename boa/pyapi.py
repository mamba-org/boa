from typing import Optional, List, Callable


import sys
from .core.monkeypatch import *
from .core.config import init_global_config
from ._version import __version__
from mamba.utils import init_api_context
import libmambapy as api

from conda_build.conda_interface import cc_conda_build


from types import SimpleNamespace

banner = r"""
           _
          | |__   ___   __ _
          | '_ \ / _ \ / _` |
          | |_) | (_) | (_| |
          |_.__/ \___/ \__,_|
"""


def py_build(
    recipe_dir: str,
    target: Optional[str] = None,
    features: Optional[str] = None,
    offline: bool = False,
    target_platform: Optional[str] = None,
    json: bool = False,
    debug: bool = False,
    variant_config_files=None,
    interactive: bool = False,
    output_folder: Optional[str] = None,
    skip_existing: Optional[str] = None,
    no_test: bool = False,
    continue_on_failure: bool = False,
    conda_build_build_id_pat: bool = False,
    conda_build_remove_work_dir: bool = True,
    conda_build_keep_old_work: bool = False,
    conda_build_prefix_length: int = 255,
    croot: bool = False,
    pkg_format: int = 1,
    zstd_compression_level: int = 22,
    post_build_callback: Optional[Callable] = None,
    add_pip_as_python_dependency: bool = False,
):

    if target is None:
        target = ""

    if variant_config_files is None:
        variant_config_files = []

    if output_folder is None:
        output_folder = cc_conda_build.get("output_folder")

    if skip_existing is None:
        skip_existing = "default"

    args = SimpleNamespace(
        recipe_dir=recipe_dir,
        target=target,
        features=features,
        offline=offline,
        target_platform=target_platform,
        json=json,
        debug=debug,
        variant_config_files=variant_config_files,
        interactive=interactive,
        output_folder=output_folder,
        skip_existing=skip_existing,
        no_test=no_test,
        continue_on_failure=continue_on_failure,
        conda_build_build_id_pat=conda_build_build_id_pat,
        conda_build_remove_work_dir=conda_build_remove_work_dir,
        conda_build_keep_old_work=conda_build_keep_old_work,
        conda_build_prefix_length=conda_build_prefix_length,
        croot=croot,
        pkg_format=pkg_format,
        zstd_compression_level=zstd_compression_level,
        post_build_callback=post_build_callback,
        command="build",
    )

    print("args", args)

    init_api_context()
    api_ctx = api.Context()
    api_ctx.add_pip_as_python_dependency = add_pip_as_python_dependency
    init_global_config(args)

    from boa.core.run_build import run_build

    run_build(args)
