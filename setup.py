#!/usr/bin/env python
from pathlib import Path
from setuptools import setup

here = Path(__file__).parent.absolute()

version_ns = {}
with open(here.joinpath("boa", "_version.py")) as f:
    exec(f.read(), {}, version_ns)

__version__ = version_ns["__version__"]

deps = [
    "jinja2",
    "setuptools",
    "mamba",
    "rich",
    "ruamel.yaml",
    "json5",
    "inotify_simple",
    "prompt-toolkit",
    "joblib",
]

setup(
    name="boa",
    version=__version__,
    author="Wolf Vollprecht",
    author_email="wolf.vollprecht@quantstack",
    url="https://github.com/mamba-org/boa",
    license="BSD 3-clause",
    classifiers=[],
    description="The mamba-powered conda package builder",
    long_description=open("README.md").read(),
    packages=["boa", "boa.cli", "boa.core"],
    entry_points={
        "console_scripts": [
            "conda-mambabuild = boa.cli.mambabuild:main",
            "boa = boa.cli.boa:main",
        ]
    },
    install_requires=deps,
    package_data={"boa": []},
)
