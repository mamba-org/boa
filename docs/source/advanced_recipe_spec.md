#### Python.app

If osx_is_app is set, entry points use `python.app` instead of
Python in macOS. The default is `False`.

```yaml
build:
  osx_is_app: true
```

#### Preserve Python egg directory

This is needed for some packages that use features specific to
setuptools. The default is `false`.

```yaml
build:
  preserve_egg_dir: true
```

#### Skip compiling some .py files into .pyc files

Some packages ship `.py` files that cannot be compiled, such
as those that contain templates. Some packages also ship `.py`
files that should not be compiled yet, because the Python
interpreter that will be used is not known at build time. In
these cases, conda-build can skip attempting to compile these
files. The patterns used in this section do not need the `**` to
handle recursive paths.

```yaml
build:
  skip_compile_pyc:
    - "*/templates/*.py"          # These should not (and cannot) be compiled
    - "*/share/plugins/gdb/*.py"  # The python embedded into gdb is unknown
```

### No link

A list of globs for files that should always be copied and never soft
linked or hard linked.

```yaml
build:
  no_link:
    - bin/*.py  # Don't link any .py files in bin/
```

### RPATHs

Set which RPATHs are used when making executables relocatable on Linux.
This is a Linux feature that is ignored on other systems. The default is
`lib/`.

```yaml
build:
  rpaths:
    - lib/
    - lib/R/lib/
```

### Force files

Force files to always be included, even if they are already in the
environment from the build dependencies. This may be needed, for
example, to create a recipe for conda itself.

```yaml
build:
  always_include_files:
    - bin/file1
    - bin/file2
```

### Relocation

Advanced features. You can use the following 4 keys to control
relocatability files from the build environment to the installation
environment:

- binary\_relocation.
- has\_prefix\_files.
- binary\_has\_prefix\_files.
- ignore\_prefix\_files.

For more information, see make-relocatable.

### Binary relocation

Whether binary files should be made relocatable using
install\_name\_tool on macOS or patchelf on Linux. The default is
`true`. It also accepts `false`, which indicates no relocation for any
files, or a list of files, which indicates relocation only for listed
files.

```yaml
build:
  binary_relocation: false
```

### Detect binary files with prefix

Binary files may contain the build prefix and need it replaced with the
install prefix at installation time. Conda can automatically identify
and register such files. The default is `true`.

> **note**
>
> The default changed from `false` to `true` in conda build 2.0. Setting
> this to `false` means that binary relocation --- RPATH --- replacement
> will still be done, but hard-coded prefixes in binaries will not be
> replaced. Prefixes in text files will still be replaced.

```yaml
build:
  detect_binary_files_with_prefix: False
```

