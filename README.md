![boa header image](docs/assets/boa_header.png)

<table>
<thead align="center" cellspacing="10">
  <tr>
    <th colspan="3" align="center" border="">part of snakepit</th>
  </tr>
</thead>
<tbody>
  <tr background="#FFF">
    <td align="center">Package Manager <a href="https://github.com/thesnakepit/mamba">mamba</a></td>
    <td align="center">Package Server <a href="https://github.com/thesnakepit/quetz">quetz</a></td>
    <td align="center">Package Builder <a href="https://github.com/thesnakepit/boa">boa</a></td>
  </tr>
</tbody>
</table>

# boa, the fast build tool for conda packages

**boa** is very much a work-in-progress right now.

[![asciicast](https://asciinema.org/a/GfAKYAS6j3KnKuc8CNjnHolI4.svg)](https://asciinema.org/a/GfAKYAS6j3KnKuc8CNjnHolI4)

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

### Dev Installation

You will have to install the dependencies of boa, and then execute pip to install:

```
mamba install conda-build colorama pip -c conda-forge
# now install boa into your prefix with pip
pip install -e .
```
