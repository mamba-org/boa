#!/usr/bin/env python
import os
from setuptools import setup

here = os.path.dirname(os.path.abspath(__file__))

version_ns = {}
with open(os.path.join(here, "boa", "_version.py")) as f:
    exec(f.read(), {}, version_ns)

__version__ = version_ns["__version__"]

deps = [
    "pyyaml",
    "jinja2",
    "setuptools",
    "colorama",
    "mamba",
    "rich",
    "ruamel.yaml",
    "tabulate",
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
    packages=["boa", "boa.cli"],
    entry_points={
        "console_scripts": [
            "conda-mambabuild = boa.cli.mambabuild:main",
            "boa = boa.cli.boa:main",
        ]
    },
    install_requires=deps,
    package_data={"boa": []},
)
