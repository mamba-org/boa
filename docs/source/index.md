Welcome to boa's documentation!
===============================

Boa is a package build tool for `.conda` packages. As such, it is an alternative to `conda-build`, but uses the more recently developed `mamba` package installer as a "backend". Additionally, boa implements a new and improved recipe spec, and also implements a `conda mambabuild ...` command to build "legacy" recipes with the faster mamba backend. This can help when debugging recipes, as the output of the mamba solver is often more readable than the one from conda.

```{toctree}
:maxdepth: 2
:caption: "Contents:"

getting_started
mambabuild
recipe_spec
```


Indices and tables
==================

* {ref}`Index <genindex>`
* {ref}`Search <search>`

<!-- * {ref}`modindex <modindex>` -->
