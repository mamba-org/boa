# generated by datamodel-codegen:
#   filename:  paths.json
#   timestamp: 2021-11-25T18:32:52+00:00

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class Path(BaseModel):
    _path: str
    path_type: str
    sha256: str
    size_in_bytes: int
    file_mode: Optional[str] = None
    prefix_placeholder: Optional[str] = None


class Model(BaseModel):
    paths: List[Path]
    paths_version: int


if __name__ == "__main__":
    print(Model.schema_json(indent=2))
