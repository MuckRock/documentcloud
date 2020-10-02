#!/bin/bash

# NOTE: YOU DO NOT NEED TO RUN THIS UNLESS YOU PLAN TO ADAPT THIS
# TO A DIFFERENT OS. IT IS MAINLY FOR REFERENCE

# Adapted from https://github.com/vladgolubev/serverless-libreoffice/blob/master/compile.sh
# For Ubuntu

set -e

export LC_CTYPE=en_US.UTF-8
export LC_ALL=en_US.UTF-8

cd /tmp
if [ ! -d /tmp/libreoffice ]
then
  curl -L https://github.com/LibreOffice/core/archive/libreoffice-6.2.1.2.tar.gz | tar -xz
  mv core-libreoffice-6.2.1.2 libreoffice
fi
cd /tmp/libreoffice

# see https://ask.libreoffice.org/en/question/72766/sourcesver-missing-while-compiling-from-source/
echo "lo_sources_ver=6.2.1.2" >> sources.ver

# set this cache if you are going to compile several times
ccache --max-size 32 G && ccache -s

apt-get update -y
apt-get --assume-yes install autoconf gperf libxslt1-dev xsltproc libxml2-utils libcurl4-nss-dev libnspr4-dev libnss3-dev bison flex zip libgl-dev nasm liblangtag-common

# the most important part. Run ./autogen.sh --help to see what each option means
./autogen.sh \
    --disable-avahi \
    --disable-cairo-canvas \
    --disable-coinmp \
    --disable-cups \
    --disable-cve-tests \
    --disable-dbus \
    --disable-dconf \
    --disable-dependency-tracking \
    --disable-evolution2 \
    --disable-dbgutil \
    --disable-extension-integration \
    --disable-extension-update \
    --disable-firebird-sdbc \
    --disable-gio \
    --disable-gstreamer-0-10 \
    --disable-gstreamer-1-0 \
    --disable-gtk \
    --disable-gtk3 \
    --disable-introspection \
    --disable-kde4 \
    --disable-largefile \
    --disable-lotuswordpro \
    --disable-lpsolve \
    --disable-odk \
    --disable-ooenv \
    --disable-pch \
    --disable-postgresql-sdbc \
    --disable-python \
    --disable-randr \
    --disable-report-builder \
    --disable-scripting-beanshell \
    --disable-scripting-javascript \
    --disable-sdremote \
    --disable-sdremote-bluetooth \
    --enable-mergelibs \
    --with-galleries="no" \
    --with-system-curl \
    --with-system-expat \
    --with-system-libxml \
    --with-system-nss \
    --with-system-openssl \
    --with-theme="no" \
    --without-export-validation \
    --without-fonts \
    --without-helppack-integration \
    --without-java \
    --without-junit \
    --without-krb5 \
    --without-myspell-dicts \
    --without-system-dicts

# Disable flaky unit test
sed -i '609s/.*/#if defined MACOSX \&\& !defined _WIN32/' ./vcl/qa/cppunit/pdfexport/pdfexport.cxx

# this will take 0-2 hours to compile, depends on your machine
# (note: on my Ubuntu vm it took 6.5 hrs)
time make

# this will remove ~100 MB of symbols from shared objects
strip ./instdir/**/*

# remove unneeded stuff for headless mode
rm -rf ./instdir/share/gallery \
    ./instdir/share/config/images_*.zip \
    ./instdir/readmes \
    ./instdir/CREDITS.fodt \
    ./instdir/LICENSE* \
    ./instdir/NOTICE

# archive
tar -czvf lo.tar.gz instdir

# test if compilation was successful
echo "hello world" > a.txt
./instdir/program/soffice --headless --invisible --nodefault --nofirststartwizard \
    --nolockcheck --nologo --norestore --convert-to pdf --outdir /tmp a.txt

# copy archive into documentcloud processing
cp lo.tar.gz /app/documentcloud/documents/processing/document_conversion/libreoffice/lo.tar.gz

echo "done"

<<USAGE
./documentcloud/documents/processing/document_conversion/libreoffice/install.sh
USAGE
