![boa header image](docs/assets/boa_header.png)

## The Fast Conda and Mamba Package Builder

<table>
<thead align="center" cellspacing="10">
  <tr>
    <th colspan="3" align="center" border="">part of mamba-org</th>
  </tr>
</thead>
<tbody>
  <tr background="#FFF">
    <td align="center">Package Manager <a href="https://github.com/mamba-org/mamba">mamba</a></td>
    <td align="center">Package Server <a href="https://github.com/mamba-org/quetz">quetz</a></td>
    <td align="center">Package Builder <a href="https://github.com/mamba-org/boa">boa</a></td>
  </tr>
</tbody>
</table>

# boa, the fast build tool for conda packages

```
Note: boa is still a work-in-progress. 
```

**boa** is a package builder for conda packages. </br>
It largely re-uses the `conda-build` infrastructure, except for some parts. For example the 'solving stage' which, in Boa, is done using `mamba`, the fast `conda`-alternative. Learn more about `mamba` [here](https://github.com/mamba-org/mamba#readme).

We are also working towards a new "meta.yaml" format in the `boa/cli/render.py` source file. Read more about it [here](https://boa-build.readthedocs.io/en/latest/recipe_spec.html). </br>
The new "meta.yaml" format is still a work-in-progress and might not work as expected.

The discussions about this new `meta.yaml` format take place [here](https://hackmd.io/axI1tQdwQB2pTJKt5XdY5w). We encourage you to participate. 

The short-term goal for boa is to parse the new version spec, and produce a `conda_build.MetaData` class in Python that describes how to assemble the final package.

[![asciicast](https://asciinema.org/a/HBduIi9TgdFgS3zV7mB3h0KpN.svg)](https://asciinema.org/a/HBduIi9TgdFgS3zV7mB3h0KpN)


We have these tools included with boa:

```
conda mambabuild my_recipe_folder
``` 
This is equivalent to running `conda build my_recipe_folder` but using mamba as a solver.

```
boa render my_recipe_folder
```  
"Render" a recipe. (Note that you must use the non-final v2 syntax. Check the recipes folder for examples.)

```
boa build my_recipe_folder  
```
Runs a "build" of the v2 recipe.

### Dev Installation

Install the boa dependencies:
```
mamba install "conda-build>=3.20" colorama pip ruamel ruamel.yaml rich -c conda-forge
```

Now install boa:
```
pip install -e .
```
### Documentation

The boa documentation can be found [here](https://boa-build.readthedocs.io/en/latest/).

### License

We use a shared copyright model that enables all contributors to maintain the copyright on their contributions.

This software is licensed under the BSD-3-Clause license. See the LICENSE file for details.
