from __future__ import print_function

import logging
import re

from oslo_config import cfg
from paramiko.client import SSHClient, AutoAddPolicy

from sanity.scenarios import Success, Failure, Skipped, SanityScenario
from sanity import fixtures


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class FloatScenario(SanityScenario):
    """Exercise a servers floating IP capability

    1. SSH into the server
    2. Check the servers hostname matches the expected hostname
    3. Check that the server can ping an external host
    """
    name = 'Float Check'
    shortname = 'float'
    log = LOG

    ping_re = re.compile(
        r'(?P<transmitted>\d+) packets transmitted, '
        r'(?P<received>\d+) received, '
        r'(?P<loss>\d+)% packet loss, time (?P<time>\S+)')

    @fixtures.useFixture(fixtures.FloatingIPFixture)
    def _test_server(self, server, floating_ip):
        if server.status != 'ACTIVE':
            return Skipped()
        result = Success()
        ip_address = floating_ip.ip_address

        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        try:
            client.connect(ip_address, username='root',
                           timeout=CONF.ssh_timeout)
        except Exception as e:
            return Failure("Failed to ssh to server.", exception=e)

        stdin, stdout, stderr = client.exec_command('hostname -f')
        stderr_output = stderr.read()
        if stderr_output:
            self.log.error('stderr: %r', stderr_output)
        remote_hostname = stdout.read().strip().split('.', 1)[0]

        expected_hostname = ('sanity-%s'
                             % server.metadata['host_id']).split('.', 1)[0]
        if remote_hostname != expected_hostname:
            return Failure("Hostname mismatch the servers %s hostname is %s"
                           % (expected_hostname, remote_hostname))

        stdin, stdout, stderr = client.exec_command(
            'ping -c 5 %s' % self._state.get('external_test_ip', '8.8.8.8'))
        stdout = stdout.read().strip()
        match = self.ping_re.search(stdout)
        if not match:
            return Failure("Host has no external connectivity.",
                           output=stdout)
        else:
            result = match.groupdict()
            if int(result['received']) == 0:
                return Failure("Host has no external connectivity.",
                               output=stdout)
            else:
                return Success(result=result)

        return result
