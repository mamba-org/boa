# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

import re

from dataclasses import dataclass
from typing import Tuple, Optional, Union

from conda_build.utils import apply_pin_expressions


@dataclass
class PinSubpackage:
    name: str
    max_pin: str
    exact: bool

    def __init__(self, splitted):
        max_pin, exact = splitted[1][len("PIN_SUBPACKAGE") + 1 : -1].split(",")
        self.max_pin = max_pin
        self.exact = exact == "True"
        self.name = splitted[0]


class PinCompatible:
    name: str
    lower_bound: Optional[str] = None
    upper_bound: Optional[str] = None
    min_pin: str
    max_pin: str
    exact: bool

    def __init__(self, splitted):
        lower_bound, upper_bound, min_pin, max_pin, exact = splitted[1][
            len("PIN_COMPATIBLE") + 1 : -1
        ].split(",")
        if lower_bound == "None":
            lower_bound = None
        if upper_bound == "None":
            upper_bound = None

        self.lower_bound = lower_bound
        self.upper_bound = upper_bound
        self.min_pin = min_pin
        self.max_pin = max_pin
        self.exact = exact == "True"


@dataclass
class CondaBuildSpec:
    name: str
    raw: str
    splitted: Tuple[str]
    pin: Optional[Union[PinSubpackage]] = None

    is_inherited: bool = False
    is_compiler: bool = False
    is_transitive_dependency: bool = False
    channel: str = ""
    # final: String

    from_run_export: bool = False
    from_pinnings: bool = False

    def __init__(self, ms, is_inherited=False):
        self.raw = ms
        self.splitted = ms.split()
        self.name = self.splitted[0]

        is_pin = False
        if len(self.splitted) > 1:
            is_pin = self.splitted[1].startswith("PIN_")
            self.is_compiler = self.splitted[0].startswith("COMPILER_")

        self.is_inherited = is_inherited
        self.is_simple = len(self.splitted) == 1
        self.final = self.raw

        if is_pin:
            is_pin_compatible = self.splitted[1].startswith("PIN_COMPATIBLE")
            is_pin_subpackage = self.splitted[1].startswith("PIN_SUBPACKAGE")

            if is_pin_compatible:
                self.final[len("PIN_COMPATIBLE") + 1 : -1]
                self.pin = PinCompatible(self.splitted)
            elif is_pin_subpackage:
                self.pin = PinSubpackage(self.splitted)
            else:
                raise RuntimeError("could nto parse pin (" + self.splitted[1] + ")")

    @property
    def is_pin(self):
        return self.pin is not None

    @property
    def is_pin_compatible(self):
        return isinstance(self.pin, PinCompatible)

    @property
    def is_pin_subpackage(self):
        return isinstance(self.pin, PinSubpackage)

    @property
    def final_name(self):
        return self.final.split(" ")[0]

    @property
    def final_pin(self):
        if hasattr(self, "final_version"):
            return f"{self.final_name} {self.final_version[0]} {self.final_version[1]}"
        else:
            return self.final

    @property
    def final_triplet(self):
        return f"{self.final_name}-{self.final_version[0]}-{self.final_version[1]}"

    def loosen_spec(self):
        if self.is_compiler or self.is_pin:
            return

        if len(self.splitted) == 1:
            return

        if re.search(r"[^0-9\.]+", self.splitted[1]) is not None:
            return

        dot_c = self.splitted[1].count(".")

        app = "*" if dot_c >= 2 else ".*"

        if len(self.splitted) == 3:
            self.final = (
                f"{self.splitted[0]} {self.splitted[1]}{app} {self.splitted[2]}"
            )
        else:
            self.final = f"{self.splitted[0]} {self.splitted[1]}{app}"

    def __repr__(self):
        self.loosen_spec()
        return str(self.final)

    def eval_pin_subpackage(self, all_outputs):
        pkg_name = self.name
        output = None

        # TODO are we pinning the right version if building multiple variants?!
        for o in all_outputs:
            if o.name == pkg_name:
                output = o
                break

        if not output:
            raise RuntimeError(f"Could not find output with name {pkg_name}")

        version = output.version
        build_string = output.final_build_id

        if self.is_pin and self.pin.exact:
            self.final = f"{pkg_name} {version} {build_string}"
        else:
            version_parts = version.split(".")
            count_pin = self.pin.max_pin.count(".")
            version_pin = ".".join(version_parts[: count_pin + 1])
            version_pin += ".*"
            self.final = f"{pkg_name} {version_pin}"

    def eval_pin_compatible(self, build, host):
        versions = {b.name: b for b in build}
        versions.update({h.name: h for h in host})

        compatibility = None
        if versions:
            if self.pin.exact and versions.get(self.name):
                compatibility = " ".join(versions[self.name].final_version)
            else:
                version = (
                    self.pin.lower_bound or versions.get(self.name).final_version[0]
                )
                if version:
                    if self.pin.upper_bound:
                        if self.pin.min_pin or self.pin.lower_bound:
                            compatibility = ">=" + str(version) + ","
                        compatibility += "<{upper_bound}".format(
                            upper_bound=self.pin.upper_bound
                        )
                    else:
                        compatibility = apply_pin_expressions(
                            version, self.pin.min_pin, self.pin.max_pin
                        )

        self.final = (
            " ".join((self.name, compatibility))
            if compatibility is not None
            else self.name
        )
