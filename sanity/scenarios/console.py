import re
import time
import logging

from sanity.scenarios import Success, Failure, Skipped, SanityScenario

LOG = logging.getLogger(__name__)


class CloudInitSuccess(Success):
    boot_time = None

    def __str__(self):
        seconds = self.duration.seconds
        return (("PASS (%s)" % self.boot_time) +
                ' {:02}:{:02}'.format(seconds % 3600 // 60, seconds % 60))

    def to_dict(self):
        return {
            'result': 'Success',
            'duration': int(float(self.boot_time)),
        }


class ConsoleScenario(SanityScenario):
    name = 'Console Log Check'
    shortname = 'console-log'
    log = LOG
    success_re = re.compile(r'Cloud-init v\. \S+ finished '
                            r'at .* Up ([\d.]+) seconds')
    failure_res = [
        ("Cloud-init Couldn't get metadata.",
         re.compile(r"DataSourceEc2.py\[CRITICAL\]: "
                    r"Giving up on md from \['.*'\] after \d+ seconds")),

        # XXX These are disabled because they fail, but the machine
        # still gets an IP, they probably should be marked as warning.

        # ("Cloud-init route info failed.",
        #  re.compile(r"ci-info: !!![!]+Route info failed!!!![!]+")),
        # ("Cloud-init couldn't get IP.",
        #  re.compile(r"ci-info: \|\s+eth0\s+\|\s+True\s+\|\s+\.\s+"
        #             r"\|\s+\.\s+\|\s+[0-9a-z:]+\s+\|")),

        ("Kernel panic",
         re.compile(r"Kernel panic - not syncing"))]

    def _test_server(self, server):
        if server.status != 'ACTIVE':
            return Skipped()

        count = 0
        output = None
        while not bool(output and self.success_re.search(output)):
            try:
                output = server.get_console_output()
            except Exception as e:
                return Failure("Failed to get console log",
                               exception=e)

            for reason, regexp in self.failure_res:
                if regexp.search(output):
                    return Failure(reason, output=output)

            count += 1
            if count > 20:
                return Failure("Can't find end of cloud-init in output.",
                               output=output)

            sleep_for = count * 2
            time.sleep(sleep_for)
            self.log.debug("Can't find end of cloud-init on server %s "
                           "sleeping %s", server.id, sleep_for)

        result = self.success_re.search(output)
        boot_time = result.groups()[0]
        return CloudInitSuccess(boot_time=boot_time)
