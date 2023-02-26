#!/usr/bin/env bash

TEST_FILE="data/test.py"

if [[ ! -f $TEST_FILE ]] ; then
    echo "data/test.py is missing"
    ls -al
    exit 1
else
    install $TEST_FILE $PREFIX/bin
fi
