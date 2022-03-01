from boa.helpers.ast_extract_syms import ast_extract_syms


def test_helpers():
    assert ast_extract_syms("vc <14") == ["vc"]
    assert ast_extract_syms("python > (3,6)") == ["python"]
    assert ast_extract_syms("somevar==(3,6)") == ["somevar"]
    assert ast_extract_syms("somevar<=linux") == ["somevar", "linux"]
    assert ast_extract_syms("target_platform == 'linux'") == ["target_platform"]
