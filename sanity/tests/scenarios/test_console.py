
import httpretty
import mock
import pytest

from sanity.scenarios import ConsoleScenario, Success, Failure


KEYSTONE_TOKEN = """{
  "access": {
    "token": {
      "issued_at": "2013-10-28T21:31:34.158770",
      "expires": "2013-10-29T21:31:34Z",
      "id": "MIINUAYJKoZIhvcNAQ==",
      "tenant": {
        "enabled": true,
        "description": null,
        "name": "admin",
        "id": "36215f8"}},
    "serviceCatalog": [{
        "endpoints_links": [],
        "endpoints": [{
            "adminURL": "http://example-cloud.local:8774/v2/36215f8",
            "region": "RegionOne",
            "publicURL": "http://example-cloud.local:8774/v2/36215f8",
            "internalURL": "http://example-cloud.local:8774/v2/36215f8",
            "id": "53ad66f"
          }],
        "type": "compute",
        "name": "nova"},
      {
        "endpoints_links": [],
        "endpoints": [{
            "adminURL": "http://example-cloud.local:9292/",
            "region": "RegionOne",
            "publicURL": "http://example-cloud.local:9292/",
            "internalURL": "http://example-cloud.local:9292/",
            "id": "a3338f8b"
          }],
        "type": "image",
        "name": "glance"},
      {
        "endpoints_links": [],
        "endpoints": [{
            "adminURL": "http://example-cloud.local:35357/v2.0",
            "region": "RegionOne",
            "publicURL": "http://example-cloud.local:5000/v2.0",
            "internalURL": "http://example-cloud.local:5000/v2.0",
            "id": "1d6a58b"
          }],
        "type": "identity",
        "name": "keystone"
      }],
    "user": {
      "username": "admin",
      "roles_links": [],
      "id": "717a936",
      "roles": [{
          "name": "admin"
        }],
      "name": "admin"
    },
    "metadata": {
      "is_admin": 0,
      "roles": [
        "a0dfe95"
]}}}"""


@pytest.fixture
def server():
    mock_server = mock.Mock()
    mock_server.status = 'ACTIVE'
    return mock_server


@pytest.fixture
@httpretty.activate
def console_scenario():
    httpretty.register_uri(httpretty.POST,
                           'http://example-cloud.local/v2.0/tokens',
                           body=KEYSTONE_TOKEN)

    console_test = ConsoleScenario(mock.Mock(), mock.Mock(),
                                   mock.Mock(), mock.Mock(),
                                   mock.Mock())
    return console_test


CLOUD_INIT_SUCCESS = """
ci-info: +++++++++++++++++++++++++++Net device info+++++++++++++++++++++++++++
ci-info: +--------+------+---------------+---------------+-------------------+
ci-info: | Device |  Up  |    Address    |      Mask     |     Hw-Address    |
ci-info: +--------+------+---------------+---------------+-------------------+
ci-info: |   lo   | True |   127.0.0.1   |   255.0.0.0   |         .         |
ci-info: |  eth0  | True | 192.168.10.11 | 255.255.255.0 | fa:88:88:88:48:9a |
ci-info: +--------+------+---------------+---------------+-------------------+
Cloud-init v. 0.7.4 finished at Thu, 04 Jun 2015 18:26:42 +0000. Datasource DataSourceEc2.  Up 35.26 seconds
"""  # noqa


def test_valid_console(console_scenario, server):
    server.get_console_output.return_value = CLOUD_INIT_SUCCESS
    result = console_scenario.test_server(server)
    assert isinstance(result, Success), result.reason


CLOUD_INIT_SUCCESS1 = """
cloud-init[766]: ci-info: ++++++++++++++++++++++++++Net device info+++++++++++++++++++++++++++
cloud-init[766]: ci-info: +--------+------+--------------+---------------+-------------------+
cloud-init[766]: ci-info: | Device |  Up  |   Address    |      Mask     |     Hw-Address    |
cloud-init[766]: ci-info: +--------+------+--------------+---------------+-------------------+
cloud-init[766]: ci-info: |  lo:   | True |  127.0.0.1   |   255.0.0.0   |         .         |
cloud-init[766]: ci-info: | eth0:  | True | 192.168.50.2 | 255.255.255.0 | fa:16:3e:0b:cf:df |
cloud-init[766]: ci-info: +--------+------+--------------+---------------+-------------------+
cloud-init[959]: Cloud-init v. 0.7.5 finished at Mon, 10 Aug 2015 05:31:31 +0000. Datasource DataSourceOpenStack [net,ver=2].  Up 46.95 seconds"""  # noqa


