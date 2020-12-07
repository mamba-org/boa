from boa.core.solver import get_solver
import copy
import re
import json
from pathlib import Path
import sys

from dataclasses import dataclass
from typing import Tuple

from rich.console import Console
from rich.table import Table
from rich.padding import Padding


# TODO remove
import conda_build.jinja_context
from conda.base.context import context
from conda_build.config import get_or_merge_config
from conda_build.utils import apply_pin_expressions
from conda.models.channel import Channel as CondaChannel
from conda.core.package_cache_data import PackageCacheData
from conda_build.metadata import eval_selector, ns_cfg

console = Console()


@dataclass
class CondaBuildSpec:
    name: str
    raw: str
    splitted: Tuple[str]
    is_pin: bool = False
    is_pin_compatible: bool = False
    is_compiler: bool = False
    is_transitive_dependency: bool = False
    channel: str = ""
    # final: String

    from_run_export: bool = False
    from_pinnings: bool = False

    def __init__(self, ms):
        self.raw = ms
        self.splitted = ms.split()
        self.name = self.splitted[0]
        if len(self.splitted) > 1:
            self.is_pin = self.splitted[1].startswith("PIN_")
            self.is_pin_compatible = self.splitted[1].startswith("PIN_COMPATIBLE")
            self.is_compiler = self.splitted[0].startswith("COMPILER_")

        self.is_simple = len(self.splitted) == 1
        self.final = self.raw

        if self.is_pin_compatible:
            self.final[len("PIN_COMPATIBLE") + 1 : -1]

    @property
    def final_name(self):
        return self.final.split(" ")[0]

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
        return self.final

    def eval_pin_subpackage(self, all_outputs):
        if not self.splitted[1].startswith("PIN_SUBPACKAGE"):
            return
        pkg_name = self.name
        max_pin, exact = self.splitted[1][len("PIN_SUBPACKAGE") + 1 : -1].split(",")
        exact = exact == "True"
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

        if exact:
            self.final = f"{pkg_name} {version} {build_string}"
        else:
            version_parts = version.split(".")
            count_pin = max_pin.count(".")
            version_pin = ".".join(version_parts[: count_pin + 1])
            version_pin += ".*"
            self.final = f"{pkg_name} {version_pin}"

    def eval_pin_compatible(self, build, host):

        lower_bound, upper_bound, min_pin, max_pin, exact = self.splitted[1][
            len("PIN_COMPATIBLE") + 1 : -1
        ].split(",")
        if lower_bound == "None":
            lower_bound = None
        if upper_bound == "None":
            upper_bound = None
        exact = exact == "True"

        versions = {b.name: b for b in build}
        versions.update({h.name: h for h in host})

        compatibility = None
        if versions:
            if exact and versions.get(self.name):
                compatibility = " ".join(versions[self.name].final_version)
            else:
                version = lower_bound or versions.get(self.name).final_version[0]
                if version:
                    if upper_bound:
                        if min_pin or lower_bound:
                            compatibility = ">=" + str(version) + ","
                        compatibility += "<{upper_bound}".format(
                            upper_bound=upper_bound
                        )
                    else:
                        compatibility = apply_pin_expressions(version, min_pin, max_pin)

        self.final = (
            " ".join((self.name, compatibility))
            if compatibility is not None
            else self.name
        )


