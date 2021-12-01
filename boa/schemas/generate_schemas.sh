#!/bin/bash

python model.py > recipe.v1.json
python info/about.py > info/info-about.schema.json
python info/index.py > info/info-index.schema.json
python info/paths.py > info/info-paths.schema.json
