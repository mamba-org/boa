# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

import os
from functools import partial
from conda_build.jinja_context import cdt as cb_cdt

# cdt = partial(cb_cdt, config=config, permit_undefined_jinja=False),


def pin_subpackage(name, max_pin="x.x.x.x.x", exact=False):
    return f"{name} PIN_SUBPACKAGE[{max_pin},{exact}]"


def pin_compatible(
    name,
    lower_bound=None,
    upper_bound=None,
    min_pin="x.x.x.x.x.x",
    max_pin="x",
    exact=False,
):
    return f"{name} PIN_COMPATIBLE[{lower_bound},{upper_bound},{min_pin},{max_pin},{exact}]"


def compiler(language):
    return f"COMPILER_{language.upper()} {language}"


def jinja_functions(config, context_dict):
    return {
        "pin_subpackage": pin_subpackage,
        "pin_compatible": pin_compatible,
        "cdt": partial(cb_cdt, config=config, permit_undefined_jinja=False),
        "compiler": compiler,
        "environ": os.environ,
    }
