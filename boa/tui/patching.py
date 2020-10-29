import subprocess
import tempfile

from boa.core.build import download_source

from rich.console import Console
from rich.syntax import Syntax

console = Console()

patch_reference_dir = None


def create_patch(dir_a, dir_b):
    # create a patch file from dir_a to dir_b
    # ignoring conda files...
    exclude = [".git", "conda_build.sh", "build_env_setup.sh"]

    exlude_args = [
        item for pair in zip(len(exclude) * ["-x"], exclude) for item in pair
    ]

    try:
        subprocess.check_output(["diff", "-uraN", dir_a, dir_b] + exlude_args)
    except subprocess.CalledProcessError as exc:
        if exc.returncode == 1:
            # ah, actually all is well!
            output = exc.output.decode("utf-8", errors="ignore")
            console.print(Syntax(output, "diff"))
        if exc.returncode == 2:
            # ouch, 2 means trouble!
            raise exc
    else:
        console.print("[red]No difference found![/red]")


def create_reference_dir(meta):
    temp_dir = tempfile.mkdtemp()
    bkup = meta.config.croot
    meta.config.croot = temp_dir
    patch_reference_dir = meta.config.build_folder
    download_source(meta)
    meta.config.croot = bkup
    console.print(f"[red]REFERENCE DIR: {patch_reference_dir}[/red]")
    return patch_reference_dir


if __name__ == "__main__":
    create_patch("/Users/wolfv/Programs/boa", "/Users/wolfv/Programs/boa2")
