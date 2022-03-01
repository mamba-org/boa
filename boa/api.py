from pathlib import Path

from boa.core.render import render as core_render
from boa.core.utils import get_config
from boa.core.run_build import to_build_tree, get_dependency_variants
from boa.core.metadata import MetaData

# os.path.join(forge_dir, forge_config["recipe_dir"]),
# platform=platform,
# arch=arch,
# ignore_system_variants=True,
# variants=migrated_combined_variant_spec,
# permit_undefined_jinja=True,
# finalize=False,
# bypass_env_check=True,
# channel_urls=forge_config.get("channels", {}).get(
#     "sources", []
# ),


def render(
    recipe_dir,
    platform,
    arch,
    ignore_system_variants=True,
    variants=None,
    permit_undefined_jinja=True,
    finalize=False,
    bypass_env_check=True,
    channel_urls=None,
    selected_features=None,
):

    if not channel_urls:
        channel_urls = []
    if not selected_features:
        selected_features = dict()

    variant = {"target_platform": platform}
    # cbc_file = Path(recipe_dir) / "conda_build_config.yaml"
    cbc, config = get_config(recipe_dir, variant, [])
    cbc["target_platform"] = [variant["target_platform"]]

    recipe_path = Path(recipe_dir) / "recipe.yaml"
    ydoc = core_render(recipe_path, config)

    # this takes in all variants and outputs, builds a dependency tree and returns
    # the final metadata

    assembled_variants = {}
    # if we have a outputs section, use that order the outputs
    if ydoc.get("outputs"):
        for o in ydoc["outputs"]:
            # inherit from global package
            pkg_meta = {}
            pkg_meta.update(ydoc["package"])
            pkg_meta.update(o["package"])
            o["package"] = pkg_meta

            build_meta = {}
            build_meta.update(ydoc.get("build"))
            build_meta.update(o.get("build") or {})
            o["build"] = build_meta

            o["selected_features"] = selected_features

            assembled_variants[o["package"]["name"]] = get_dependency_variants(
                o.get("requirements", {}), variants, config
            )
    else:
        # we only have one output
        assembled_variants[ydoc["package"]["name"]] = get_dependency_variants(
            ydoc.get("requirements", {}), variants, config
        )

    print("Selected variants: ", assembled_variants)

    sorted_outputs = to_build_tree(
        ydoc, assembled_variants, config, variants, selected_features
    )

    metas = []
    for output in sorted_outputs:
        meta = MetaData(recipe_path, output)
        print(output)
        meta.config.variants = {}
        meta.config.input_variants = variants
        # meta.config.variants =
        metas.append((meta, None, None))
    print(metas)
    return metas
    # o.set_final_build_id(meta)
