import logging

LOG = logging.getLogger(__name__)


def gethostid(host):
    try:
        return host.hostname
    except AttributeError:
        try:
            return host.host
        except AttributeError:
            pass
    return host


class Host(object):
    def __init__(self, sanity):
        self._sanity = sanity

    def boot_server(self, host):
        LOG.info("Launching on %s", gethostid(host))
        server = self._sanity.boot_server_on_host(host)
        LOG.info("Launched %s on %s", server.id, gethostid(host))
        return server
