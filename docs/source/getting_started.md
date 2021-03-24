Getting started with boa
========================

Installation
------------

You can install boa from conda-forge:

```
# using mamba
mamba install boa -c conda-forge

# using conda
conda install boa -c conda-forge
```

Basic Usage
-----------

Boa implements two main commands:

- `boa build ...`
- `conda mambabuild ...`

### mambabuild

The `conda mambabuild` command is a "drop-in" replacement for the `conda build` command and uses the same recipes and configuration files as conda-build. The only difference is that it swaps out the package resolver to use `mamba` instead of conda, which makes environment resolution faster, and can help in the debugging of resolution problems as the error messages from mamba are usually easier to understand than the ones from conda. 

To use `conda mambabuild` just replace your existing command line usage of `conda build ...` with `conda mambabuild ...` (all the same arguments should function properly). For more information on the recipe spec and conda_build_config.yaml usage, please refer to the [conda-build documentation](https://docs.conda.io/projects/conda-build/en/latest/).

### boa build

The boa package also implements a new recipe spec (described under `spec`). To build a package that follows this new convention, just use 

```
boa build mypackage
```

The `boa build` command does not yet support all flags that can be used with conda-build and is still very much under active development.