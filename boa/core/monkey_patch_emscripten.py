import os
import sys


def patch():
    ###############################################
    # CONDA MONKEY-PATCH
    ###############################################
    from conda.base import constants

    KNOWN_SUBDIRS = PLATFORM_DIRECTORIES = (
        "noarch",
        "linux-32",
        "linux-64",
        "linux-aarch64",
        "linux-armv6l",
        "linux-armv7l",
        "linux-ppc64",
        "linux-ppc64le",
        "linux-s390x",
        "osx-64",
        "osx-arm64",
        "win-32",
        "win-64",
        "zos-z",
        "emscripten-32",
    )
    constants.KNOWN_SUBDIRS = KNOWN_SUBDIRS
    constants.PLATFORM_DIRECTORIES = PLATFORM_DIRECTORIES

    ###############################################
    # CONDA-BUILD MONKEY-PATCH
    ###############################################

    from conda_build import utils, variants, environ
    from conda_build.conda_interface import non_x86_linux_machines
    from conda_build import metadata
    from conda_build.features import feature_list

    def ns_cfg(config):
        # Remember to update the docs of any of this changes
        plat = config.host_subdir
        d = dict(
            linux=plat.startswith("linux-"),
            linux32=bool(plat == "linux-32"),
            linux64=bool(plat == "linux-64"),
            arm=plat.startswith("linux-arm"),
            osx=plat.startswith("osx-"),
            emscripten=plat.startswith("emscripten-"),
            emscripten32=bool(plat == "emscripten-32"),
            emscripten64=bool(plat == "emscripten-64"),
            unix=plat.startswith(("linux-", "osx-", "emscripten-")),
            win=plat.startswith("win-"),
            win32=bool(plat == "win-32"),
            win64=bool(plat == "win-64"),
            x86=plat.endswith(("-32", "-64")),
            x86_64=plat.endswith("-64"),
            os=os,
            environ=os.environ,
            nomkl=bool(int(os.environ.get("FEATURE_NOMKL", False))),
        )

        defaults = variants.get_default_variant(config)
        py = config.variant.get("python", defaults["python"])
        # there are times when python comes in as a tuple
        if not hasattr(py, "split"):
            py = py[0]
        # go from "3.6 *_cython" -> "36"
        # or from "3.6.9" -> "36"
        py = int("".join(py.split(" ")[0].split(".")[:2]))

        d["build_platform"] = config.build_subdir

        d.update(
            dict(
                py=py,
                py3k=bool(30 <= py < 40),
                py2k=bool(20 <= py < 30),
                py26=bool(py == 26),
                py27=bool(py == 27),
                py33=bool(py == 33),
                py34=bool(py == 34),
                py35=bool(py == 35),
                py36=bool(py == 36),
            )
        )

        np = config.variant.get("numpy")
        if not np:
            np = defaults["numpy"]
            if config.verbose:
                utils.get_logger(__name__).warn(
                    "No numpy version specified in conda_build_config.yaml.  "
                    "Falling back to default numpy value of {}".format(
                        defaults["numpy"]
                    )
                )
        d["np"] = int("".join(np.split(".")[:2]))

        pl = config.variant.get("perl", defaults["perl"])
        d["pl"] = pl

        lua = config.variant.get("lua", defaults["lua"])
        d["lua"] = lua
        d["luajit"] = bool(lua[0] == "2")

        for machine in non_x86_linux_machines:
            d[machine] = bool(plat.endswith("-%s" % machine))

        for feature, value in feature_list:
            d[feature] = value
        d.update(os.environ)

        # here we try to do some type conversion for more intuitive usage.  Otherwise,
        #    values like 35 are strings by default, making relational operations confusing.
        # We also convert "True" and things like that to booleans.
        for k, v in config.variant.items():
            if k not in d:
                try:
                    d[k] = int(v)
                except (TypeError, ValueError):
                    if isinstance(v, str) and v.lower() in ("false", "true"):
                        v = v.lower() == "true"
                    d[k] = v
        return d

    metadata.ns_cfg = ns_cfg

    DEFAULT_SUBDIRS = {
        "linux-64",
        "linux-32",
        "linux-s390x",
        "linux-ppc64",
        "linux-ppc64le",
        "linux-armv6l",
        "linux-armv7l",
        "linux-aarch64",
        "win-64",
        "win-32",
        "osx-64",
        "osx-arm64",
        "zos-z",
        "noarch",
        "emscripten-32",
    }

    utils.DEFAULT_SUBDIRS = DEFAULT_SUBDIRS

    def get_shlib_ext(host_platform):
        # Return the shared library extension.
        if host_platform.startswith("win"):
            return ".dll"
        elif host_platform in ["osx", "darwin"]:
            return ".dylib"
        elif host_platform.startswith("linux") or host_platform.startswith(
            "emscripten"
        ):
            return ".so"
        elif host_platform == "noarch":
            # noarch packages should not contain shared libraries, use the system
            # platform if this is requested
            return get_shlib_ext(sys.platform)
        else:
            raise NotImplementedError(host_platform)

    environ.get_shlib_ext = get_shlib_ext
