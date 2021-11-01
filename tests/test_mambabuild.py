import pytest
import pathlib
from subprocess import check_call, CalledProcessError


def test_build_recipes():
    recipes_dir = pathlib.Path(__file__).parent / "recipes"

    recipes = [str(x) for x in recipes_dir.iterdir() if x.is_dir()]

    expected_fail_recipes = ["baddeps"]
    for recipe in recipes:
        if recipe.rsplit("/", 1)[-1] in expected_fail_recipes:
            with pytest.raises(CalledProcessError):
                check_call(["conda", "mambabuild", recipe])
        else:
            check_call(["conda", "mambabuild", recipe])


def test_build_notest():
    recipes_dir = pathlib.Path(__file__).parent / "recipes"

    recipes = [str(x) for x in recipes_dir.iterdir() if x.is_dir()]
    recipe = recipes[0]

    check_call(["conda", "mambabuild", recipe, "--no-test"])
