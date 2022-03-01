import itertools
import copy

if False:  # TYPE_CHECKING
    from typing import OrderedDict

from boa.core.conda_build_spec import CondaBuildSpec
from boa.core.config import boa_config
from boa.core.render import ensure_list
from boa.core.utils import get_sys_vars_stubs

from conda_build.variants import get_default_variant
from conda.models.match_spec import MatchSpec
import conda_build.jinja_context

console = boa_config.console


def _assemble_variants(
    env, conda_build_config, config, variants, sys_var_stubs, default_variant
):
    specs = {}

    for var in sys_var_stubs:
        if var in conda_build_config:
            variants[var] = ensure_list(conda_build_config[var])

    for s in env:
        spec = CondaBuildSpec(s)
        specs[spec.name] = spec

    for n, cb_spec in specs.items():
        if cb_spec.is_compiler:
            # This is a compiler package
            _, lang = cb_spec.raw.split()
            compiler = conda_build.jinja_context.compiler(lang, config)
            cb_spec.final = compiler
            config_key = f"{lang}_compiler"
            config_version_key = f"{lang}_compiler_version"

            if conda_build_config.get(config_key):
                variants[config_key] = conda_build_config[config_key]
            if conda_build_config.get(config_version_key):
                variants[config_version_key] = conda_build_config[config_version_key]

        # Note: as a historical artifact we __have to__ use underscore-replaced
        # names here!
        variant_key = n.replace("-", "_")
        vlist = None
        if variant_key in conda_build_config:
            vlist = conda_build_config[variant_key]
        elif variant_key in default_variant:
            vlist = [default_variant[variant_key]]
        if vlist:
            # we need to check if v matches the spec
            if cb_spec.is_simple:
                variants[variant_key] = vlist
            elif cb_spec.is_pin:
                # ignore variants?
                pass
            else:
                # check intersection of MatchSpec and variants
                ms = MatchSpec(cb_spec.raw)
                filtered = []
                for var in vlist:
                    vsplit = var.split()
                    if len(vsplit) == 1:
                        p = {
                            "name": n,
                            "version": vsplit[0],
                            "build_number": 0,
                            "build": "",
                        }
                    elif len(vsplit) == 2:
                        p = {
                            "name": n,
                            "version": var.split()[0],
                            "build": var.split()[1],
                            "build_number": 0,
                        }
                    else:
                        raise RuntimeError("Check your conda_build_config")

                    if ms.match(p):
                        filtered.append(var)
                    else:
                        console.print(
                            f"Configured variant ignored because of the recipe requirement:\n  {cb_spec.raw} : {var}\n"
                        )

                if len(filtered):
                    variants[variant_key] = filtered

    return variants


def get_dependency_variants(variant_keys, conda_build_config, config):
    variants = {}
    default_variant = get_default_variant(config)

    variants["target_platform"] = conda_build_config.get(
        "target_platform", [default_variant["target_platform"]]
    )

    if conda_build_config["target_platform"] == [None]:
        variants["target_platform"] = [default_variant["target_platform"]]

    config.variant["target_platform"] = variants["target_platform"][0]

    sys_var_stubs = get_sys_vars_stubs(config.variant["target_platform"])

    v = _assemble_variants(
        variant_keys,
        conda_build_config,
        config,
        variants,
        sys_var_stubs,
        default_variant,
    )
    return v


