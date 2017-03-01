import logging

LOG = logging.getLogger(__name__)


class Compute(object):
    def __init__(self, client):
        self._client = client

    def start(self, server):
        LOG.info("Starting %s", server)
        server.start()
        return server

    def stop(self, server):
        LOG.info("Stopping %s", server)
        server.stop()
        return server

    def pause(self, server):
        LOG.info("Pausing %s", server)
        server.pause()
        return server

    def unpause(self, server):
        LOG.info("Unpausing %s", server)
        server.unpause()
        return server

    def suspend(self, server):
        LOG.info("Suspend %s", server)
        server.suspend()
        return server

    def resume(self, server):
        LOG.info("Resume %s", server)
        server.resume()
        return server

    def migrate(self, server):
        LOG.info("Migrating %s", server)
        server.migrate()
        return server

    def live_migrate(self, server):
        LOG.info("Migrating %s", server)
        server.live_migrate()
        return server

    def reboot(self, server):
        LOG.info("Rebooting %s", server)
        server.reboot()
        return server

    @classmethod
    def delete(self, server):
        LOG.info("Deleting %s", server)
        server.delete()
        return server
