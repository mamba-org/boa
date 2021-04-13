The boa recipe spec
===================

Boa implements a new recipe spec, different from the traditional "meta.yaml" used in `conda-build`. A boa recipe has to be stored as `recipe.yaml` file.

History
-------

A discussion was started on what a new recipe spec could or should look like. The fragments of this discussion can be found here: https://github.com/mamba-org/conda-specs/blob/master/proposed_specs/recipe.md
The reason for a new spec are:

- Make it easier to parse ("pure yaml"). conda-build uses a mix of comments and jinja to achieve a great deal of flexibility, but it's hard to parse the recipe with a computer
- iron out some inconsistencies around multiple outputs (build vs. build/script and more)
- remove any need for recursive parsing & solving

Spec
----

The boa spec has the following parts:

- `context`: to set up variables that can later be used in Jinja string interpolation
- `package`: defines name, version etc. of the top-level package
- `source`: points to the sources that need to be downloaded in order to build the recipe
- `build`: defines how to build the recipe and what build number to use
- `requirements`: defines requirements of the top-level package
- `test`: defines tests for the top-level package
- `outputs`: a recipe can have multiple outputs. Each output can and should have a `package`, `requirements` and `test` section

Major differences with conda-build
----------------------------------

- recipe filename is `recipe.yaml`, not `meta.yaml`
- outputs have less complicated behavior, keys are same as top-level recipe (e.g. build/script, not just script), same for package/name, not just name)
- no implicit meta-packages in outputs
- no full Jinja2 support: no conditional or `{% set ...` support, only string interpolation. Variables can be set in the toplevel "context" which is valid YAML
- Jinja string interpolation needs to be quoted at the beginning of a string, e.g. `- "{{ version }}"` in order for it to be valid YAML
- Selectors use a YAML dictionary style (vs. comments in conda-build). E.g. `- sel(osx): somepkg` instead of `- somepkg  # [osx]`
- Skip instruction uses a list of skip conditions and not the selector syntax from conda-build (e.g. `skip: ["osx", "win and py37"]`)

Quick start (from conda-build)
------------------------------

You can use `boa convert meta.yaml` to convert an existing recipe from conda-build syntax to boa. The command will output the new recipe to stdout. To quickly save the result, you can use `boa convert meta.yaml > recipe.yaml` and run `boa build .`. Please note that the conversion process is working fine only for "simple" recipes and there will be some needed manual work to convert complex recipes.

Examples
--------

```yaml
# this sets up "context variables" (in this case name and version) that
# can later be used in Jinja expressions
context:
  version: 1.1.0
  name: imagesize

# top level package information (name and version)
package:
  name: "{{ name }}"
  version: "{{ version }}"

# location to get the source from
source:
  url: https://pypi.io/packages/source/{{ name[0] }}/{{ name }}/{{ name }}-{{ version }}.tar.gz
  sha256: f3832918bc3c66617f92e35f5d70729187676313caa60c187eb0f28b8fe5e3b5

# build number (should be incremented if a new build is made, but version is not incrementing)
build:
  number: 1
  script: python -m pip install --no-deps --ignore-installed .

# the requirements at build and runtime
requirements:
  host:
    - python
    - pip
  run:
    - python

# tests to validate that the package works as expected
test:
  imports:
    - imagesize

# information about the package
about:
  home: https://github.com/shibukawa/imagesize_py
  license: MIT
  summary: 'Getting image size from png/jpeg/jpeg2000/gif file'
  description: |
    This module analyzes jpeg/jpeg2000/png/gif image header and
    return image size.
  dev_url: https://github.com/shibukawa/imagesize_py
  doc_url: https://pypi.python.org/pypi/imagesize
  doc_source_url: https://github.com/shibukawa/imagesize_py/blob/master/README.rst

# the below is conda-forge specific!
extra:
  recipe-maintainers:
    - somemaintainer

```


### Package section

Specifies package information.

```yaml
package:
  name: bsdiff4
  version: "2.1.4"
```

