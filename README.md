![boa header image](docs/assets/boa_header.png)

# boa, the fast build tool for conda packages

**boa** is very much a work-in-progress right now.

**boa** is a package builder for conda packages. It is re-using a lot of the `conda-build` infrastructure, but replaces some parts. Specifically the solving stage is done using `mamba`, the fast `conda`-alternative (implemented in C++ and based on `libsolv`).

We are also working towards a new "meta.yaml" format in the `boa/cli/render.py` source file. 
This is totally a work-in-progress, and you should not expect it to work or to be stable.

You can find (and participate!) in discussions regarding the new `meta.yaml` format in this hackmd: https://hackmd.io/axI1tQdwQB2pTJKt5XdY5w

The shortterm-goal for boa is to parse the new version spec, and produce a `conda_build.MetaData` class in Python that describes how to to assemble the final package.

We have two small tools included with boa:

```
boa my_recipe_folder  # this is equivalent to running conda build my_recipe_folder
boar my_recipe.yaml  # this is running a "render" of the recipe
```