class Output:
    def __init__(
        self, d, config, parent=None, conda_build_config=None, selected_features=None
    ):
        if parent is None:
            parent = {}
        if selected_features is None:
            selected_features = {}
        self.data = d
        self.data["source"] = d.get("source", parent.get("source", {}))
        self.config = config
        self.conda_build_config = conda_build_config or {}
        self.name = d["package"]["name"]
        self.version = d["package"]["version"]
        self.build_string = d["package"].get("build_string")
        self.build_number = d["build"].get("number", 0)
        self.is_first = False
        self.sections = {}

        def set_section(sname):
            self.sections[sname] = {}
            self.sections[sname].update(parent.get(sname, {}))
            self.sections[sname].update(d.get(sname, {}))

        set_section("build")
        set_section("package")
        set_section("app")
        set_section("extra")
        set_section("test")

        self.sections["files"] = d.get("files")
        self.sections["source"] = self.data.get("source", {})
        if hasattr(self.sections["source"], "keys"):
            self.sections["source"] = [self.sections["source"]]

        self.sections["features"] = parent.get("features", [])

        self.feature_map = {f["name"]: f for f in self.sections.get("features", [])}
        for fname, feat in self.feature_map.items():
            activated = feat.get("default", False)
            if fname in selected_features:
                activated = selected_features[fname]

            feat["activated"] = activated

        if self.feature_map.get("static") and self.feature_map["static"]["activated"]:
            self.name += "-static"

        if len(self.feature_map):
            table = Table()
            table.title = "Activated Features"
            table.add_column("Feature")
            table.add_column("State")
            for feature in self.feature_map:
                if self.feature_map[feature]["activated"]:
                    table.add_row(feature, "[green]ON[/green]")
                else:
                    table.add_row(feature, "[red]OFF[/red]")

            console.print(table)

        self.requirements = copy.copy(d.get("requirements", {}))
        for f in self.feature_map.values():
            if f["activated"]:
                if not f.get("requirements"):
                    continue
                for i in ["build", "host", "run", "run_constrained"]:
                    base_req = self.requirements.get(i, [])
                    feat_req = f["requirements"].get(i, [])
                    base_req += feat_req
                    if len(base_req):
                        self.requirements[i] = base_req

        self.transactions = {}

        self.parent = parent

        for section in ("build", "host", "run", "run_constrained"):
            self.requirements[section] = [
                CondaBuildSpec(r) for r in (self.requirements.get(section) or [])
            ]

        # handle strong and weak run exports
        run_exports = []
        for el in self.sections["build"].get("run_exports", []):
            if type(el) is str:
                run_exports.append(CondaBuildSpec(el))
            else:
                raise RuntimeError("no strong run exports supported as of now.")
                # sub_run_exports = []
                # for key, val in el:
                #     for x in val:
                #         sub_run_exports.append(CondaBuildSpec(x))
                #     run_exports.append({})
        if run_exports:
            self.sections["build"]["run_exports"] = run_exports

    def skip(self):
        skips = self.sections["build"].get("skip")

        if skips:
            return any([eval_selector(x, ns_cfg(self.config), []) for x in skips])
        return False

    def all_requirements(self):
        requirements = (
            self.requirements.get("build")
            + self.requirements.get("host")
            + self.requirements.get("run")
        )
        return requirements

    def apply_variant(self, variant, differentiating_keys=()):
        copied = copy.deepcopy(self)

        copied.variant = variant
        for idx, r in enumerate(self.requirements["build"]):
            vname = r.name.replace("-", "_")
            if vname in variant:
                copied.requirements["build"][idx] = CondaBuildSpec(
                    r.name + " " + variant[vname]
                )
                copied.requirements["build"][idx].from_pinnings = True
        for idx, r in enumerate(self.requirements["host"]):
            vname = r.name.replace("-", "_")
            if vname in variant:
                copied.requirements["host"][idx] = CondaBuildSpec(
                    r.name + " " + variant[vname]
                )
                copied.requirements["host"][idx].from_pinnings = True

        # todo figure out if we should pin like that in the run reqs as well?
        for idx, r in enumerate(self.requirements["run"]):
            vname = r.name.replace("-", "_")
            if vname in variant:
                copied.requirements["run"][idx] = CondaBuildSpec(
                    r.name + " " + variant[vname]
                )
                copied.requirements["run"][idx].from_pinnings = True

        # insert compiler_cxx, compiler_c and compiler_fortran
        for idx, r in enumerate(self.requirements["build"]):
            if r.name.startswith("COMPILER_"):
                lang = r.splitted[1].lower()
                compiler = conda_build.jinja_context.compiler(lang, self.config)
                if variant.get(lang + "_compiler_version"):
                    version = variant[lang + "_compiler_version"]
                    copied.requirements["build"][idx].final = f"{compiler} {version}*"
                else:
                    copied.requirements["build"][idx].final = f"{compiler}"
                copied.requirements["build"][idx].from_pinnings = True

        for r in self.requirements["host"]:
            if r.name.startswith("COMPILER_"):
                raise RuntimeError("Compiler should be in build section")

        copied.config = get_or_merge_config(self.config, variant=variant)

        copied.differentiating_variant = []
        for k in differentiating_keys:
            copied.differentiating_variant.append(variant[k])

        return copied

    def __rich__(self):
        from rich import box

        table = Table(box=box.MINIMAL_DOUBLE_HEAD)
        s = f"Output: {self.name} {self.version} BN: {self.build_number}\n"
        if hasattr(self, "differentiating_variant"):
            short_v = " ".join([val for val in self.differentiating_variant])
            s += f"Variant: {short_v}\n"
        s += "Build:\n"
        table.title = s
        table.add_column("Dependency")
        table.add_column("Version requirement")
        table.add_column("Selected")
        table.add_column("Build")
        table.add_column("Channel")

        def spec_format(x):
            version, fv = " ", " "
            channel = CondaChannel.from_url(x.channel).name

            if (
                x.channel.startswith("file://")
                and context.local_build_root in x.channel
            ):
                channel = "local"

            if len(x.final.split(" ")) > 1:
                version = " ".join(r.final.split(" ")[1:])
            if hasattr(x, "final_version"):
                fv = x.final_version
            color = "white"
            if x.from_run_export:
                color = "blue"
            if x.from_pinnings:
                color = "green"
            if x.is_transitive_dependency:
                table.add_row(
                    f"{r.final_name}", "", f"{fv[0]}", f"{fv[1]}", f"{channel}"
                )
                return

            if x.is_pin:
                if x.is_pin_compatible:
                    version = "PC " + version
                else:
                    version = "PS " + version
                color = "cyan"

            if len(fv) >= 2:
                table.add_row(
                    f"[bold white]{r.final_name}[/bold white]",
                    f"[{color}]{version}[/{color}]",
                    f"{fv[0]}",
                    f"{fv[1]}",
                    f"{channel}",
                )
            else:
                table.add_row(
                    f"[bold white]{r.final_name}[/bold white]",
                    f"[{color}]{version}[/{color}]",
                    f"{fv[0]}",
                    "",
                    f"{channel}",
                )

        def add_header(header, head=False):
            p = Padding("", (0, 0), style="black")
            if head:
                pns = Padding("", (0, 0), style="black")
                table.add_row(pns, pns, pns, pns, pns)
            table.add_row(Padding(header, (0, 0), style="bold yellow"), p, p, p, p)

        if self.requirements["build"]:
            add_header("Build")
            for r in self.requirements["build"]:
                spec_format(r)
        if self.requirements["host"]:
            add_header("Host", True)
            for r in self.requirements["host"]:
                spec_format(r)
        if self.requirements["run"]:
            add_header("Run", True)
            for r in self.requirements["run"]:
                spec_format(r)
        return table

    def __repr__(self):
        s = f"Output: {self.name} {self.version} BN: {self.build_number}\n"
        if hasattr(self, "differentiating_variant"):
            short_v = " ".join([val for val in self.differentiating_variant])
            s += f"Variant: {short_v}\n"
        s += "Build:\n"

        def spec_format(x):
            version, fv = " ", " "
            if len(x.final.split(" ")) > 1:
                version = " ".join(r.final.split(" ")[1:])
            if hasattr(x, "final_version"):
                fv = x.final_version
            color = "white"
            if x.from_run_export:
                color = "blue"
            if x.from_pinnings:
                color = "green"
            if x.is_transitive_dependency:
                return f" - {r.final_name:<51} {fv[0]:<10} {fv[1]:<10}\n"
            if x.is_pin:
                if x.is_pin_compatible:
                    version = "PC " + version
                else:
                    version = "PS " + version
                color = "cyan"

            channel = CondaChannel.from_url(x.channel).name

            if len(fv) >= 2:
                return f" - [white]{r.final_name:<30}[/white] [{color}]{version:<20}[/{color}] {fv[0]:<10} {fv[1]:<20} {channel}\n"
            else:
                return f" - [white]{r.final_name:<30}[/white] [{color}]{version:<20}[/{color}] {fv[0]:<20} {channel}\n"

        for r in self.requirements["build"]:
            s += spec_format(r)
        s += "Host:\n"
        for r in self.requirements["host"]:
            s += spec_format(r)
        s += "Run:\n"
        for r in self.requirements["run"]:
            s += spec_format(r)
        return s

    def propagate_run_exports(self, env, pkg_cache):
        # find all run exports
        collected_run_exports = []
        config_pins = self.conda_build_config.get("pin_run_as_build", {})
        for s in self.requirements[env]:
            if s.is_transitive_dependency:
                continue
            if s.name in self.sections["build"].get("ignore_run_exports", []):
                continue
            if hasattr(s, "final_version"):
                final_triple = (
                    f"{s.final_name}-{s.final_version[0]}-{s.final_version[1]}"
                )
            else:
                console.print(f"[red]{s} has no final version")
                continue

            if s.name.replace("-", "_") in config_pins:
                s.run_exports_info = {
                    "weak": [
                        f"{s.final_name} {apply_pin_expressions(s.final_version[0], **config_pins[s.name.replace('-', '_')])}"
                    ]
                }
                collected_run_exports.append(s.run_exports_info)
            else:
                path = Path(pkg_cache).joinpath(
                    final_triple, "info", "run_exports.json",
                )
                if path.exists():
                    with open(path) as fi:
                        run_exports_info = json.load(fi)
                        s.run_exports_info = run_exports_info
                        collected_run_exports.append(run_exports_info)
                else:
                    s.run_exports_info = None

        def append_or_replace(env, spec):
            spec = CondaBuildSpec(spec)
            name = spec.name
            spec.from_run_export = True
            for idx, r in enumerate(self.requirements[env]):
                if r.final_name == name:
                    self.requirements[env][idx] = spec
                    return
            self.requirements[env].append(spec)

        if env == "build":
            for rex in collected_run_exports:
                if "strong" in rex:
                    for r in rex["strong"]:
                        append_or_replace("host", r)
                        append_or_replace("run", r)
                if "weak" in rex:
                    for r in rex["weak"]:
                        append_or_replace("host", r)

        if env == "host":
            for rex in collected_run_exports:
                if "strong" in rex:
                    for r in rex["strong"]:
                        append_or_replace("run", r)
                if "weak" in rex:
                    for r in rex["weak"]:
                        append_or_replace("run", r)

    def _solve_env(self, env, all_outputs):
        if self.requirements.get(env):
            console.print(f"Finalizing [yellow]{env}[/yellow] for {self.name}")
            specs = self.requirements[env]
            for s in specs:
                if s.is_pin:
                    s.eval_pin_subpackage(all_outputs)
                if env == "run" and s.is_pin_compatible:
                    s.eval_pin_compatible(
                        self.requirements["build"], self.requirements["host"]
                    )

            # save finalized requirements in data for usage in metadata
            self.data["requirements"][env] = [s.final for s in self.requirements[env]]

            spec_map = {s.final_name: s for s in specs}
            specs = [str(x) for x in specs]

            pkg_cache = PackageCacheData.first_writable().pkgs_dir
            if env in ("host", "run") and not self.config.subdirs_same:
                subdir = self.config.host_subdir
            else:
                subdir = self.config.build_subdir

            solver, pkg_cache = get_solver(subdir)
            t = solver.solve(specs, [pkg_cache])

            _, install_pkgs, _ = t.to_conda()
            for _, _, p in install_pkgs:
                p = json.loads(p)
                if p["name"] in spec_map:
                    spec_map[p["name"]].final_version = (
                        p["version"],
                        p["build_string"],
                    )
                    spec_map[p["name"]].channel = p["channel"]
                else:
                    cbs = CondaBuildSpec(f"{p['name']}")
                    cbs.is_transitive_dependency = True
                    cbs.final_version = (p["version"], p["build_string"])
                    cbs.channel = p["channel"]
                    self.requirements[env].append(cbs)

            self.transactions[env] = {
                "transaction": t,
                "pkg_cache": pkg_cache,
            }

            downloaded = t.fetch_extract_packages(
                pkg_cache, solver.repos + list(solver.local_repos.values()),
            )
            if not downloaded:
                raise RuntimeError("Did not succeed in downloading packages.")

            if env in ("build", "host"):
                self.propagate_run_exports(env, self.transactions[env]["pkg_cache"])

    def set_final_build_id(self, meta):
        self.final_build_id = meta.build_id()
        # we need to evaluate run_exports pin_subpackage here...
        if self.sections["build"].get("run_exports"):
            run_exports_list = self.sections["build"]["run_exports"]
            for x in run_exports_list:
                if self.name.endswith("-static") and self.name.startswith(x.name):
                    # remove self-run-exports for static packages
                    run_exports_list[:] = []
                else:
                    x.eval_pin_subpackage([self])

                x.eval_pin_subpackage([self])
            run_exports_list[:] = [x.final for x in run_exports_list]
            self.data["build"]["run_exports"] = run_exports_list

    def finalize_solve(self, all_outputs):

        self._solve_env("build", all_outputs)
        self._solve_env("host", all_outputs)
        self._solve_env("run", all_outputs)

        # TODO figure out if we can avoid this?!
        if self.config.variant.get("python") is None:
            for r in self.requirements["build"] + self.requirements["host"]:
                if r.name == "python":
                    self.config.variant["python"] = r.final_version[0]

        if self.config.variant.get("python") is None:
            self.config.variant["python"] = ".".join(
                [str(v) for v in sys.version_info[:3]]
            )

        self.variant = self.config.variant