- **name**: The lower case name of the package. It may contain "-", but no spaces.
- **version**: The version number of the package. Use the PEP-386 verlib conventions. Cannot contain "-". YAML interprets version numbers such as 1.0 as floats, meaning that 0.10 will be the same as 0.1. To avoid this, put the version number in quotes so that it is interpreted as a string.


### Source section

Specifies where the source code of the package is coming from.
The source may come from a tarball file, git, hg, or svn. It may
be a local path and it may contain patches.


#### Source from tarball or zip archive

```
source:
  url: https://pypi.python.org/packages/source/b/bsdiff4/bsdiff4-1.1.4.tar.gz
  md5: 29f6089290505fc1a852e176bd276c43
  sha1: f0a2c9a30073449cfb7d171c57552f3109d93894
  sha256: 5a022ff4c1d1de87232b1c70bde50afbb98212fd246be4a867d8737173cf1f8f
```

If an extracted archive contains only 1 folder at its top level, its contents
will be moved 1 level up, so that the extracted package contents sit in the
root of the work folder.

#### Source from git

The git_url can also be a relative path to the recipe directory.

```
source:
  git_url: https://github.com/ilanschnell/bsdiff4.git
  git_rev: 1.1.4
  git_depth: 1 # (Defaults to -1/not shallow)
```

The depth argument relates to the ability to perform a shallow clone.
A shallow clone means that you only download part of the history from
Git. If you know that you only need the most recent changes, you can
say, ``git_depth: 1``, which is faster than cloning the entire repo.
The downside to setting it at 1 is that, unless the tag is on that
specific commit, then you won't have that tag when you go to reference
it in ``git_rev`` (for example). If your ``git_depth`` is insufficient
to capture the tag in ``git_rev``, you'll encounter an error. So in the
example above, unless the 1.1.4 is the very head commit and the one
that you're going to grab, you may encounter an error.


#### Source from hg

```
source:
  hg_url: ssh://hg@bitbucket.org/ilanschnell/bsdiff4
  hg_tag: 1.1.4
```

#### Source from svn

```
source:
  svn_url: https://github.com/ilanschnell/bsdiff
  svn_rev: 1.1.4
  svn_ignore_externals: True # (defaults to False)
```

#### Source from a local path

If the path is relative, it is taken relative to the recipe
directory. The source is copied to the work directory before
building.

```yaml
  source:
    path: ../src
```

If the local path is a git or svn repository, you get the
corresponding environment variables defined in your build
environment. The only practical difference between git_url or
hg_url and path as source arguments is that git_url and hg_url
would be clones of a repository, while path would be a copy of
the repository. Using path allows you to build packages with
unstaged and uncommitted changes in the working directory.
git_url can build only up to the latest commit.


#### Patches

Patches may optionally be applied to the source.

```yaml
  source:
    #[source information here]
    patches:
      - my.patch # the patch file is expected to be found in the recipe
```

boa (conda-build) automatically determines the patch strip level.

#### Destination path

Within boa's work directory, you may specify a particular folder to
place source into. Boa will always drop you into the same folder (build folder/work),
but it's up to you whether you want your source extracted into that folder, or
nested deeper. This feature is particularly useful when dealing with multiple
sources, but can apply to recipes with single sources as well.

```yaml
source:
  #[source information here]
  folder: my-destination/folder
```

#### Source from multiple sources

Some software is most easily built by aggregating several pieces.

The syntax is a list of source dictionaries. Each member of this list
follows the same rules as the single source. All features for each member are supported.

Example:

```yaml
  source:
    - url: https://package1.com/a.tar.bz2
      folder: stuff
    - url: https://package1.com/b.tar.bz2
      folder: stuff
    - git_url: https://github.com/mamba-org/boa
      folder: boa
```

Here, the two URL tarballs will go into one folder, and the git repo
is checked out into its own space. Git will not clone into a non-empty folder.

## Build section

Specifies build information.

