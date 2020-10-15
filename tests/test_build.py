import pathlib
from subprocess import check_call



def test_build_recipes():
    recipes_dir = pathlib.Path(__file__).parent / 'recipes'

    recipes = [str(x) for x in recipes_dir.iterdir() if x.is_dir()]

    for recipe in recipes:
        check_call(['boa', 'build', recipe])
