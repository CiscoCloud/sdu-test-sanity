from __future__ import print_function

import logging
import os
import subprocess

from sanity.scenarios import Success, Failure, Skipped, SanityScenario

LOG = logging.getLogger(__name__)


def ping(host):
    with open(os.devnull, 'w') as DEVNULL:
        try:
            subprocess.check_call(
                ['ping', '-c', '1', str(host)],
                stdout=DEVNULL,
                stderr=DEVNULL
            )
            return True
        except subprocess.CalledProcessError:
            return False


class PingScenario(SanityScenario):
    """Ping all servers interfaces

    """
    name = 'Ping Check'
    shortname = 'ping'
    log = LOG

    def _test_server(self, server):
        if server.status != 'ACTIVE':
            return Skipped()
        result = Success()
        failed_pings = []
        for network in server.addresses:
            for address in server.addresses[network]:
                if address.get('version') != 4:
                    continue
                ip_address = address['addr']
                if not ping(ip_address):
                    failed_pings.append((network, ip_address))
                    self.log.error('Failed to ping IP %s on network %s',
                                   ip_address, network)
                else:
                    self.log.info('Succeeded to ping IP %s on network %s',
                                  ip_address, network)

        if failed_pings:
            return Failure("Interfaces failed. %r " % failed_pings)
        return result