Each field that expects a path can also handle a glob pattern. The matching is
performed from the top of the build environment, so to match files inside
your project you can use a pattern similar to the following one:
`"**/myproject/**/*.txt"`. This pattern will match any .txt file found in
your project. Quotation marks (`""`) are required for patterns that start with a `*`.

Recursive globbing using `**` is also supported.

#### Build number and string

The build number should be incremented for new builds of the same
version. The number defaults to `0`. The build string cannot
contain "-". The string defaults to the default boa build
string plus the build number.

```yaml
  build:
    number: 1
    string: abc
```

A hash will appear when the package is affected by one or more variables from
the conda_build_config.yaml file. The hash is made up from the "used" variables
- if anything is used, you have a hash. If you don't use these variables then you
won't have a hash. There are a few special cases that do not affect the hash, such as
Python and R or anything that already had a place in the build string.

The build hash will be added to the build string if these are true for any
dependency:

  * package is an explicit dependency in build, host, or run deps
  * package has a matching entry in conda_build_config.yaml which
    is a pin to a specific version, not a lower bound
  * that package is not ignored by ignore_version

OR

  * package uses `{{ compiler() }}` jinja2 function


#### Python entry points

The following example creates a Python entry point named
"bsdiff4" that calls ``bsdiff4.cli.main_bsdiff4()``.

```yaml
build:
  entry_points:
    - bsdiff4 = bsdiff4.cli:main_bsdiff4
    - bspatch4 = bsdiff4.cli:main_bspatch4
```


### Script

By default, boa uses a `build.sh` file on Unix (macOS and Linux) and a `bld.bat` file
on Linux, if they exist in the same folder as the `recipe.yaml` file. With the script
parameter you can either supply a different filename or write out short build scripts.
You may need to use selectors to use different scripts for different platforms.

```yaml
build:
  script: python setup.py install --single-version-externally-managed --record=record.txt
```



### Skipping builds

List conditions under which boa should skip the build of this recipe.
Particularly useful for defining recipes that are platform specific. By default,
a build is never skipped.

```yaml
build:
  skip:
    - win
    - osx and py36
    ...
```

### Architecture independent packages

Allows you to specify "no architecture" when building a package, thus
making it compatible with all platforms and architectures. Noarch
packages can be installed on any platform.

Assigning the noarch key as `generic` tells conda to not try any
manipulation of the contents.

```yaml
build:
  noarch: generic
```

`noarch: generic` is most useful for packages such as static javascript
assets and source archives. For pure Python packages that can run on any
Python version, you can use the `noarch: python` value instead:

```yaml
build:
  noarch: python
```

```{warning}
At the time of this writing, `noarch` packages should not make use of
preprocess-selectors: `noarch` packages are built with the
directives which evaluate to `true` in the platform it is built on,
which probably will result in incorrect/incomplete installation in
other platforms.
```

### Include build recipe

The full boa recipe and rendered `recipe.yaml` file is included in
the package\_metadata by default. You can disable this with:

```yaml
build:
  include_recipe: false
```

Requirements section
--------------------

Specifies the build and runtime requirements. Dependencies of these
requirements are included automatically.

Versions for requirements must follow the conda/mamba match specification. See
build-version-spec.

### Build

Tools required to build the package. These packages are run on the build
system and include things such as revision control systems (Git, SVN)
make tools (GNU make, Autotool, CMake) and compilers (real cross,
pseudo-cross, or native when not cross-compiling), and any source
pre-processors.

Packages which provide "sysroot" files, like the `CDT` packages (see
below) also belong in the build section.

```yaml
requirements:
  build:
    - git
    - cmake
```

### Host

It represents packages that need to be specific to the target
platform when the target platform is
not necessarily the same as the native build platform. For example, in
order for a recipe to be "cross-capable", shared libraries requirements
must be listed in the host section, rather than the build section, so
that the shared libraries that get linked are ones for the target
platform, rather than the native build platform. You should also include
the base interpreter for packages that need one. In other words, a
Python package would list `python` here and an R package would list
`mro-base` or `r-base`.

