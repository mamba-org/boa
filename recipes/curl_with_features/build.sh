#!/bin/bash
export PKG_CONFIG_PATH="${PREFIX}/lib/pkgconfig"
export C_INCLUDE_PATH="${PREFIX}/include"

     # ([ $FEATURE_HTTP2 ] && --with-nghttp2=${PREFIX} || --disable-nghttp2)
     # ([ $FEATURE_KRB5 ] && --with-krb5=${PREFIX} || --disable-krb5)

# Legacy toolchain flags
if [[ ${c_compiler} =~ .*toolchain.* ]]; then
    if [ $(uname) == "Darwin" ]; then
        export DYLD_FALLBACK_LIBRARY_PATH="${PREFIX}/lib"
        export CC=clang
        export CXX=clang++
    else
        export LDFLAGS="$LDFLAGS -Wl,--disable-new-dtags"
    fi
fi
if [[ ${target_platform} != osx-64 ]]; then
    export LDFLAGS="${LDFLAGS} -Wl,-rpath-link,$PREFIX/lib"
fi

function feature()
{
    if [[ $1 != "0" ]]
    then
        echo $2
    else
        echo $3
    fi
}

./configure \
    --prefix=${PREFIX} \
    --host=${HOST} \
    $(feature $FEATURE_LDAP --enable-ldap --disable-ldap) \
    --with-ca-bundle=${PREFIX}/ssl/cacert.pem \
    --without-ssl \
    --with-zlib=${PREFIX} \
    $(feature $FEATURE_KRB5 --with-gssapi=${PREFIX} "") \
    --with-libssh2=${PREFIX} \
    $(feature $FEATURE_HTTP2 --with-nghttp2=${PREFIX} --without-nghttp2) \
# || cat config.log

# make -j${CPU_COUNT} ${VERBOSE_AT}
make install

# Includes man pages and other miscellaneous.
rm -rf "${PREFIX}/share"
