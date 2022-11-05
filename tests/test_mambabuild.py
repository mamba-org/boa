import pytest
from pathlib import Path
from subprocess import check_call, CalledProcessError

recipes_dir = Path(__file__).parent / "recipes"

dep_error_recipes = [
    str(recipes_dir / name) for name in (
        "baddeps",
        "dep_error_nothing_provides",
        "dep_error_needed_by",
        "dep_error_package_requires",
        "dep_error_has_constaint",
    )
]
recipes = [
    str(x) for x in recipes_dir.iterdir()
    if x.is_dir() and str(x) not in dep_error_recipes
]
notest_recipes = [str(recipes_dir / "baddeps")]


@pytest.mark.parametrize("recipe", dep_error_recipes)
def test_build_dep_error_recipes(recipe):
    with pytest.raises(CalledProcessError):
        check_call(["conda", "mambabuild", recipe])


@pytest.mark.parametrize("recipe", recipes)
def test_build_recipes(recipe):
    check_call(["conda", "mambabuild", recipe])


@pytest.mark.parametrize("recipe", notest_recipes)
def test_build_notest(recipe):
    check_call(["conda", "mambabuild", recipe, "--no-test"])