def test_valid_console1(console_scenario, server):
    server.get_console_output.return_value = CLOUD_INIT_SUCCESS1
    result = console_scenario.test_server(server)
    assert isinstance(result, Success), result.reason


CLOUD_INIT_FAILED_IP = """
ci-info: +++++++++++++++++++++++++++Net device info+++++++++++++++++++++++++++
ci-info: +--------+------+---------------+---------------+-------------------+
ci-info: | Device |  Up  |    Address    |      Mask     |     Hw-Address    |
ci-info: +--------+------+---------------+---------------+-------------------+
ci-info: |   lo   | True |   127.0.0.1   |   255.0.0.0   |         .         |
ci-info: |  eth0  | True |       .       |        .      | fa:88:88:88:48:9a |
ci-info: +--------+------+---------------+---------------+-------------------+
Cloud-init v. 0.7.4 finished at Thu, 04 Jun 2015 18:26:42 +0000. Datasource DataSourceEc2.  Up 35.26 seconds
"""  # noqa


@pytest.mark.xfail
def test_invalid_ip(console_scenario, server):
    server.get_console_output.return_value = CLOUD_INIT_FAILED_IP
    result = console_scenario.test_server(server)
    assert isinstance(result, Failure)
    assert result.reason == "Cloud-init couldn't get IP."


CLOUD_INIT_FAILED_ROUTE = """
ci-info: +++++++++++++++++++++++++++Net device info+++++++++++++++++++++++++++
ci-info: +--------+------+---------------+---------------+-------------------+
ci-info: | Device |  Up  |    Address    |      Mask     |     Hw-Address    |
ci-info: +--------+------+---------------+---------------+-------------------+
ci-info: |   lo   | True |   127.0.0.1   |   255.0.0.0   |         .         |
ci-info: |  eth0  | True | 192.168.10.11 | 255.255.255.0 | fa:88:88:88:48:9a |
ci-info: +--------+------+---------------+---------------+-------------------+
ci-info: !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!Route info failed!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
Cloud-init v. 0.7.4 finished at Thu, 04 Jun 2015 18:26:42 +0000. Datasource DataSourceEc2.  Up 35.26 seconds
"""  # noqa


@pytest.mark.xfail
def test_invalid_route(console_scenario, server):
    server.get_console_output.return_value = CLOUD_INIT_FAILED_ROUTE
    result = console_scenario.test_server(server)
    assert isinstance(result, Failure)
    assert result.reason == "Cloud-init route info failed."


CLOUD_INIT_NO_METADATA = """
2015-02-13 01:09:02,137 - DataSourceEc2.py[CRITICAL]: Giving up on md from ['http://169.254.169.254/2009-04-04/meta-data/instance-id'] after 126 seconds
Cloud-init v. 0.7.4 finished at Thu, 04 Jun 2015 18:26:42 +0000. Datasource DataSourceEc2.  Up 35.26 seconds
"""  # noqa


def test_no_metadata(console_scenario, server):
    server.get_console_output.return_value = CLOUD_INIT_NO_METADATA
    result = console_scenario.test_server(server)
    assert isinstance(result, Failure)
    assert result.reason == "Cloud-init Couldn't get metadata."


KERNEL_PANIC = """
Kernel panic - not syncing: Watchdog detected hard LOCKUP on cpu 3
Cloud-init v. 0.7.4 finished at Thu, 04 Jun 2015 18:26:42 +0000. Datasource DataSourceEc2.  Up 35.26 seconds
"""  # noqa


def test_kernel_panic(console_scenario, server):
    server.get_console_output.return_value = KERNEL_PANIC
    result = console_scenario.test_server(server)
    assert isinstance(result, Failure)
    assert result.reason == "Kernel panic"
