#!/bin/bash

BASEDIR=/opt/ccs/sdu-test-sanity

if [ -d $BASEDIR ]; then
    find $BASEDIR -name \*pyc -exec rm {} \;
fi
