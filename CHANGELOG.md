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
