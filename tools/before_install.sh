#!/bin/bash

SERVICE=sdu-test-repository
GROUPNAME=litmus
USERNAME=litmus


getent group $GROUPNAME >/dev/null || groupadd -r $GROUPNAME
getent passwd $USERNAME >/dev/null || \
    useradd -r -g $GROUPNAME -d /var/lib/$SERVICE/ -s /sbin/nologin \
    -c "sdu-test-celery user" $USERNAME
