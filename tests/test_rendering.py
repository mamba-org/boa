import pytest
from boa.core.run_build import extract_features, build_recipe
from boa.core.utils import get_config

import pathlib

tests_path = pathlib.Path(__file__).parent / "recipes-v2"

def test_extract_features():
    feats = extract_features("[static, ~xz, zlib, bzip2, ~something]")
    assert(feats["static"] is True)
    assert(feats["xz"] is False)
    assert(feats["zlib"] is True)
    assert(feats["bzip2"] is True)
    assert(feats["something"] is False)

    with pytest.raises(AssertionError):
        feats = extract_features("[static, ~xz, zlib, bzip2, ~something")

    with pytest.raises(AssertionError):
        feats = extract_features("static, ~xz, zlib, bzip2, ~something]")

    feats = extract_features("")
    assert(feats == {})

def test_variants():
    recipe = tests_path / "variant_test" / "recipe.yaml"
    cbc_file = tests_path / "variant_test" / "conda_build_config.yaml"

    variant = {"target_platform": 'linux-64'}
    cbc, config = get_config(".", variant, [cbc_file])
    cbc["target_platform"] = [variant["target_platform"]]

    assert(cbc == {'python': ['3.6', '3.7', '3.8'], 'target_platform': ['linux-64']})

    sorted_outputs = build_recipe("render", recipe,
            cbc,
            config,
            selected_features={}, notest=True, skip_existing=False, interactive=False)

    for o in sorted_outputs:
        assert(o.name == 'variant_test')
        assert(o.version == '0.1.0')

        print(o.requirements)