```yaml
requirements:
  build:
    - "{{ compiler('c') }}"
    - sel(linux): "{{ cdt('xorg-x11-proto-devel') }}"
  host:
    - python
```

```{note}
When both build and host sections are defined, the build section can
be thought of as "build tools" - things that run on the native platform, but output results for the target platform. For example, a cross-compiler that runs on linux-64, but targets linux-armv7.
```

The PREFIX environment variable points to the host prefix. With respect
to activation during builds, both the host and build environments are
activated. The build prefix is activated before the host prefix so that
the host prefix has priority over the build prefix. Executables that
don't exist in the host prefix should be found in the build prefix.

The build and host prefixes are always separate
when both are defined, or when `{{ compiler() }}` Jinja2 functions are
used. The only time that build and host are merged is when the host
section is absent, and no `{{ compiler() }}` Jinja2 functions are used
in meta.yaml.

### Run

Packages required to run the package. These are the dependencies that
are installed automatically whenever the package is installed. Package
names should follow the [package match
specifications](https://conda.io/projects/conda/en/latest/user-guide/concepts/pkg-specs.html#package-match-specifications).

```yaml
requirements:
  run:
    - python
    - sel(py26): argparse
    - six >=1.8.0
```

To build a recipe against different versions of NumPy and ensure that
each version is part of the package dependencies, list `numpy` as a
requirement in `recipe.yaml` and use a `conda_build_config.yaml` file with
multiple NumPy versions.

### Run\_constrained

Packages that are optional at runtime but must obey the supplied
additional constraint if they are installed.

Package names should follow the [package match
specifications](https://conda.io/projects/conda/en/latest/user-guide/concepts/pkg-specs.html#package-match-specifications).

```yaml
requirements:
  run_constrained:
    - optional-subpackage =={{ version }}
```

For example, let's say we have an environment that has package "a"
installed at version 1.0. If we install package "b" that has a
run\_constrained entry of "a\>1.0", then mamba would need to upgrade "a"
in the environment in order to install "b".

This is especially useful in the context of virtual packages, where the
run\_constrained dependency is not a package that mamba manages, but
rather a [virtual
package](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-virtual.html)
that represents a system property that mamba can't change. For example,
a package on linux may impose a run\_constrained dependency on
\_\_glibc\>=2.12. This is the version bound consistent with CentOS 6.
Software built against glibc 2.12 will be compatible with CentOS 6. This
run\_constrained dependency helps mamba tell the user that a given
package can't be installed if their system glibc version is too old.

Test section
------------

If this section exists or if there is a `run_test.[py,pl,sh,bat]` file
in the recipe, the package is installed into a test environment after
the build is finished and the tests are run there.

### Test files

Test files that are copied from the recipe into the temporary test
directory and are needed during testing.

```yaml
test:
  files:
    - test-data.txt
```

### Source files

Test files that are copied from the source work directory into the
temporary test directory and are needed during testing.

```yaml
test:
  source_files:
    - test-data.txt
    - some/directory
    - some/directory/pattern*.sh
```

### Test requirements

In addition to the runtime requirements, you can specify requirements
needed during testing. The runtime requirements that you specified in
the "run" section described above are automatically included during
testing.

```yaml
test:
  requires:
    - nose
```

### Test commands

Commands that are run as part of the test.

```yaml
test:
  commands:
    - bsdiff4 -h
    - bspatch4 -h
```

### Python imports

List of Python modules or packages that will be imported in the test
environment.

```yaml
test:
  imports:
    - bsdiff4
```

This would be equivalent to having a `run_test.py` with the following:

```python
import bsdiff4
```

### Run test script

The script `run_test.sh`---or `.bat`, `.py`, or `.pl`---is run
automatically if it is part of the recipe.

```{note}
Python .py and Perl .pl scripts are valid only as part of Python and
Perl packages, respectively.
```

Outputs section
---------------

Explicitly specifies packaging steps. This section supports multiple
outputs, as well as different package output types. The format is a list
of mappings. Build strings for subpackages are determined by their
runtime dependencies.

```yaml
outputs:
  - package:
      name: some-subpackage
      version: 1.0
  - package:
      name: some-other-subpackage
      version: 2.0
```

Scripts that create or move files into the build prefix can be any kind
of script. Known script types need only specify the script name.
Currently the list of recognized extensions is `py, bat, ps1`, and `sh`.

```yaml
outputs:
  - name: subpackage-name
    build:
      script: install-subpackage.sh
```

For scripts that move or create files, a fresh copy of the working
directory is provided at the start of each script execution. This
ensures that results between scripts are independent of one another.
You should take care of not packaging the same files twice.

### Subpackage requirements

Like a top-level recipe, a subpackage may have zero or more dependencies
listed as build, host or run requirements.

The dependencies listed as subpackage build requirements are available
only during the packaging phase of that subpackage.

A subpackage does not automatically inherit any dependencies from its
top-level recipe, so any build or run requirements needed by the
subpackage must be explicitly specified.

```
outputs:
  - package:
      name: subpackage-name
    requirements:
      build:
        - some-dep
      run:
        - some-dep
```

You can also impose runtime dependencies whenever a given (sub)package
is installed as a build dependency. For example, if we had an
overarching "compilers" package, and within that, had `gcc` and `libgcc`
outputs, we could force recipes that use GCC to include a matching
libgcc runtime requirement:

```yaml
outputs:
  - package:
      name: gcc
    build:
      run_exports:
        - libgcc 2.*
  - package:
      name: libgcc
```

See the run\_exports section for additional information.

### Subpackage tests

You can test subpackages independently of the top-level package.
Independent test script files for each separate package are specified
under the subpackage's test section. These files support the same
formats as the top-level `run_test.*` scripts, which are .py, .pl, .bat,
and .sh. These may be extended to support other script types in the
future.

```yaml
outputs:
  - package:
      name: subpackage-name
    test:
      script: some-other-script.py
```

By default, the `run_test.*` scripts apply only to the top-level
package. To apply them also to subpackages, list them explicitly in the
script section:

```yaml
outputs:
  - package:
      name: subpackage-name
    test:
      script: run_test.py
```

Test requirements for subpackages are not supported. Instead, subpackage
tests install their runtime requirements---but not the run requirements
for the top-level package---and the test-time requirements of the
top-level package.

EXAMPLE: In this example, the test for `subpackage-name` installs
`some-test-dep` and `subpackage-run-req`, but not
`some-top-level-run-req`.

```yaml
requirements:
  run:
    - some-top-level-run-req

test:
  requires:
    - some-test-dep

outputs:
  - name: subpackage-name
    requirements:
      - subpackage-run-req
    test:
      script: run_test.py
```

About section
-------------

Specifies identifying information about the package. The information
displays in the package server.

```yaml
about:
  home: https://github.com/ilanschnell/bsdiff4
  license: BSD
  license_file: LICENSE
  summary: binary diff and patch using the BSDIFF4-format
```

### License file

Add a file containing the software license to the package metadata. Many
licenses require the license statement to be distributed with the
package. The filename is relative to the source or recipe directory. The
value can be a single filename or a YAML list for multiple license
files. Values can also point to directories with license information.
Directory entries must end with a `/` suffix (this is to lessen
unintentional inclusion of non-license files; all of the directory's
contents will be unconditionally and recursively added).

```yaml
about:
  license_file:
    - LICENSE
    - vendor-licenses/
```

Extra section
-------------

A schema-free area for storing non-conda-specific metadata in standard
YAML form.

EXAMPLE: To store recipe maintainer information:

```yaml
extra:
  maintainers:
   - name of maintainer
```

Templating with Jinja
---------------------

Boa supports simple Jinja templating in the `meta.yaml` file.

You can set up Jinja variables in the context yaml section:

```
context:
  name: "test"
  version: "5.1.2"
  major_version: "{{ version.split('.')[0] }}"
```

Later in your `recipe.yaml` you can use these values in string interpolation
with Jinja. For example:

```
source:
  url: https://github.com/mamba-org/{{ name }}/v{{ version }}.tar.gz
```

Jinja has built-in support for some common string manipulations.

In boa, complex Jinja is completely disallowed as we try to produce YAML that is valid at all times.
So you should not use any `{% if ... %}` or similar Jinja constructs that produce invalid yaml.
Furthermore, quotes need to be applied when starting a value with double-curly brackets like so:

```
package:
  name: {{ name }}   # WRONG: invalid yaml
  name: "{{ name }}" # correct
```

For more information, see the [Jinja2 template
documentation](http://jinja.pocoo.org/docs/dev/templates/) and
the list of available environment
variables \<env-vars\>.

Jinja templates are evaluated during the build process. To retrieve a
fully rendered `recipe.yaml`, use the commands/boa-render command.

#### Additional Jinja2 functionality in Boa

Besides the default Jinja2 functionality, additional Jinja functions are
available during the conda-build process: `pin_compatible`,
`pin_subpackage`, and `compiler`.

The compiler function takes `c`, `cxx`, `fortran` and other values as argument and
automatically selects the right (cross-)compiler for the target platform.

```
build:
  - "{{ compiler('c') }}"
```

The `pin_subpackage` function pins another package produced by the recipe with the supplied
parameters.

Similarly, the `pin_compatible` function will pin a package according to the specified rules.


Preprocessing selectors
-----------------------

You can add selectors to any item, and the selector is evaluated in
a preprocessing stage. If a selector evaluates to `true`, the item is
flattened into the parent element. If a selector evaluates to `false`,
the item is removed.

```yaml
source:
  - sel(not win):
      url: http://path/to/unix/source
  - sel(win):
      url: http://path/to/windows/source
```

A selector is a valid Python statement that is executed. The following
variables are defined. Unless otherwise stated, the variables are
booleans.

The use of the Python version selectors, py27, py34, etc. is discouraged
in favor of the more general comparison operators. Additional selectors
in this series will not be added to conda-build.

Because the selector is any valid Python expression, complicated logic
is possible:

```yaml
source:
  - sel(win):
      url: http://path/to/windows/source
  - sel(unix and py2k):
      url: http://path/to/python2/unix/source
  - sel(unix and py>=35):
      url: http://path/to/python3/unix/source
```

Experimental features
---------------------

### Build time features

```{warning}
This is a very experimental feature of boa and may change or go away completely
```

With boa, you can add "build-time" features. That makes building packages from
source much more flexible and powerful and is a first step to enable a true "source"-distribution on top of conda packages.

```
name: libarchive

...

features:
  - name: zlib
    default: true
    requirements:
      host:
        - zlib
      run:
        - zlib

  - name: bzip2
    default: true
    requirements:
      host:
        - bzip2
      run:
        - bzip2
```

This adds two "features" to the boa recipe. These features can be enabled / disabled when invoking boa:

`boa build . --features [zlib, ~bzip2]`

This would compile libarchive with the zlib compression mechanism enabled, and bzip2 disabled. If a feature is not specified, the default value is used.
A feature can add additional requirements to the build/host/run section, and adds some environment variables to the build script invokation. In our example, the FEATURE_ZLIB environment variable will be set to `1`. This information can be used in the build script to enable or disable configuration and compilation flags.

For this libarchive recipe, the `./configure` call might look like this:

```
${SRC_DIR}/configure --prefix=${PREFIX}                                           \
                     $(feature $FEATURE_ZLIB --with-zlib --without-zlib)          \
                     $(feature $FEATURE_BZIP2 --with-bz2lib --without-bz2lib) ...

```

In this case we're using a special shell function `feature` to select between the enabled and disabled flag (similar to a ternary operator). The `feature` shell function is automatically added by boa into the shell environment.

One could similary use bash `if / else` to set flags based on the `$FEATURE_...` variable.
