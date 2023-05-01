from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from enum import Enum
from pydantic import BaseModel, Extra, Field, conint, constr


###################
# Package section #
###################


class Package(BaseModel):
    class Config:
        extra = Extra.forbid

    name: str = Field(description="The package name")
    version: str = Field(description="The package version")


###################
# Source section  #
###################


sha256str = constr(min_length=64, max_length=64, regex=r"^[0-9a-fA-F]{64}$")
md5str = constr(min_length=32, max_length=32, regex=r"^[0-9a-fA-F]{32}$")
sha1 = constr(min_length=40, max_length=40, regex=r"^[0-9a-fA-F]{40}$")

# We require some paths to contain no backslashes, even on Windows
path_no_backslash = constr(regex=r"^[^\\]+$")
ListNoBackslash = List[path_no_backslash]


class BaseSourceItem(BaseModel):
    class Config:
        extra = Extra.forbid

    patches: Optional[List[str]] = None
    folder: Optional[str] = None


class UrlSource(BaseSourceItem):
    url: str = None

    sha256: Optional[sha256str] = None
    md5: Optional[md5str] = None
    sha1: Optional[sha1] = None
    fn: Optional[str] = None


class GitSource(BaseSourceItem):
    git_rev: str = "HEAD"
    git_url: str
    git_depth: int = -1


class HgSource(BaseSourceItem):
    hg_url: str
    hg_tag: str = "tip"


class SvnSource(BaseSourceItem):
    svn_url: str
    svn_rev: str = "head"
    svn_ignore_externals: bool = False


class LocalSource(BaseSourceItem):
    path: str


SourceItem = Union[UrlSource, GitSource, HgSource, SvnSource, LocalSource]


###################
# Build section   #
###################


class NoarchType(Enum):
    generic = "generic"
    python = "python"


class RunExports(BaseModel):
    class Config:
        extra = Extra.forbid

    weak: Optional[List[str]] = Field(
        None, description="Weak run exports apply from the host env to the run env"
    )
    strong: Optional[List[str]] = Field(
        None,
        description="Strong run exports apply from the build and host env to the run env",
    )
    noarch: Optional[List[str]] = Field(
        None,
        description="Noarch run exports are the only ones looked at when building noarch packages",
    )
    weak_constrains: Optional[List[str]] = Field(
        None, description="Weak run constrains add run_constrains from the host env"
    )
    strong_constrains: Optional[List[str]] = Field(
        None,
        description="Strong run constrains add run_constrains from the build and host env",
    )


