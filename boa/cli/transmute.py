# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

from glob import glob
import os
from pathlib import Path
from math import log
from libmambapy import transmute as mamba_transmute
from joblib import Parallel, delayed

from rich.console import Console

console = Console()

unit_list = list(zip(["bytes", "kB", "MB", "GB", "TB", "PB"], [0, 0, 1, 2, 2, 2]))


def sizeof_fmt(num):
    """Human friendly file size"""
    if num > 1:
        exponent = min(int(log(num, 1024)), len(unit_list) - 1)
        quotient = float(num) / 1024**exponent
        unit, num_decimals = unit_list[exponent]
        format_string = "{:.%sf} {}" % (num_decimals)
        return format_string.format(quotient, unit)
    if num == 0:
        return "0 bytes"
    if num == 1:
        return "1 byte"


def transmute_task(f, args):
    filename = os.path.basename(f)
    outpath = os.path.abspath(args.output_directory)

    if f.endswith(".tar.bz2"):
        filename = filename[:-8]
        outfile = os.path.join(outpath, filename + ".conda")
    elif f.endswith(".conda"):
        filename = filename[:-6]
        outfile = os.path.join(outpath, filename + ".tar.bz2")
    else:
        console.print("[bold red]Transmute can only handle .tar.bz2 and .conda formats")

    console.print(f"Processing {filename}")
    mamba_transmute(f, outfile, args.compression_level)

    stat_before = Path(f).stat()
    stat_after = Path(outfile).stat()

    saved_percent = 1.0 - (stat_after.st_size / stat_before.st_size)
    color = "[bold green]" if saved_percent > 0 else "[bold red]"

    return filename, outfile, stat_before, stat_after, saved_percent, color


def main(args):
    # from libmambapy import Context
    # api_ctx = Context()
    # api_ctx.set_verbosity(1)

    files = args.files
    final_files = []

    if not os.path.exists(args.output_directory):
        Path(args.output_directory).mkdir(parents=True, exist_ok=True)

    for f in files:
        final_files += [os.path.abspath(fx) for fx in glob(f)]

    logs = Parallel(n_jobs=args.num_jobs)(
        delayed(transmute_task)(f, args) for f in final_files
    )

    for filename, outfile, stat_before, stat_after, saved_percent, color in logs:
        console.print(f"\nConverting [bold]{filename}")
        console.print(f"Done: [bold]{outfile}")
        console.print(f"   Before    : {sizeof_fmt(stat_before.st_size)}")
        console.print(f"   After     : {sizeof_fmt(stat_after.st_size)}")
        console.print(f"   Difference: {color}{saved_percent * 100:.2f}%")
