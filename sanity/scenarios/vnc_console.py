import logging
import requests

from oslo_config import cfg
from sanity.scenarios import Success, Failure, Skipped, SanityScenario

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class VNCConsoleScenario(SanityScenario):
    name = 'VNC Console Check'
    shortname = 'vnc-console'
    log = LOG

    def _test_server(self, server):
        if server.status != 'ACTIVE':
            return Skipped()
        response = None
        try:
            response = server.get_vnc_console('novnc')
        except Exception as e:
            return Failure('Error trying to get console URL.', exception=e)

        url = response['console']['url']
        try:
            response = requests.get(url, timeout=CONF.vnc_timeout)
        except requests.exceptions.ReadTimeout as e:
            return Failure('Timed out reading data from console.', exception=e)
        except requests.exceptions.ConnectTimeout as e:
            return Failure('Timed out connecting to console.', exception=e)
        except requests.exceptions.SSLError as e:
            return Failure("SSL isn't working correctly at %s." % url,
                           exception=e)
        except requests.exceptions.ConnectionError as e:
            return Failure('Connection error while connecting to console.',
                           exception=e)
        except requests.exceptions.RequestException as e:
            return Failure('Failed to connect to console.', exception=e)
        try:
            response.raise_for_status()
        except Exception as e:
            return Failure('Error trying to view console.', exception=e)

        return Success()