class Build(BaseModel):
    class Config:
        extra = Extra.forbid

    number: Optional[conint(ge=0)] = Field(
        0,
        description="Build number to version current build in addition to package version",
    )
    string: Optional[str] = Field(
        None,
        description="Build string to identify build variant (if not explicitly set, computed automatically from used build variant)",
    )
    skip: Optional[List[str]] = Field(
        None,
        description="List of conditions under which to skip the build of the package.",
    )
    script: Optional[Union[str, List[str]]] = Field(
        None,
        description="Build script to be used. If not given, tries to find 'build.sh' on Unix or 'bld.bat' on Windows inside the recipe folder.",
    )

    noarch: Optional[NoarchType] = Field(
        None,
        description="Can be either 'generic' or 'python'. A noarch 'python' package compiles .pyc files upon installation.",
    )
    # Note: entry points only valid if noarch: python is used! Write custom validator?
    entry_points: Optional[List[str]] = None
    # Deprecated
    # noarch_python: bool = False

    run_exports: Optional[Union[RunExports, List[str]]] = None
    ignore_run_exports: Optional[List[str]] = None
    ignore_run_exports_from: Optional[List[str]] = None

    # deprecated, but still used to downweigh packages
    track_features: Optional[List[str]] = None

    # Features are completely deprecated
    # features: List[str]
    # requires_features: Dict[str, str]
    # provides_features: Dict[str, str],

    include_recipe: bool = Field(True, description="Include recipe in final package.")

    pre_link: Optional[str] = Field(
        None,
        alias="pre-link",
        description="Script to execute when installing - before linking. Highly discouraged!",
    )
    post_link: Optional[str] = Field(
        None,
        alias="post-link",
        description="Script to execute when installing - after linking.",
    )
    pre_unlink: Optional[str] = Field(
        None,
        alias="pre-unlink",
        description="Script to execute when removing - before unlinking.",
    )

    osx_is_app: bool = False
    disable_pip: bool = False
    preserve_egg_dir: bool = False

    no_link: Optional[ListNoBackslash] = None
    binary_relocation: Union[bool, ListNoBackslash] = True

    has_prefix_files: ListNoBackslash = []
    binary_has_prefix_files: Optional[ListNoBackslash] = None
    ignore_prefix_files: Union[bool, ListNoBackslash] = False

    # the following is defaulting to True on UNIX and False on Windows
    detect_binary_files_with_prefix: Optional[bool] = None

    skip_compile_pyc: Optional[List[str]] = None

    rpaths: Optional[List[str]] = None
    rpaths_patcher: Optional[str] = None

    # Note: this deviates from conda-build `script_env`!
    script_env: Optional[Dict[str, str]] = None

    # Files to be included even if they are present in the PREFIX before building
    always_include_files: Optional[List[str]] = None

    # msvc_compiler: Optional[str] = None -- deprecated in conda_build
    # pin_depends: Optional[str] -- did not find usage anywhere, removed
    # preferred_env: Optional[str]
    # preferred_env_executable_paths': Optional[List]

    # note didnt find _any_ usage of force_use_keys in conda-forge
    force_use_keys: Optional[List[str]] = None
    force_ignore_keys: Optional[List[str]] = None

    merge_build_host: bool = False

    missing_dso_whitelist: Optional[List[str]] = None
    error_overdepending: bool = Field(False, description="Error on overdepending")
    error_overlinking: bool = Field(False, description="Error on overlinking")


###################
# About section   #
###################


class About(BaseModel):

    # URLs
    home: Optional[str] = None
    dev_url: Optional[str] = None
    doc_url: Optional[str] = None
    doc_source_url: Optional[str] = None
    license_url: Optional[str] = None

    # Text
    license_: Optional[str] = Field(None, alias="license")
    summary: Optional[str] = None
    description: Optional[str] = None
    license_family: Optional[str] = None

    # Lists
    identifiers: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    keywords: Optional[List[str]] = None

    # Paths in source tree
    license_file: Optional[List[str]] = None
    prelink_message: Optional[str] = None
    readme: Optional[str] = None


#########################
# Requirements Section  #
#########################


class Requirements(BaseModel):
    build: Optional[List[str]] = None
    host: Optional[List[str]] = None
    run: Optional[List[str]] = None
    run_constrained: Optional[List[str]] = None


class Test(BaseModel):
    files: Optional[List[str]] = Field(
        None,
        description="Test files that are copied from the recipe into the temporary test directory and are needed during testing.",
    )
    source_files: Optional[List[str]] = Field(
        None,
        description="Test files that are copied from the source work directory into the temporary test directory and are needed during testing.",
    )
    requires: Optional[List[str]] = Field(
        None,
        description="In addition to the runtime requirements, you can specify requirements needed during testing.",
    )
    imports: Optional[List[str]] = Field(None, description="Test importing modules.")
    commands: Optional[List[str]] = Field(
        None, description="The test commands to execute."
    )


class Output(BaseModel):
    package: Package = Field(..., description="The package name and version")
    build: Optional[Build] = None
    requirements: Optional[Requirements] = None
    test: Optional[Test] = None


class BoaRecipeV1(BaseModel):
    class Config:
        extra = Extra.forbid

    context: Optional[Dict[str, Any]] = Field(None, description="The recipe context.")
    package: Optional[Package] = Field(
        None, description="The package name and version."
    )
    source: Optional[List[SourceItem]] = Field(
        None, description="The source items to be downloaded and used for the build."
    )
    build: Optional[Build] = None
    features: Optional[List] = None
    steps: Optional[List[Output]] = None
    about: Optional[About] = None
    extra: Optional[Dict[str, Any]] = None


if __name__ == "__main__":
    print(BoaRecipeV1.schema_json(indent=2))
