======
Sanity
======


Host based functional testing for clouds.

* Free software: Apache2 license


Cliff Notes Usage:
------------------

1. open terminal & source your Openrc
2. cd to sdu-test-sanity
3. Normal execution? then: type "sanity test" @ bash prompt

OR

3. Advanced Execution? then,:

type each entry, press enter, watch screen:

- sanity shell
- start()
- launch_on_each_host()

# Run baseline tests
- run_baseline()
# or some custom set of tests
- test_boot()
- test_console()
- test_floatingip()
- test_vncconsole()

- print_results()
- stop()


Normal Execution
~~~~~~~~~~~~~~~~

First source the credentials of the cloud you intend to test::

  $ source openrc

Then test away::

  $ sanity host-list
  csl-a-nova1-[001-004].us-stage-1.cloud.cisco.com
  csl-a-nova2-[001-002,004-010].us-stage-1.cloud.cisco.com
  csl-a-nova3-[001-003].us-stage-1.cloud.cisco.com

Test the whole cloud::

  $ sanity test

Test some hosts only::

  $ sanity test -w 'csl-a-nova1-[001-003].us-stage-1.cloud.cisco.com'

Test one host only::

  $ sanity test -w 'csl-a-nova1-001.us-stage-1.cloud.cisco.com'

For further details run::

  $ sanity -h

And ::

  $ sanity test -h

Advanced Execution
~~~~~~~~~~~~~~~~~~

First source the configuration of the cloud you intend to test, then test away::

  $ sanity shell

  # Connected to https://us-integration-1:5000/v2.0/
  # This is a python shell, it will execute python commands.

  # First thing to do is initialise the environment
  start()

Once started you can initialise the environment::

  us-integration-1 <1>: start()

  Using flavor m1.small
  Using External Net public-floating
  Using Availability Zone <AvailabilityZone: default>
  Using Image centos-7_x86_64
  Creating keypair qaspankey
  Can't find security group qaspansecg
  Creating security group qaspansecg
  Can't find router qa-span-test-router
  Creating router qa-span-test-router
  Can't find network qaspansecg
  Creating network qa-span-network

  # Launch Servers:
  launch_on_each_host()
  launch_on_some_hosts(list_of_hosts)
  launch_on_one_host(hostname)

To launch on a single host use the `launch_on_one_host` function, but there are other functions for launching on all or a subset of hosts::

  us-integration-1 <3>: launch_on_one_host('nova-001')
  Launching on nova-001

  # Enabled tests are:
  test_console()
  test_floatingip()
  test_vncconsole()

  # To run the standard baseline test use:
  run_baseline()

Run some tests on the nodes::

  us-integration-1 <4>: run_baseline()
  Running:  Console Log Check
  100% |################################################################| Time: 0:00:02
  Running:  VNC Console Check
  100% |################################################################| Time: 0:00:02
  Running:  Float Check
  100% |################################################################| Time: 0:00:28

  # To view the results use:
  print_results()

To get a list of the results from the test run::

  us-integration-1 <5>: print_results()
  +----------+--------------------------------------+-------------------+-------------+-------------------+
  | Host ID  |              Server ID               | Console Log Check | Float Check | VNC Console Check |
  +----------+--------------------------------------+-------------------+-------------+-------------------+
  | nova-001 | ce5a8f38-7083-4bbd-a6a5-13e4b9e8cad8 |        PASS       |     PASS    |        PASS       |
  +----------+--------------------------------------+-------------------+-------------+-------------------+
  Untested hosts: nova-002, nova-003, nova-004

  # Once you are happy be sure to clean up using:
  stop()


Stop everything an clean up when finished::

  us-integration-1 <6>: stop()
  Shutting Down Servers
  Deleting <Server: Sanity-nova-001>
  Deleting Subnet
  Deleting Router
  Deleting Network
  Deleting Security Group
  Deleting Keypair
  Deleting Unused floating IPs

Features
--------

* Console log (cloud-init) checking
* VNC console checking
* Floating IP checking
