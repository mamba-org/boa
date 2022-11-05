import pytest
from pathlib import Path
from subprocess import check_call, CalledProcessError

recipes_dir = Path(__file__).parent / "recipes"

recipes = [str(x) for x in recipes_dir.iterdir() if x.is_dir()]
notest_recipes = [x for x in recipes if Path(x).name in ["baddeps"]]


@pytest.mark.parametrize("recipe", recipes)
def test_build_recipes(recipe):
    expected_fail_recipes = ["baddeps"]
    if Path(recipe).name in expected_fail_recipes:
        with pytest.raises(CalledProcessError):
            check_call(["conda", "mambabuild", recipe])
    else:
        check_call(["conda", "mambabuild", recipe])


@pytest.mark.parametrize("recipe", notest_recipes)
def test_build_notest(recipe):
    check_call(["conda", "mambabuild", recipe, "--no-test"])