Windows handles binary prefix replacement very differently than
Unix-like systems such as macOS and Linux. At this time, we are unaware
of any executable or library that uses hardcoded embedded paths for
locating other libraries or program data on Windows. Instead, Windows
follows [DLL search path
rules](https://msdn.microsoft.com/en-us/library/7d83bc18.aspx) or more
natively supports relocatability using relative paths. Because of this,
conda ignores most prefixes. However, pip creates executables for Python
entry points that do use embedded paths on Windows. Conda-build thus
detects prefixes in all files and records them by default. If you are
getting errors about path length on Windows, you should try to disable
detect\_binary\_files\_with\_prefix. Newer versions of Conda, such as
recent 4.2.x series releases and up, should have no problems here, but
earlier versions of conda do erroneously try to apply any binary prefix
replacement.

### Binary has prefix files

By default, conda-build tries to detect prefixes in all files. You may
also elect to specify files with binary prefixes individually. This
allows you to specify the type of file as binary, when it may be
incorrectly detected as text for some reason. Binary files are those
containing NULL bytes.

```yaml
build:
  binary_has_prefix_files:
    - bin/binaryfile1
    - lib/binaryfile2
```

### Text files with prefix files

Text files---files containing no NULL bytes---may contain the build
prefix and need it replaced with the install prefix at installation
time. Conda will automatically register such files. Binary files that
contain the build prefix are generally handled differently---see
bin-prefix---but there may be cases where such a binary file needs to be
treated as an ordinary text file, in which case they need to be
identified.

```yaml
build:
  has_prefix_files:
    - bin/file1
    - lib/file2
```


### Ignore prefix files

Used to exclude some or all of the files in the build recipe from the
list of files that have the build prefix replaced with the install
prefix.

To ignore all files in the build recipe, use:

```yaml
build:
  ignore_prefix_files: True
```

To specify individual filenames, use:

```yaml
build:
  ignore_prefix_files:
    - file1
```

This setting is independent of RPATH replacement. Use the detect-bin
setting to control that behavior.

### Use environment variables

Normally the build script in `build.sh` or `bld.bat` does not pass
through environment variables from the command line. Only environment
variables documented in env-vars are seen by the build script. To
"white-list" environment variables that should be passed through to the
build script:

```yaml
build:
  script_env:
    - MYVAR
    - ANOTHER_VAR
```

If a listed environment variable is missing from the environment seen by
the conda-build process itself, a UserWarning is emitted during the
build process and the variable remains undefined.

Additionally, values can be set by including `=` followed by the desired
value:

```yaml
build:
  script_env:
   - MY_VAR=some value
```

> **note**
>
> Inheriting environment variables can make it difficult for others to
> reproduce binaries from source with your recipe. Use this feature with
> caution or explicitly set values using the `=` syntax.

> **note**
>
> If you split your build and test phases with `--no-test` and `--test`,
> you need to ensure that the environment variables present at build
> time and test time match. If you do not, the package hashes may use
> different values, and your package may not be testable, because the
> hashes will differ.

### Export runtime requirements

Some build or host requirements will impose a runtime requirement. Most
commonly this is true for shared libraries (e.g. libpng), which are
required for linking at build time, and for resolving the link at run
time. With `run_exports` (new in conda-build 3) such a runtime
requirement can be implicitly added by host requirements (e.g. libpng
exports libpng), and with `run_exports/strong` even by build
requirements (e.g. GCC exports libgcc).

```yaml
# meta.yaml of libpng
build:
  run_exports:
    - libpng
```

Here, because no specific kind of `run_exports` is specified, libpng's
`run_exports` are considered "weak." This means they will only apply
when libpng is in the host section, when they will add their export to
the run section. If libpng were listed in the build section, the
`run_exports` would not apply to the run section.

```yaml
# meta.yaml of gcc compiler
build:
  run_exports:
    strong:
      - libgcc
```

Strong `run_exports` are used for things like runtimes, where the same
runtime needs to be present in the host and the run environment, and
exactly which runtime that should be is determined by what's present in
the build section. This mechanism is how we line up appropriate software
on Windows, where we must match MSVC versions used across all of the
shared libraries in an environment.

```yaml
# meta.yaml of some package using gcc and libpng
requirements:
  build:
    - gcc            # has a strong run export
  host:
    - libpng         # has a (weak) run export
    # - libgcc       <-- implicitly added by gcc
  run:
    # - libgcc       <-- implicitly added by gcc
    # - libpng       <-- implicitly added by libpng
```

You can express version constraints directly, or use any of the Jinja2
helper functions listed at extra\_jinja2.

For example, you may use pinning\_expressions to obtain flexible version
pinning relative to versions present at build time:

```yaml
build:
  run_exports:
    - {{ pin_subpackage('libpng', max_pin='x.x') }}
```

With this example, if libpng were version 1.6.34, this pinning
expression would evaluate to `>=1.6.34,<1.7`.

If build and link dependencies need to impose constraints on the run
environment but not necessarily pull in additional packages, then this
can be done by altering the Run\_constrained entries. In addtion to
`weak`/`strong` `run_exports` which add to the `run` requirements,
`weak_constrains` and `strong_constrains` add to the `run_constrained`
requirements. With these, e.g., minimum versions of compatible but not
required packages (like optional plugins for the linked dependency, or
certain system attributes) can be expressed:

```yaml
requirements:
  build:
    - build-tool                 # has a strong run_constrained export
  host:
    - link-dependency            # has a weak run_constrained export
  run:
  run_constrained:
    # - system-dependency >=min  <-- implicitly added by build-tool
    # - optional-plugin >=min    <-- implicitly added by link-dependency
```

Note that `run_exports` can be specified both in the build section and
on a per-output basis for split packages.

`run_exports` only affects directly named dependencies. For example, if
you have a metapackage that includes a compiler that lists
`run_exports`, you also need to define `run_exports` in the metapackage
so that it takes effect when people install your metapackage. This is
important, because if `run_exports` affected transitive dependencies,
you would see many added dependencies to shared libraries where they are
not actually direct dependencies. For example, Python uses bzip2, which
can use `run_exports` to make sure that people use a compatible build of
bzip2. If people list python as a build time dependency, bzip2 should
only be imposed for Python itself and should not be automatically
imposed as a runtime dependency for the thing using Python.

The potential downside of this feature is that it takes some control
over constraints away from downstream users. If an upstream package has
a problematic `run_exports` constraint, you can ignore it in your recipe
by listing the upstream package name in the `build/ignore_run_exports`
section:

```yaml
build:
  ignore_run_exports:
    - libstdc++
```

You can also list the package the `run_exports` constraint is coming
from using the `build/ignore_run_exports_from` section:

```yaml
build:
  ignore_run_exports_from:
    - {{ compiler('cxx') }}
```

### Export runtime requirements

Some build or host requirements will impose a runtime requirement. Most
commonly this is true for shared libraries (e.g. libpng), which are
required for linking at build time, and for resolving the link at run
time. With `run_exports` (new in conda-build 3) such a runtime
requirement can be implicitly added by host requirements (e.g. libpng
exports libpng), and with `run_exports/strong` even by build
requirements (e.g. GCC exports libgcc).

```yaml
# meta.yaml of libpng
build:
  run_exports:
    - libpng
```

Here, because no specific kind of `run_exports` is specified, libpng's
`run_exports` are considered "weak." This means they will only apply
when libpng is in the host section, when they will add their export to
the run section. If libpng were listed in the build section, the
`run_exports` would not apply to the run section.

```yaml
# meta.yaml of gcc compiler
build:
  run_exports:
    strong:
      - libgcc
```

Strong `run_exports` are used for things like runtimes, where the same
runtime needs to be present in the host and the run environment, and
exactly which runtime that should be is determined by what's present in
the build section. This mechanism is how we line up appropriate software
on Windows, where we must match MSVC versions used across all of the
shared libraries in an environment.

```yaml
# meta.yaml of some package using gcc and libpng
requirements:
  build:
    - gcc            # has a strong run export
  host:
    - libpng         # has a (weak) run export
    # - libgcc       <-- implicitly added by gcc
  run:
    # - libgcc       <-- implicitly added by gcc
    # - libpng       <-- implicitly added by libpng
```

You can express version constraints directly, or use any of the Jinja2
helper functions listed at extra\_jinja2.

For example, you may use pinning\_expressions to obtain flexible version
pinning relative to versions present at build time:

```yaml
build:
  run_exports:
    - {{ pin_subpackage('libpng', max_pin='x.x') }}
```

With this example, if libpng were version 1.6.34, this pinning
expression would evaluate to `>=1.6.34,<1.7`.

If build and link dependencies need to impose constraints on the run
environment but not necessarily pull in additional packages, then this
can be done by altering the Run\_constrained entries. In addtion to
`weak`/`strong` `run_exports` which add to the `run` requirements,
`weak_constrains` and `strong_constrains` add to the `run_constrained`
requirements. With these, e.g., minimum versions of compatible but not
required packages (like optional plugins for the linked dependency, or
certain system attributes) can be expressed:

```yaml
requirements:
  build:
    - build-tool                 # has a strong run_constrained export
  host:
    - link-dependency            # has a weak run_constrained export
  run:
  run_constrained:
    # - system-dependency >=min  <-- implicitly added by build-tool
    # - optional-plugin >=min    <-- implicitly added by link-dependency
```

Note that `run_exports` can be specified both in the build section and
on a per-output basis for split packages.

`run_exports` only affects directly named dependencies. For example, if
you have a metapackage that includes a compiler that lists
`run_exports`, you also need to define `run_exports` in the metapackage
so that it takes effect when people install your metapackage. This is
important, because if `run_exports` affected transitive dependencies,
you would see many added dependencies to shared libraries where they are
not actually direct dependencies. For example, Python uses bzip2, which
can use `run_exports` to make sure that people use a compatible build of
bzip2. If people list python as a build time dependency, bzip2 should
only be imposed for Python itself and should not be automatically
imposed as a runtime dependency for the thing using Python.

The potential downside of this feature is that it takes some control
over constraints away from downstream users. If an upstream package has
a problematic `run_exports` constraint, you can ignore it in your recipe
by listing the upstream package name in the `build/ignore_run_exports`
section:

```yaml
build:
  ignore_run_exports:
    - libstdc++
```

You can also list the package the `run_exports` constraint is coming
from using the `build/ignore_run_exports_from` section:

```yaml
build:
  ignore_run_exports_from:
    - {{ compiler('cxx') }}
```

### Whitelisting shared libraries

The `missing_dso_whitelist` build key is a list of globs for dynamic
shared object (DSO) files that should be ignored when examining linkage
information.

During the post-build phase, the shared libraries in the newly created
package are examined for linkages which are not provided by the
package's requirements or a predefined list of system libraries. If such
libraries are detected, either a warning `--no-error-overlinking` or
error `--error-overlinking` will result.

```yaml
build:
  missing_dso_whitelist:
```

These keys allow additions to the list of allowed libraries.

The `runpath_whitelist` build key is a list of globs for paths which are
allowed to appear as runpaths in the package's shared libraries. All
other runpaths will cause a warning message to be printed during the
build.

```yaml
build:
  runpath_whitelist:
```

### Downstream tests

Knowing that your software built and ran its tests successfully is
necessary, but not sufficient, for keeping whole systems of software
running. To have confidence that a new build of a package hasn't broken
other downstream software, conda-build supports the notion of downstream
testing.

```yaml
test:
  downstreams:
    - some_downstream_pkg
```

This is saying "When I build this recipe, after you run my test suite
here, also download and run some\_downstream\_pkg which depends on my
package." Conda-build takes care of ensuring that the package you just
built gets installed into the environment for testing
some\_downstream\_pkg. If conda-build can't create that environment due
to unsatisfiable dependencies, it will skip those downstream tests and
warn you. This usually happens when you are building a new version of a
package that will require you to rebuild the downstream dependencies.

Downstreams specs are full conda specs, similar to the requirements
section. You can put version constraints on your specs in here:

```yaml
test:
  downstreams:
    - some_downstream_pkg  >=2.0
```

More than one package can be specified to run downstream tests for:

```yaml
test:
  downstreams:
    - some_downstream_pkg
    - other_downstream_pkg
```

However, this does not mean that these packages are tested together.
Rather, each of these are tested for satisfiability with your new
package, then each of their test suites are run separately with the new
package.


App section
-----------

If the app section is present, the package is an app, meaning that it
appears in [Anaconda
Navigator](https://docs.anaconda.com/anaconda/navigator/).

### Entry point

The command that is called to launch the app in Navigator.

```yaml
app:
  entry: ipython notebook
```

### Icon file

The icon file contained in the recipe.

```yaml
app:
  icon: icon_64x64.png
```

### Summary

Summary of the package used in Navigator.

```yaml
app:
  summary:  "The Jupyter Notebook"
```

### Own environment

If `True`, installing the app through Navigator installs into its own
environment. The default is `False`.

```yaml
app:
  own_environment: True
```


### Output type

Conda-build supports creating packages other than conda packages.
Currently that support includes only wheels, but others may come as
demand appears. If type is not specified, the default value is `conda`.

```yaml
requirements:
  build:
    - wheel

outputs:
  - name: name-of-wheel-package
    type: wheel
```

Currently you must include the wheel package in your top-level
requirements/build section in order to build wheels.

When specifying type, the name field is optional and it defaults to the
package/name field for the top-level recipe.

```yaml
requirements:
  build:
    - wheel

outputs:
  - type: wheel
```

> **note**
>
> You must use pip to install Twine in order for this to work.


### Specifying files to include in output

You can specify files to be included in the package in 1 of 2 ways:

-   Explicit file lists.
-   Scripts that move files into the build prefix.

Explicit file lists are relative paths from the root of the build
prefix. Explicit file lists support glob expressions. Directory names
are also supported, and they recursively include contents.

```
outputs:
  - name: subpackage-name
    files:
      - a-file
      - a-folder
      - *.some-extension
      - somefolder/*.some-extension
```


