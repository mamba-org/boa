#!/usr/bin/env python
import sys
from setuptools import setup

# deps = ['conda', 'requests', 'filelock', 'pyyaml', 'jinja2', 'pkginfo',
#         'beautifulsoup4', 'chardet', 'pytz', 'tqdm', 'psutil', 'six',
#         'libarchive-c', 'setuptools']
deps = ['pyyaml', 'jinja2', 'setuptools', 'colorama']

setup(
    name="boa",
    version="0.0.1",
    # cmdclass=versioneer.get_cmdclass(),
    author="QuantStack",
    author_email="info@quantstack",
    url="https://github.com/quantstack/boa",
    license="BSD 3-clause",
    classifiers=[],
    description="tools for building conda packages",
    long_description=open('README.md').read(),
    packages=['boa', 'boa.cli'],
    entry_points={
        'console_scripts': [
            'conda-mambabuild = boa.cli.mambabuild:main',
            'boa = boa.cli.boa:main'
        ]
    },
    install_requires=deps,
    package_data={'boa': []},
)
