# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

import subprocess
import tempfile

from boa.core.build import download_source

from rich.console import Console

console = Console()

patch_reference_dir = None


def create_patch(dir_a, dir_b):
    # create a patch file from dir_a to dir_b
    # ignoring conda files...
    git = False
    if git:
        exclude = [":(exclude)conda_build.sh", ":(exclude)build_env_setup.sh"]
        cmd = ["git", "diff", dir_a, dir_b] + exclude
    else:
        exclude = [".git", "conda_build.sh", "build_env_setup.sh"]
        exclude_args = [
            item for pair in zip(len(exclude) * ["-x"], exclude) for item in pair
        ]
        cmd = ["diff", "-uraN", dir_a, dir_b] + exclude_args

    console.print(f"[yellow]Calling: [/yellow] {' '.join(cmd)}")
    try:
        subprocess.check_output(cmd)
    except subprocess.CalledProcessError as exc:
        if exc.returncode == 1:
            # ah, actually all is well!
            output = exc.output.decode("utf-8", errors="ignore")
            output = output.replace(dir_a, "old")
            output = output.replace(dir_b, "new")
            return output
        if exc.returncode == 2:
            # ouch, 2 means trouble!
            raise exc
    else:
        return None


def create_reference_dir(meta):
    if hasattr(meta, "boa_patch_reference_dir"):
        return meta.boa_patch_reference_dir
    temp_dir = tempfile.mkdtemp()
    bkup = meta.config.croot
    meta.config.croot = temp_dir
    patch_reference_dir = meta.config.build_folder
    bkup_verbose = meta.config.verbose = False
    console.print("Preparing reference dir... this might take a while")
    download_source(meta)
    meta.config.verbose = bkup_verbose
    meta.config.croot = bkup
    console.print(f"Reference dir: {patch_reference_dir}\n")
    meta.boa_patch_reference_dir = patch_reference_dir
    return patch_reference_dir


if __name__ == "__main__":
    create_patch("/Users/wolfv/Programs/boa", "/Users/wolfv/Programs/boa2")
