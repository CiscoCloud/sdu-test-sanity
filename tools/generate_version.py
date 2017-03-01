#!/bin/python

"""Generate a version number that looks like "1.feature-upstream-111"
for branches and like "0.0.1-5752.111" for master branch.

In the case of branches the template is basically
"1.<branch_name>-<build_number>"

In the case of master the template is
"<nimbus_yml_version>-<commit_count>.<build_number>"

"""

import os
import logging
import yaml
import subprocess

LOG = logging.getLogger(__file__)
logging.basicConfig(level=logging.DEBUG)


def main():
    version = []
    BASE_VERSION = yaml.load(open('.nimbus.yml')).get('version', '0')

    if 'GERRIT_BRANCH' in os.environ:
        BRANCH_NAME = os.environ['GERRIT_BRANCH'].strip()
    else:
        BRANCH_NAME = subprocess.check_output(
            ["git", "rev-parse", '--abbrev-ref', 'HEAD']).strip()

    LOG.debug('Branch name %s', BRANCH_NAME)

    COMMIT_NUM = subprocess.check_output(
        ["git", "rev-list", 'HEAD', '--count']).strip()

    LOG.debug('Commit number %s', COMMIT_NUM)

    BUILD_NUM = ''
    URL = os.environ.get('BUILD_URL', '')
    if URL:
        try:
            BUILD_NUM = str(int(URL.split('/')[-2]))
        except:
            LOG.exception("Can't parse BUILD_NUM")

    LOG.debug('Build number %s', BUILD_NUM)

    if BRANCH_NAME != 'master':
        version.append('1.' + BRANCH_NAME.replace('/', '_'))
        if BUILD_NUM:
            version.append(BUILD_NUM)
        return (BASE_VERSION, '.'.join(version))
    else:
        if COMMIT_NUM:
            try:
                version.append(str(int(COMMIT_NUM)))
            except:
                LOG.exception("Can't parse COMMIT_NUM")
        if BUILD_NUM:
            version.append(BUILD_NUM)

        return (BASE_VERSION, '.'.join(version))


if '__main__' == __name__:
    import argparse

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="Increase verbosity (specify multiple times for more)")
    parser.add_argument(
        '--version', action='store_true',
        help="Return only the version")
    parser.add_argument(
        '--revision', action='store_true',
        help="Return only the revision")

    args = parser.parse_args()

    log_level = logging.WARNING
    if args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(name)s %(levelname)s %(message)s')

    version = main()
    if args.version:
        print version[0]
    elif args.revision:
        print version[1]
    else:
        print '%s-%s' % version
