# Copyright (C) 2021, QuantStack
# SPDX-License-Identifier: BSD-3-Clause

import hashlib
import os
import time
import sys
import re
import json
import copy

from typing import Union, Dict, Iterable, Any, Optional

try:
    from conda_build.metadata import default_structs, ARCH_MAP

    FIELDS = None
except ImportError:
    from conda_build.metadata import FIELDS, ARCH_MAP

    default_structs = None

from conda_build.utils import ensure_list, expand_globs, on_win


def get_package_version_pin(specs, name):
    for s in specs:
        x = s.split(" ")
        if x[0] == name and len(x) > 1:
            return x[1]
    return None


def build_string_from_metadata(metadata):
    if metadata.meta.get("build", {}).get("string"):
        build_str = metadata.get_value("build/string")
    else:
        res = []
        build_or_host = "host" if metadata.is_cross else "build"
        build_pkg_names = [ms.name for ms in metadata.ms_depends(build_or_host)]
        build_deps = metadata.meta.get("requirements", {}).get(build_or_host, [])
        # TODO: this is the bit that puts in strings like py27np111 in the filename.  It would be
        #    nice to get rid of this, since the hash supercedes that functionally, but not clear
        #    whether anyone's tools depend on this file naming right now.
        for s, names, places in (
            ("np", "numpy", 2),
            ("py", "python", 2),
            ("pl", "perl", 2),
            ("lua", "lua", 2),
            ("r", ("r", "r-base"), 2),
            ("mro", "mro-base", 3),
            ("mro", "mro-base_impl", 3),
        ):

            for ms in metadata.ms_depends("run"):
                for name in ensure_list(names):
                    if ms.name == name and name in build_pkg_names:
                        # only append numpy when it is actually pinned
                        if name == "numpy" and not metadata.numpy_xx:
                            continue
                        if metadata.noarch == name or (
                            metadata.get_value("build/noarch_python")
                            and name == "python"
                        ):
                            res.append(s)
                        else:
                            pkg_names = list(ensure_list(names))
                            pkg_names.extend(
                                [
                                    _n.replace("-", "_")
                                    for _n in ensure_list(names)
                                    if "-" in _n
                                ]
                            )
                            for _n in pkg_names:
                                variant_version = get_package_version_pin(
                                    build_deps, _n
                                ) or metadata.config.variant.get(
                                    _n.replace("-", "_"), ""
                                )
                                if variant_version:
                                    break
                            entry = "".join([s] + variant_version.split(".")[:places])
                            if entry not in res:
                                res.append(entry)

        features = ensure_list(metadata.get_value("build/features", []))
        if res:
            res.append("_")
        if features:
            res.extend(("_".join(features), "_"))
        res.append(
            "{0}".format(metadata.build_number() if metadata.build_number() else 0)
        )
        build_str = "".join(res)
    return build_str


