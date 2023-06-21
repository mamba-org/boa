0.15.1 (June 21, 2023)
======================

 - Disable error messages for now to see if that fixes segfault issues observed on conda-forge (https://github.com/conda-forge/conda-forge.github.io/issues/1960) #352

0.15.0 (May 17, 2023)
=====================

- Run export types by @wolfv in https://github.com/mamba-org/boa/pull/324
- Fix pin_compatible by @ruben-arts in https://github.com/mamba-org/boa/pull/325
- emscripten 32 - conditional monkeypatch by @wolfv in https://github.com/mamba-org/boa/pull/333
- Fix #322 by adding "about" section in Output constructor by @moqmar in https://github.com/mamba-org/boa/pull/327
- add support for the new error messages by @jaimergp in https://github.com/mamba-org/boa/pull/340
- Switch to setup-micromamba by @pavelzw in https://github.com/mamba-org/boa/pull/339
- Support passing build variants from cli by @frmdstryr in https://github.com/mamba-org/boa/pull/337
- Allow for multiple license files by @dhirschfeld in https://github.com/mamba-org/boa/pull/342
- Make it possible to include the recipe.yaml inside a pyproject.toml by @moqmar in https://github.com/mamba-org/boa/pull/345
- Implement separate "boa test" command to fix #326 by @moqmar in https://github.com/mamba-org/boa/pull/343
- fix: support strict channel priorities by @johanneskoester in https://github.com/mamba-org/boa/pull/347

0.14.0 (November 10, 2022)
==========================

- [boa] fix schema mistake (destination should be folder in schema) (thanks @alexshagiev) #316
- [boa] For issue 313 use os.path.normpath not os.normpath when setting git_url. (thanks @ericvoltron) #314
- [boa, mambabuild] update precommit files (thanks @mariusvniekerk) #315

0.13.0 (November 10, 2022)
==========================

- [boa] compatibility with mamba 1.0.0
- [mambabuild] dependency error parse improvements (thanks @mbargull) #306
- [mambabuild] fix parsing problems when test_downstream is called (thanks @isuruf) #301
- [boa] Add environ to context and proper build/script_env handling #299


0.12.0 (October 5, 2022)
========================

- [boa] compatibility with mamba 0.27.0
- [boa] Fix documentation and docstrings (thanks @LunarLanding and @martinRenou)
- [boa] Allow channel pinnings in boa build (thanks @mariusvniekerk)
- [boa] Support additional conda build command line arguments (thanks @mariusvniekerk)
- [boa] Fix propagation of build strings in dependencies (thanks @alexshagiev)
- [boa] Proper run exports handling
- [boa] Fix error in test when include_recipe is false (thanks @frmdstryr)

0.11.0 (April 27, 2022)
=======================

- [boa] compatibility with mamba 0.23.0
- [boa] fix an AttributeError if there is no pin (thanks @TobiasFischer) #268

0.10.0 (March 18, 2022)
=======================

- [boa] add `boa --version`
- [boa] add more docs and vastly improved new recipe schema, render recipe schema in docs
- [boa] add version from top-level to outputs to make validation pass
- [boa] move CondaBuildSpec class to it's own file
- [boa] save properly rendered recipe into final package
- [boa] implement build steps and variant inheritance logic
- [boa] read and respect binary_relocation value (thanks @frmdstryr)
- [boa] add debug assert messages (thanks @dhirschfeld)


0.9.0 (February 11, 2022)
=========================

- [boa] add support for `build.py` Python based build scripts (also check out [`bitfurnace`](https://github.com/mamba-org/bitfurnace))
- [boa,mambabuild] fix compatibility with mamba 0.21.*

0.8.2 (January 31, 2022)
========================

- [boa] fix multi-output
- [boa] fix keep run_export and existing spec when existing spec is not simple
- [mambabuild] allow testing multiple recipes (thanks @gabm)
