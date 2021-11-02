import pathlib
from subprocess import check_call


def test_build_grayskull():
    recipes_dir = pathlib.Path(__file__).parent / "recipes-v2"

    recipes = [str(x) for x in recipes_dir.iterdir() if x.is_dir()]

    for recipe in recipes:
        if "grayskull" in recipe:
            check_call(["boa", "build", recipe])


def test_build_ipywidgets():
    recipes_dir = pathlib.Path(__file__).parent / "recipes-v2"

    recipes = [str(x) for x in recipes_dir.iterdir() if x.is_dir()]

    for recipe in recipes:
        if "ipywidgets" in recipe:
            check_call(["boa", "build", recipe])


def test_build_notest():
    recipes_dir = pathlib.Path(__file__).parent / "recipes-v2"

    recipes = [str(x) for x in recipes_dir.iterdir() if x.is_dir()]
    recipe = recipes[0]

    check_call(["boa", "build", recipe, "--no-test"])