class MetaData:

    path: str
    uses_new_style_compiler_activation: bool = False
    uses_vcs_in_meta: bool = False
    uses_vcs_in_build: bool = False
    build_is_host: bool = False
    is_cross: bool = True
    final: bool = True
    activate_build_script: bool = True

    numpy_xx: bool = False
    noarch: Optional[str] = None
    noarch_python: bool = False

    # TODO? What are the implications of this?!
    is_output: bool = False
    pin_depends: bool = False

    def __init__(self, path, output):
        self.config = output.config
        self.meta = output.data
        self.output = output

        if os.path.isdir(path):
            self.path = os.path.abspath(path)
        else:
            self.path = os.path.dirname(os.path.abspath(path))

        self._meta_name = "recipe.yaml"
        self._meta_path = os.path.join(self.path, self._meta_name)

        self.noarch = self.output.sections["build"].get("noarch", None)

    def get_section(self, key: str) -> Union[Dict, Iterable]:
        return self.output.sections[key]

    def skip(self):
        return self.output.skip()

    def get_value(self, in_key: str, default: Any = None, autotype=True) -> Any:
        if in_key.count("/") == 2:
            section, num, key = in_key.split("/")
        else:
            section, key = in_key.split("/")
            num = 0

        # conda-build compat
        if default_structs:
            if default is None and in_key in default_structs:
                default = default_structs[in_key]()
        elif FIELDS:
            if autotype and default is None and FIELDS.get(section, {}).get(key):
                default = FIELDS[section][key]()

        section = self.output.sections.get(section, {})
        if isinstance(section, list):
            return section[int(num)].get(key, default)
        else:
            return section.get(key, default)

    def rendered_meta(self):
        res = self.meta.copy()
        for typ in res.get("requirements", tuple()):
            res["requirements"][typ] = [x.final_pin for x in self.get_dependencies(typ)]

        return res

    @property
    def source_provided(self):
        return not bool(self.meta.get("source")) or (
            os.path.isdir(self.config.work_dir)
            and len(os.listdir(self.config.work_dir)) > 0
        )

    def ms_depends(self, typ="run"):
        names = ("python", "numpy", "perl", "lua")
        name_ver_list = [
            (name, self.config.variant[name])
            for name in names
            if self.config.variant.get(name)
        ]
        if self.config.variant.get("r_base"):
            # r is kept for legacy installations, r-base deprecates it.
            name_ver_list.extend(
                [
                    ("r", self.config.variant["r_base"]),
                    ("r-base", self.config.variant["r_base"]),
                ]
            )
        specs = []
        # for spec in ensure_list(self.get_value('requirements/' + typ, [])):
        for spec in self.get_dependencies(typ):
            if not spec:
                continue
            if spec.is_transitive_dependency and not spec.from_run_export:
                continue

            if spec.name == self.name():
                raise RuntimeError("%s cannot depend on itself" % self.name())

            for name, _ in name_ver_list:
                if spec.name == name:
                    if self.noarch:
                        continue

            for c in "=!@#$%^&*:;\"'\\|<>?/":
                if c in spec.name:
                    sys.exit(
                        "Error: bad character '%s' in package name "
                        "dependency '%s'" % (c, spec.name)
                    )

            parts = spec.splitted
            if len(parts) >= 2:
                if parts[1] in {">", ">=", "=", "==", "!=", "<", "<="}:
                    msg = (
                        "Error: bad character '%s' in package version "
                        "dependency '%s'" % (parts[1], spec.name)
                    )
                    if len(parts) >= 3:
                        msg += "\nPerhaps you meant '%s %s%s'" % (
                            spec.name,
                            parts[1],
                            parts[2],
                        )
                    sys.exit(msg)
            specs.append(spec)

        return specs

    def name(self, fail_ok=False):
        return self.output.name

    def version(self):
        return self.output.version

    def build_string(self):
        return self.output.build_string

    def build_number(self):
        return self.output.build_number

    def include_recipe(self):
        return self.get_value("build/include_recipe", True)

    def use_feature_map(self):
        return self.output.feature_map

    def build_features(self):
        m = self.use_feature_map()

        def truefalse(x):
            if x:
                return "1"
            else:
                return "0"

        return {"FEATURE_" + k.upper(): truefalse(v["activated"]) for k, v in m.items()}

    @property
    def meta_path(self):
        meta_path = self._meta_path or self.meta.get("extra", {}).get(
            "parent_recipe", {}
        ).get("path", "")
        if meta_path and os.path.basename(meta_path) != self._meta_name:
            meta_path = os.path.join(meta_path, self._meta_name)
        return meta_path

    def hash_dependencies(self):
        """With arbitrary pinning, we can't depend on the build string as done in
        build_string_from_metadata - there's just too much info.  Instead, we keep that as-is, to
        not be disruptive, but we add this extra hash, which is just a way of distinguishing files
        on disk.  The actual determination of dependencies is done in the repository metadata.

        This was revised in conda-build 3.1.0: hashing caused too many package
            rebuilds. We reduce the scope to include only the pins added by conda_build_config.yaml,
            and no longer hash files that contribute to the recipe.
        """
        hash_ = ""
        hashing_dependencies = self.get_hash_contents()
        if hashing_dependencies:
            hash_ = hashlib.sha1(
                json.dumps(hashing_dependencies, sort_keys=True).encode()
            )
            # save only the first HASH_LENGTH characters - should be more than
            #    enough, since these only need to be unique within one version
            # plus one is for the h - zero pad on the front, trim to match HASH_LENGTH
            hash_ = "h{0}".format(hash_.hexdigest())[: self.config.hash_length + 1]
        return hash_

    def build_id(self):
        manual_build_string = self.get_value("build/string")
        if manual_build_string:
            out = manual_build_string
        else:
            # default; build/string not set or uses PKG_HASH variable, so we should fill in the hash
            out = build_string_from_metadata(self)
            if self.config.filename_hashing and self.final:
                hash_ = self.hash_dependencies()
                if not re.findall("h[0-9a-f]{%s}" % self.config.hash_length, out):
                    ret = out.rsplit("_", 1)
                    try:
                        int(ret[0])
                        out = "_".join((hash_, str(ret[0]))) if hash_ else str(ret[0])
                    except ValueError:
                        out = ret[0] + hash_
                    if len(ret) > 1:
                        out = "_".join([out] + ret[1:])
                else:
                    out = re.sub("h[0-9a-f]{%s}" % self.config.hash_length, hash_, out)
        return out

    def dist(self):
        return "%s-%s-%s" % (self.name(), self.version(), self.build_id())

    def get_dependencies(self, which):
        deps = self.output.requirements[which]
        # print(deps)
        # for feat, used in self.use_feature_map().items():
        #     if used:
        #         fdeps = used.get('requirements')
        #         if fdeps:
        #             fdeps = fdeps.get(which, [])
        #         deps.extend(fdeps)
        return deps

    def get_hash_contents(self):
        """
        # A hash will be added if all of these are true for any dependency:
        #
        # 1. package is an explicit dependency in build, host, or run deps
        # 2. package has a matching entry in conda_build_config.yaml which is a pin to a specific
        #    version, not a lower bound
        # 3. that package is not ignored by ignore_version
        #
        # The hash is computed based on the pinning value, NOT the build
        #    dependency build string. This means hashes won't change as often,
        #    but it also means that if run_exports is overly permissive,
        #    software may break more often.
        #
        # A hash will also ALWAYS be added when a compiler package is a build
        #    or host dependency. Reasoning for that is that the compiler
        #    package represents compiler flags and other things that can and do
        #    dramatically change compatibility. It is much more risky to drop
        #    this info (by dropping the hash) than it is for other software.

        # used variables - anything with a value in conda_build_config.yaml that applies to this
        #    recipe.  Includes compiler if compiler jinja2 function is used.
        """

        # trim_build_only_deps(self, dependencies)
        dependencies = (
            self.get_dependencies("build")
            + self.get_dependencies("host")
            # self.output.requirements["build"] + self.output.requirements["host"]
        )
        dependencies = {x.name for x in dependencies}
        # filter out ignored versions
        build_string_excludes = ["python", "r_base", "perl", "lua", "target_platform"]
        build_string_excludes.extend(
            ensure_list(self.config.variant.get("ignore_version", []))
        )

        # TODO
        # if 'numpy' in dependencies:
        #     pin_compatible, not_xx = self.uses_numpy_pin_compatible_without_xx
        #     # numpy_xx means it is accounted for in the build string, with npXYY
        #     # if not pin_compatible, then we don't care about the usage, and omit it from the hash.
        #     if self.numpy_xx or (pin_compatible and not not_xx):
        #         build_string_excludes.append('numpy')
        # always exclude older stuff that's always in the build string (py, np, pl, r, lua)
        if build_string_excludes:
            exclude_pattern = re.compile(
                "|".join("{}[\\s$]?.*".format(exc) for exc in build_string_excludes)
            )
            filtered_deps = []
            for req in dependencies:
                if exclude_pattern.match(req):
                    continue
                if req in self.config.variant:
                    if " " in self.config.variant[req]:
                        continue
                filtered_deps.append(req)

        take_keys = set(self.config.variant.keys())
        if "python" in take_keys and "python" not in dependencies:
            take_keys.remove("python")

        # retrieve values - this dictionary is what makes up the hash.
        return {key: self.config.variant[key] for key in take_keys}

    def info_index(self):
        arch = (
            "noarch" if self.config.target_subdir == "noarch" else self.config.host_arch
        )
        d = dict(
            name=self.name(),
            version=self.version(),
            build=self.build_id(),
            build_number=self.build_number() if self.build_number() else 0,
            platform=self.config.platform
            if (self.config.platform != "noarch" and arch != "noarch")
            else None,
            arch=ARCH_MAP.get(arch, arch),
            subdir=self.config.target_subdir,
            depends=sorted(
                " ".join(ms.final.split(" ")[:3]) for ms in self.ms_depends()
            ),
            timestamp=int(time.time() * 1000),
        )
        for key in ("license", "license_family"):
            value = self.get_value("about/" + key)
            if value:
                d[key] = value

        preferred_env = self.get_value("build/preferred_env")
        if preferred_env:
            d["preferred_env"] = preferred_env

        # conda 4.4+ optional dependencies
        constrains = ensure_list(self.get_value("requirements/run_constrained"))
        # filter None values
        constrains = [str(v) for v in constrains if v]
        if constrains:
            d["constrains"] = constrains

        if self.get_value("build/features"):
            d["features"] = " ".join(self.get_value("build/features"))
        if self.get_value("build/track_features"):
            d["track_features"] = " ".join(self.get_value("build/track_features"))
        if self.get_value("build/provides_features"):
            d["provides_features"] = self.get_value("build/provides_features")
        if self.get_value("build/requires_features"):
            d["requires_features"] = self.get_value("build/requires_features")
        if self.noarch:
            d["platform"] = d["arch"] = None
            d["subdir"] = "noarch"
            # These are new-style noarch settings.  the self.noarch setting can be True in 2 ways:
            #    if noarch: True or if noarch_python: True.  This is disambiguation.
            build_noarch = self.get_value("build/noarch")
            if build_noarch:
                d["noarch"] = build_noarch

        # TODO
        # if self.is_app():
        #     d.update(self.app_meta())
        return d

    # options
    def always_include_files(self):
        files = ensure_list(self.get_value("build/always_include_files", []))
        if any("\\" in i for i in files):
            raise RuntimeError(
                "build/always_include_files paths must use / "
                "as the path delimiter on Windows"
            )
        if on_win:
            files = [f.replace("/", "\\") for f in files]

        return expand_globs(files, self.config.host_prefix)

    def binary_relocation(self):
        v = self.get_value("build/binary_relocation", True)
        if isinstance(v, bool):
            return v
        return expand_globs(v, self.config.host_prefix)

    def ignore_prefix_files(self):
        v = self.get_value("build/ignore_prefix_files", False)
        if isinstance(v, bool):
            return v
        return expand_globs(v, self.config.host_prefix)

    def binary_has_prefix_files(self):
        ret = self.get_value("build/binary_has_prefix_files", [])
        return expand_globs(ret, self.config.host_prefix)

    def has_prefix_files(self):
        ret = self.get_value("build/has_prefix_files", [])
        return expand_globs(ret, self.config.host_prefix)

    def copy(self):
        # delete transactions as we can't copy them
        # TODO find a better way ...
        self.output.transactions = None
        new = copy.deepcopy(self)
        return new

    def get_test_deps(self, py_files, pl_files, lua_files, r_files):
        specs = ["%s %s %s" % (self.name(), self.version(), self.build_id())]

        # add packages listed in the run environment and test/requires
        specs.extend(ms.final for ms in self.ms_depends("run"))
        specs += self.get_value("test/requires", [])
        spec_names = set((s.name for s in self.ms_depends("run")))

        if py_files and "python" not in spec_names:
            # as the tests are run by python, ensure that python is installed.
            specs += ["python"]
        if pl_files and "perl" not in spec_names:
            # as the tests are run by perl, we need to specify it
            specs += ["perl"]
        if lua_files and "lua" not in spec_names:
            # not sure how this shakes out
            specs += ["lua"]
        if r_files and not any(s in ("r-base", "mro-base") for s in spec_names):
            # not sure how this shakes out
            specs += ["r-base"]

        # What is this?!
        # specs.extend(utils.ensure_list(self.config.extra_deps))
        return specs
