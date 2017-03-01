#!/bin/bash -xe

NAME='sdu-test-sanity'

VERSION=$(python tools/generate_version.py --version)
REVISION=$(python tools/generate_version.py --revision)


sudo pip install virtualenv-tools

fpm --log info \
    -s virtualenv \
    -t rpm \
    -n $NAME \
    --directories /opt/ccs/$NAME \
    --virtualenv-install-location /opt/ccs/sdu-test-sanity \
    --version $VERSION \
    --iteration $REVISION \
    --exclude .git \
    --exclude Vagrantfile \
    --before-install tools/before_install.sh \
    --before-remove tools/before_remove.sh \
    --before-upgrade tools/before_upgrade.sh \
    -d libxml2 \
    -d libxslt \
    -d libffi \
    -d postgresql-libs \
    -d MySQL-python .
