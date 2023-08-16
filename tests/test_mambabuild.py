import pytest
import sys
from pathlib import Path
from queue import Queue
from subprocess import CalledProcessError, PIPE, Popen, check_call, check_output
from threading import Thread

recipes_dir = Path(__file__).parent / "recipes"

dep_error_recipes = {
    str(recipes_dir / name): deps
    for name, *deps in (
        ("baddeps", "thispackagedoesnotexist"),
        ("dep_error_nothing_provides", "thispackagedoesnotexist"),
        ("dep_error_needed_by", "thispackagedoesnotexist", "dep_error_needed_by_1"),
        ("dep_error_package_requires", "python", "cython"),
        ("dep_error_has_constaint", "python=", "python_abi="),
    )
}
recipes = [
    str(x)
    for x in recipes_dir.iterdir()
    if x.is_dir() and str(x) not in dep_error_recipes
]
notest_recipes = [str(recipes_dir / "baddeps")]


def dep_error_capture_call(cmd):
    def capture(pipe, put):
        err_lines = []
        for line in iter(pipe.readline, ""):
            if err_lines or line.startswith(
                "conda_build.exceptions.DependencyNeedsBuildingError:"
            ):
                err_lines.append(line)
            put(line)
        put(None)
        put("".join(err_lines).replace("\n", ""))
        pipe.close()

    def passthrough(write, get):
        for line in iter(get, None):
            write(line)

    def create_thread(target, *args):
        return Thread(target=target, args=args, daemon=True)

    process = Popen(cmd, stderr=PIPE, close_fds=True, text=True)
    queue = Queue()
    capture_thread = create_thread(capture, process.stderr, queue.put)
    passthrough_thread = create_thread(passthrough, sys.stderr.write, queue.get)
    capture_thread.start()
    passthrough_thread.start()
    process.wait()
    capture_thread.join()
    passthrough_thread.join()
    if process.returncode:
        raise CalledProcessError(process.returncode, cmd, None, queue.get())


@pytest.mark.parametrize("recipe,deps", dep_error_recipes.items())
def test_build_dep_error_recipes(recipe, deps):
    with pytest.raises(CalledProcessError) as exc_info:
        dep_error_capture_call(["conda", "mambabuild", recipe])
    error = exc_info.value.stderr
    for dep in deps:
        assert f'MatchSpec("{dep}' in error


@pytest.mark.parametrize("recipe", recipes)
def test_build_recipes(recipe):
    check_call(["conda", "mambabuild", recipe])


@pytest.mark.parametrize("recipe", notest_recipes)
def test_build_notest(recipe):
    check_call(["conda", "mambabuild", recipe, "--no-test"])


@pytest.mark.parametrize("recipe", recipes)
def test_build_with_output_flags(recipe, tmp_path: Path):
    recipe = recipes_dir / "environ"
    proposed_output = check_output(
        [
            "conda",
            "mambabuild",
            recipe,
            "--output-folder",
            str(tmp_path),
            "--output",
        ]
    ).decode()

    assert proposed_output.startswith(str(tmp_path.absolute()))
    assert sys.platform in proposed_output
