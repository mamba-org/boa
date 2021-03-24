The boa recipe spec
===================

Boa implements a new recipe spec, different from the traditional "meta.yaml" used in `conda-build`. A boa recipe has to be stored as `recipe.yaml` file.

History
-------

A discussion was started on what a new recipe spec could or should look like. The fragments of this discussion can be found here: https://github.com/mamba-org/conda-specs/blob/master/proposed_specs/recipe.md
The reason for a new spec are:

- Make it easier to parse ("pure yaml"). conda-build uses a mix of comments and jinja to achieve a great deal of flexibility, but it's hard to parse the recipe with a computer
- iron out some inconsistencies around multiple outputs (build vs. build/script and more)
- remove any need for recursive parsing & solving

Spec
----

The boa spec has the following parts:

- `context`: to set up variables that can later be used in Jinja expressions
- `package`: defines name, version etc. of the top-level package
- `source`: points to the sources that need to be downloaded in order to build the recipe
- `build`: defines how to build the recipe and what build number to use
- `requirements`: defines requirements of the top-level package
- `test`: defines tests for the top-level package
- `outputs`: a recipe can have multiple outputs. Each output can and should have a `package`, `requirements` and `test` section

Examples
--------

```yaml
# this sets up the context variables (name and version) that are later
# used in Jinja expressions
context:
  version: 1.1.0
  name: imagesize

# top level package information (name and version)
package:
  name: {{ name }}'
  version: '{{ version }}'

# location to get the source from 
source:
  url: https://pypi.io/packages/source/{{ name[0] }}/{{ name }}/{{ name }}-{{ version }}.tar.gz
  sha256: f3832918bc3c66617f92e35f5d70729187676313caa60c187eb0f28b8fe5e3b5

# build number (should be incremented if a new build is made, but version is not incrementing)
build:
  number: 1
  script: python -m pip install --no-deps --ignore-installed .

# the requirements at build and runtime
requirements:
  host:
    - python
    - pip
  run:
    - python

# tests to validate that the package works as expected
test:
  imports:
    - imagesize

# information about the package
about:
  home: https://github.com/shibukawa/imagesize_py
  license: MIT
  summary: 'Getting image size from png/jpeg/jpeg2000/gif file'
  description: |
    This module analyzes jpeg/jpeg2000/png/gif image header and
    return image size.
  dev_url: https://github.com/shibukawa/imagesize_py
  doc_url: https://pypi.python.org/pypi/imagesize
  doc_source_url: https://github.com/shibukawa/imagesize_py/blob/master/README.rst

# the below is conda-forge specific!
extra:
  recipe-maintainers:
    - somemaintainer

```


### Package section

Specifies package information.

```yaml
package:
  name: bsdiff4
  version: "2.1.4"
```

- **name**: The lower case name of the package. It may contain "-", but no spaces.
- **version**: The version number of the package. Use the PEP-386 verlib conventions. Cannot contain "-". YAML interprets version numbers such as 1.0 as floats, meaning that 0.10 will be the same as 0.1. To avoid this, put the version number in quotes so that it is interpreted as a string.




