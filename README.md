# boa, the fast build tool for conda packages

**boa** is very much a work-in-progress right now.

Boa is a package builder for conda packages. It is re-using a lot of the `conda-build` infrastructure, but replaces some parts, namely the solving stage is done using `mamba`, the fast C++ `conda`-alternative based on `libsolv`.

We are also working towards a new "meta.yaml" format in the `boa/cli/render.py` source file. 
This is absolutely a work-in-progress, and you should not expect it to work or be stable.

You can find (and participate!) in discussions regarding the new `meta.yaml` format in this hackmd: https://hackmd.io/axI1tQdwQB2pTJKt5XdY5w

The shortterm-goal for boa is to parse the new version spec, and produce a `conda_build.MetaData` class in Python that describes how to to assemble the final package.

We have two small tools included with boa:

```
boa my_recipe_folder  # this is equivalent to running conda build my_recipe_folder
boar my_recipe.yaml  # this is running a "render" of the recipe
```
