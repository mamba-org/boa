import pathlib
from subprocess import check_call
import tempfile
import tarfile
import json

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


def test_run_exports():
    recipe = tests_dir / "runexports"
    with tempfile.TemporaryDirectory() as td:
        check_call(["boa", "build", recipe, "--output-folder", td])
        output_path = pathlib.Path(td)

        rex_a = next(output_path.rglob("**/rex-a*.tar.bz2"))

        with tarfile.open(rex_a) as fin:
            rexport = json.load(fin.extractfile("info/run_exports.json"))
            assert rexport["weak"]
            assert "strong" not in rexport
            assert rexport["weak"] == ["rex-exporter 0.1.*"]

        rex_b = next(output_path.rglob("**/rex-b*.tar.bz2"))

        with tarfile.open(rex_b) as fin:
            rexport = json.load(fin.extractfile("info/run_exports.json"))
            assert rexport["weak"]
            assert rexport["weak"] == ["rex-a 0.1.0.*"]
            assert rexport["strong"]
            assert rexport["strong"] == ["rex-exporter 0.1.*"]

        rexporter = next(output_path.rglob("**/rex-exporter*.tar.bz2"))
        with tarfile.open(rexporter) as fin:
            names = [x.name for x in fin.getmembers()]
            print(names)
            assert "info/run_exports.json" not in names
