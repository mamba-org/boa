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
