# generated by datamodel-codegen:
#   filename:  recipe.v1.json
#   timestamp: 2021-11-22T15:42:45+00:00

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Extra, Field, conint


class Package(BaseModel):
    class Config:
        extra = Extra.forbid

    name: Optional[str] = Field(None, description="The package name")
    version: Optional[str] = Field(None, description="The package version")


class SourceItem(BaseModel):
    url: Optional[str] = None
    sha256: Optional[str] = None
    md5: Optional[str] = None
    sha1: Optional[str] = None
    patches: Optional[List[str]] = None
    folder: Optional[str] = None
    git_rev: Optional[str] = None
    git_url: Optional[str] = None


class Build(BaseModel):
    number: conint(ge=0)
    string: Optional[str] = None
    run_exports: Optional[Dict[str, Any]] = None
    skip: Optional[List[str]] = None
    noarch: Optional[str] = None
    pre_link: Optional[str] = Field(None, alias="pre-link")
    post_link: Optional[str] = Field(None, alias="post-link")
    pre_unlink: Optional[str] = Field(None, alias="pre-unlink")
    ignore_run_exports: Optional[List[str]] = None
    ignore_run_exports_from: Optional[List[str]] = None


class Package1(BaseModel):
    name: str
    version: Optional[str] = None


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
    package: Package1 = Field(..., description="The package name.")
    build: Optional[Dict[str, Any]] = None
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
        None, description="The package name and version."
    )
    outputs: Optional[List[Output]] = None
    features: Optional[List] = None
    extra: Optional[Dict[str, Any]] = None
    build: Optional[Dict[str, Any]] = None
    about: Optional[Dict[str, Any]] = None
