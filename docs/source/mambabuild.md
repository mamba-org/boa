The conda mambabuild command
============================

Boa comes with an extension to `conda build`: the `conda mambabuild` command. It replaces the `conda` solver with the faster `mamba` solver. To learn more about mamba, visit the [mamba documentation](http://mamba.readthedocs.io).

There are some benefits:

1. Faster solve speed: for complicated environments, mamba is significantly faster than conda and will speed up builds.
2. Better error messages: when you have an un-solvable environment, conda will print a large error message that is often hard to decipher. Mamba prints something that is easier to understand.
3. Full compatibility with existing recipes and the conda-build command line arguments -- since we're "monkeypatching" conda-build and only replace the solver part

To use `conda mambabuild`, just install `boa` and call `conda mambabuild` with the same arguments that would be used with `conda build` (replacing `build` with `mambabuild`).

For example:

```
$ conda mambabuild libsolv -m libsolv/.ci_support/linux_64_.yaml --no-test
```

Please refer to the [conda-build documentation](https://docs.conda.io/projects/conda-build/en/latest/) to learn about all the command line arguments that can be used.