def apply_variants(output, variants, cbc):

    final_outputs = []

    # this is all a bit hacky ... will have to clean that up eventually
    # variant_name = output.name

    # # need to strip static away from output name... :/
    # static_feature = output.selected_features.get("static", False)

    # if static_feature and output.name.endswith("-static"):
    #     variant_name = output.name[: -len("-static")]
    # stop hacky ti hacky

    # zip keys need to be contracted
    zipped_keys = cbc.get("zip_keys", [])

    if variants:
        vzipped = copy.copy(variants)
        zippers = {}
        for zkeys in zipped_keys:
            # we check if our variant contains keys that need to be zipped
            if sum(k in variants for k in zkeys) > 1:
                filtered_zip_keys = [k for k in variants if k in zkeys]

                zkname = "__zip_" + "_".join(filtered_zip_keys)

                zklen = None
                for zk in filtered_zip_keys:
                    if zk not in cbc:
                        raise RuntimeError(
                            f"Trying to zip keys, but not all zip keys found on conda-build-config {zk}"
                        )

                    zkl = len(cbc[zk])
                    if not zklen:
                        zklen = zkl

                    if zklen and zkl != zklen:
                        raise RuntimeError(
                            f"Trying to zip keys, but not all zip keys have the same length {zkeys}"
                        )

                vzipped[zkname] = [str(i) for i in range(zklen)]
                zippers[zkname] = {zk: cbc[zk] for zk in filtered_zip_keys}

                for zk in filtered_zip_keys:
                    del vzipped[zk]

        combos = []
        differentiating_keys = []
        for k, vz in vzipped.items():
            if len(vz) > 1:
                differentiating_keys.append(k)
            combos.append([(k, x) for x in vz])

        all_combinations = tuple(itertools.product(*combos))
        all_combinations = [dict(x) for x in all_combinations]

        # unzip the zipped keys
        unzipped_combinations = []
        for c in all_combinations:
            unz_combo = {}
            for vc in c:
                if vc.startswith("__zip_"):
                    ziptask = zippers[vc]
                    zipindex = int(c[vc])
                    for zippkg in ziptask:
                        unz_combo[zippkg] = ziptask[zippkg][zipindex]
                    if vc in differentiating_keys:
                        differentiating_keys.remove(vc)
                        differentiating_keys.extend(zippers[vc].keys())
                else:
                    unz_combo[vc] = c[vc]

            unzipped_combinations.append(unz_combo)

        for c in unzipped_combinations:
            x = output.apply_variant(c, differentiating_keys)
            final_outputs.append(x)
    else:
        x = output.apply_variant({})
        final_outputs.append(x)
    return final_outputs


def add_prev_steps(output, variant, prev_outputs, variants):
    requirements = output.all_requirements()
    for k in requirements:
        if k.is_pin_subpackage and k.pin.exact:
            # add additional variants for each output of the subpackage
            add_exact_pkgs = []
            for o in prev_outputs:
                if o.name == k.name:
                    add_exact_pkgs.append(o)

            if not output.requirements.get("virtual"):
                output.requirements["virtual"] = []
            output.requirements["virtual"] += o.differentiating_keys
            variant.update(variants[k.name])


def variant_overlap(a, b):
    overlap = 0
    for ak, av in a.items():
        if b.get(ak) == av:
            overlap += 1
    return overlap


def get_variants(sorted_outputs: "OrderedDict", cbc: dict, config):
    variants = {}

    final_outputs = []
    for name, output in sorted_outputs.items():
        variants[name] = get_dependency_variants(output.variant_keys(), cbc, config)
        add_prev_steps(output, variants[name], final_outputs, variants)
        final_outputs += apply_variants(output, variants[name], cbc)

    # create a proper graph
    for output in final_outputs:
        # if we have pin_subpackage(exact) packages, we need to find those
        # with the largest common variant to connect them
        # same for the empty build steps
        parent_steps = []

        for required_step in output.required_steps:
            max_overlap = 0
            best_step_variant = None

            for f in final_outputs:
                overlap = variant_overlap(f.variant, output.variant)
                if f.name == required_step and overlap > max_overlap:
                    best_step_variant = f
                    max_overlap = overlap

            parent_steps.append(best_step_variant)

        requirements = output.all_requirements()
        for k in requirements:
            max_overlap = 0
            best_step_variant = None

            if k.is_pin_subpackage and k.pin.exact:
                for f in final_outputs:
                    overlap = variant_overlap(f.variant, output.variant)
                    if f.name == k.name and overlap > max_overlap:
                        best_step_variant = f
                        max_overlap = overlap

                parent_steps.append(best_step_variant)

        output.parent_steps = parent_steps

    return variants, final_outputs
