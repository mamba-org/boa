#!/bin/bash
mkdir -p build
cd build

cmake -DCMAKE_INSTALL_PREFIX=$PREFIX \
      -DCMAKE_PREFIX_PATH=$PREFIX \
      -DCMAKE_INSTALL_LIBDIR=lib \
      -DENABLE_CONDA=ON \
      -DMULTI_SEMANTICS=ON \
      -DCMAKE_BUILD_TYPE=Release \
      -DENABLE_STATIC=ON \
      ..

make VERBOSE=1 -j${CPU_COUNT} install