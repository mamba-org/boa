import sys
import pytest
from boa.core.run_build import extract_features, build_recipe
from boa.core.utils import get_config
import pathlib

tests_path = pathlib.Path(__file__).parent / "variants"


def test_extract_features():
    feats = extract_features("[static, ~xz, zlib, bzip2, ~something]")
    assert feats["static"] is True
    assert feats["xz"] is False
    assert feats["zlib"] is True
    assert feats["bzip2"] is True
    assert feats["something"] is False

    with pytest.raises(AssertionError):
        feats = extract_features("[static, ~xz, zlib, bzip2, ~something")

    with pytest.raises(AssertionError):
        feats = extract_features("static, ~xz, zlib, bzip2, ~something]")

    feats = extract_features("")
    assert feats == {}


def get_target_platform():
    if sys.platform == "win32":
        return "win-64"
    else:
        return "linux-64"


def get_outputs(
    cbcfname, recipename="recipe.yaml", folder="variant_test", cmd="render"
):
    recipe = tests_path / folder / recipename
    cbc_file = tests_path / folder / cbcfname

    variant = {"target_platform": get_target_platform()}

    cbc, config = get_config(".", variant, [cbc_file])
    cbc["target_platform"] = [variant["target_platform"]]

    sorted_outputs = build_recipe(
        cmd,
        recipe,
        cbc,
        config,
        selected_features={},
        notest=True,
        skip_existing=False,
        interactive=False,
        continue_on_failure=False,
    )

    return cbc, sorted_outputs


def test_variants_zipping():

    cbc, sorted_outputs = get_outputs("cbc1.yaml")
    assert cbc == {
        "python": ["3.6", "3.7", "3.8"],
        "target_platform": [get_target_platform()],
    }

    expected_variants = ["python 3.6.*", "python 3.7.*", "python 3.8.*"]

    for o in sorted_outputs:
        assert o.name == "variant_test"
        assert o.version == "0.1.0"
        assert str(o.requirements["host"][0]) in expected_variants
        assert o.requirements["host"][0].from_pinnings is True

    cbc, sorted_outputs = get_outputs("cbc2.yaml")
    assert len(sorted_outputs) == 9

    cbc, sorted_outputs = get_outputs("cbc3.yaml")

    assert len(sorted_outputs) == 3

    expected_variants = [
        ["python 3.6.*", "pip 1.*"],
        ["python 3.7.*", "pip 2.*"],
        ["python 3.8.*", "pip 3.*"],
    ]
    got_variants = []
    for o in sorted_outputs:
        assert o.name == "variant_test"
        assert o.version == "0.1.0"
        got_variants.append([str(x) for x in o.requirements["host"]])
        assert o.requirements["host"][0].from_pinnings is True
    assert got_variants == expected_variants

    cbc, sorted_outputs = get_outputs("cbc4.yaml")
    got_variants = []
    for o in sorted_outputs:
        assert o.name == "variant_test"
        assert o.version == "0.1.0"
        got_variants.append([str(x) for x in o.requirements["host"]])
        assert o.requirements["host"][0].from_pinnings is True
    assert got_variants == expected_variants

    cbc, sorted_outputs = get_outputs("cbc3.yaml", "recipe2.yaml")

    assert len(sorted_outputs) == 3

    expected_variants = [
        ["python 3.6.*", "pip 1.*", "libxyz"],
        ["python 3.7.*", "pip 2.*", "libxyz"],
        ["python 3.8.*", "pip 3.*", "libxyz"],
    ]
    got_variants = []
    for o in sorted_outputs:
        assert o.name == "variant_test"
        assert o.version == "0.1.0"
        got_variants.append([str(x) for x in o.requirements["host"]])
        assert o.requirements["host"][0].from_pinnings is True
    assert got_variants == expected_variants

    cbc, sorted_outputs = get_outputs("cbc5.yaml", "recipe2.yaml")

    expected_variants = [
        ["python 3.6.*", "pip 1.*", "libxyz 5.*"],
        ["python 3.7.*", "pip 2.*", "libxyz 5.*"],
        ["python 3.6.*", "pip 1.*", "libxyz 6.*"],
        ["python 3.7.*", "pip 2.*", "libxyz 6.*"],
        ["python 3.6.*", "pip 1.*", "libxyz 7.*"],
        ["python 3.7.*", "pip 2.*", "libxyz 7.*"],
    ]
    got_variants = []
    for o in sorted_outputs:
        assert o.name == "variant_test"
        assert o.version == "0.1.0"
        got_variants.append([str(x) for x in o.requirements["host"]])
        assert o.requirements["host"][0].from_pinnings is True

    assert got_variants == expected_variants

    with pytest.raises(ValueError):
        cbc, sorted_outputs = get_outputs("cbc6.yaml", "recipe2.yaml")

    cbc, sorted_outputs = get_outputs("cbc7.yaml", "recipe2.yaml")
    expected_variants = [
        ["python 3.6.*", "pip 1.*", "libxyz 5.*"],
        ["python 3.7.*", "pip 2.*", "libxyz 6.*"],
    ]
    got_variants = []
    for o in sorted_outputs:
        assert o.name == "variant_test"
        assert o.version == "0.1.0"
        got_variants.append([str(x) for x in o.requirements["host"]])
        assert o.requirements["host"][0].from_pinnings is True

    assert got_variants == expected_variants


def test_variants():
    cbc, sorted_outputs = get_outputs("cbc1.yaml", folder="underscores")
    assert cbc["abseil_cpp"] == ["20200225.2"]
    assert cbc["arpack"] == ["3.6.3"]

    expected_variants = [
        "abseil-cpp 20200225.2.*",
        "arrow-cpp 0.17.*",
        "boost-cpp 1.72.0.*",
    ]

    for o in sorted_outputs:
        assert o.name == "underscores"
        assert o.version == "0.1.0"
        print(o.requirements)
        assert str(o.requirements["host"][0]) in expected_variants
        assert o.requirements["host"][0].from_pinnings is True

    cbc, sorted_outputs = get_outputs(
        "cbc2.yaml", "recipe2.yaml", folder="underscores", cmd="full-render"
    )


def test_compiler():
    cbc, sorted_outputs = get_outputs("cbc_default.yaml", folder="compiler_test")
    for o in sorted_outputs:
        assert o.name == "compiler_test"
        assert o.version == "0.1.0"
        print(o.requirements)
        c_comp = str(o.requirements["build"][0])
        assert c_comp.rsplit("_", 1)[1] == get_target_platform()
        if sys.platform == "linux":
            str(o.requirements["build"][0]) == "gcc_linux-64"
        assert (
            str(o.requirements["build"][1]).rsplit("_", 1)[1] == get_target_platform()
        )
        assert (
            str(o.requirements["build"][2]).rsplit("_", 1)[1] == get_target_platform()
        )
        assert o.requirements["build"][0].from_pinnings is True

    cbc, sorted_outputs = get_outputs("compilers.yaml", folder="compiler_test")
    expected_compilers = [
        f"customcompiler_{get_target_platform()} 11*",
        f"fortranisstillalive_{get_target_platform()} 2000*",
        f"cppcompiler_{get_target_platform()} 200*",
    ]
    for o in sorted_outputs:
        assert o.name == "compiler_test"
        assert o.version == "0.1.0"
        print(o.requirements)
        comps = [str(x) for x in o.requirements["build"]]
        assert sorted(comps) == sorted(expected_compilers)
