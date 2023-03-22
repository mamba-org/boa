import pathlib
from subprocess import check_call
import sys
import tarfile
import json
import os

from pathlib import Path

import pytest


recipes_dir = pathlib.Path(__file__).parent / "recipes-v2"
tests_dir = pathlib.Path(__file__).parent / "tests-v2"


def test_build_recipes():
    recipes = [str(x) for x in recipes_dir.iterdir() if x.is_dir()]
    for recipe in recipes:
        check_call(["boa", "build", recipe])


def test_build_notest():
    recipes = [str(x) for x in recipes_dir.iterdir() if x.is_dir()]
    recipe = recipes[0]
    check_call(["boa", "build", recipe, "--no-test"])


def test_run_exports(tmp_path: Path):
    recipe = tests_dir / "runexports"
    check_call(["boa", "build", str(recipe), "--output-folder", str(tmp_path)])

    rex_a = next(tmp_path.rglob("**/rex-a*.tar.bz2"))

    with tarfile.open(rex_a) as fin:
        rexport = json.load(fin.extractfile("info/run_exports.json"))
        assert rexport["weak"]
        assert "strong" not in rexport
        assert rexport["weak"] == ["rex-exporter 0.1.*"]

    rex_b = next(tmp_path.rglob("**/rex-b*.tar.bz2"))

    with tarfile.open(rex_b) as fin:
        rexport = json.load(fin.extractfile("info/run_exports.json"))
        assert rexport["weak"]
        assert rexport["weak"] == ["rex-a 0.1.0.*"]
        assert rexport["strong"]
        assert rexport["strong"] == ["rex-exporter 0.1.*"]

    rexporter = next(tmp_path.rglob("**/rex-exporter*.tar.bz2"))
    with tarfile.open(rexporter) as fin:
        names = [x.name for x in fin.getmembers()]
        print(names)
        assert "info/run_exports.json" not in names


@pytest.mark.skipif(sys.platform == "win32", reason="No pytorch on Windows")
def test_build_with_channel_pins(tmp_path: Path):
    # Ensure that channel pins round trip correctly
    recipe = tests_dir / "metapackage-channel-pin"
    check_call(["boa", "build", str(recipe), "--output-folder", str(tmp_path)])

    channel_pins = next(tmp_path.rglob("**/metapackage-channel-pin*.tar.bz2"))

    with tarfile.open(channel_pins) as fin:
        info = json.load(fin.extractfile("info/index.json"))
        assert "conda-forge::pytorch" in info["depends"]


def test_build_with_script_env(tmp_path: Path):
    # Ensure that channel pins round trip correctly
    recipe = recipes_dir / "environ"
    os.environ["KEY1"] = "KEY1_RANDOM_VALUE"
    check_call(["boa", "build", str(recipe), "--output-folder", str(tmp_path)])

    result = next(tmp_path.rglob("**/test_environ*.tar.bz2"))

    with tarfile.open(result) as fin:
        key1 = fin.extractfile("key1.txt").read().decode("utf8").strip()
        assert key1 == "KEY1_RANDOM_VALUE"
        key2 = fin.extractfile("key2.txt").read().decode("utf8").strip()
        assert key2 == "JUST A VALUE"
