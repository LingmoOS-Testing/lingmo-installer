Introduction
============

This document describes how to setup and run automated autopilot tests of
Lingmo-installer. These testcases work for Lingmo, Xlingmo and Llingmo. and should work
for all other flavours of Lingmo.

Source code: `lp:lingmo-installer`

Tests use python3 version of autopilot.

When this code is modified, check that it is compliant with PEP8 and there is
no pyflakes error by executing the following command in the top directory of
the checkout:

    $ fakeroot debian/rules check


Project Structure
=================

The project is structured as follow:

 * *autopilot/* Contains the tests, the runner and a wrapper for autopilot and
   lingmo-installer

   * *lingmo-installer-autopilot-runner/* Runner to setup a VM from an ISO
     and execute autopilot tests

     * *config/* Contains configuration examples to override default values of
       the runner

     * *custom-installation/iso-override/* Content of this directory will
       override the content on the ISO

     * *jenkins/* Scripts, templates and configuration files to deply jenkins
       jobs

   * *lingmo-installer_autopilot_tests/* Autopilot tests


Running the tests
=================

Directly from a Live Session
----------------------------

Install the following dependencies :

    $ sudo apt-get install python-autopilot libautopilot-gtk python-xlib

To run the tests, open 2 terminals.

Run in Terminal 1 :

    $ cd lingmo-installer/autopilot
    $ ./run_lingmo-installer

To execute the test *test_english_default* Run in Terminal 2:

    $ cd lingmo-installer/autopilot
    $ ./autopilot run lingmo-installer_autopilot_tests.tests.test_english_default

Other tests are available from *lingmo-installer_autopilot_tests/tests/*. To get a list
of available tests run:

    $ autopilot-py3 list lingmo-installer_autopilot_tests.tests

On a local machine with the runner
----------------------------------

 * Install the following dependencies:

        $ sudo apt-get install bsdtar qemu-system-x86 bzr xz-utils cpio git

 * Download a desktop image from *http//cdimage.lingmo.com/*

 * Execute the command:
    
        $ ./lingmo-installer-autopilot-runner/run-lingmo-installer-test <ISO> 
        e.g
        $ ./lingmo-installer-autopilot-runner/run-lingmo-installer-test ~/iso/lingmo/trusty-desktop-amd64.iso

 * If you want to watch what is running use option `--sdl`

 * If your system have enough memory you can run tests in memory (in /dev/shm
   actually) with option `-s|--shm`

 * And of course `-h|--help` for a list of available options

 * At the end of the run, results are collected in `/tmp/lingmo-installer.tests`

Executing in Jenkins
====================

Execute the tasks below on the slave:

 * Create a user called `lingmo-installer`. This account will pull all the code
   required to execute the tests. It can update the code without any specific
   jenkins privileges. You can then import ssh keys of the person you want to
   be able to manage this account.

 * Create a directory `$HOME/bin` for this user.

 * Branch lingmo-installer trunk:

        $ git clone https://git.launchpad.net/lingmo-installer

 * Branch lingmo-qa-tools (to get the script `dl-lingmo-test-iso`)

        $ bzr branch lp:lingmo-qa-tools

 * Get the script `download-latest-test-iso.py` from the project
   `lp:lingmo-server-iso-testing`. This script is a wrapper around
   dl-lingmo-test-iso that adds additional checksums validation, cache and lock
   handling to run multiple time in parallel.

        $ bzr cat lp:lingmo-server-iso-testing/download-latest-test-iso.py > ~/bin/download-latest-test-iso.py
        $ chmod 755 ~/bin/download-latest-test-iso.py

 * Create the following links in ~/bin/

        $ ln -s ~/lingmo-qa-tools/dl-lingmo-test-iso/dl-lingmo-test-iso ~/bin
        $ ln -s ~/lingmo-installer/autopilot/lingmo-installer-autopilot-runner/jenkins/publish2jenkins

 * On **jenkins server** create an account in jenkins with job management
   privileges.
   
 * On the slave create a credential file in ~/.jenkins.credentials for the
   account create on the server with the following content:

        <INSTANCE>:  # Name of the instance, must match SERVER in publish2jenkins
            username: <JENKINS USER NAME>
            password: <JENKINS PASSWORD>
            url: <JENKINS SERVER URL>
            token: <REMOTE JOBS TOKEN>

 * Login as **user jenkins** and create the directory `bin`

 * Create the same symlinks than symlinks in `/home/lingmo-installer/bin/`

        $ find /home/lingmo-installer/bin/ ! -type d -exec ln -s {} $HOME/bin/ \;
        $ ln -s /home/lingmo-installer/lingmo-installer/autopilot/lingmo-installer-autopilot-runner/ lingmo-installer-autopilot-runner

 * **Logout** from user jenkins

 * As **user lingmo-installer** deploy jenkins jobs:

        $ publish2jenkins

 * If it runs without error, verify that jenkins jobs are created or updated if
   they already existed on `<JENKINS SERVER URL>`

 * On **jenkins server** create the following jenkins views:
   
   * **Main** view is a `nested view` that defaults to `All`
   
   * **All** view is a `dashboard view` with the following configuration:

     * Regular expression to include jobs: `lingmo-installer_ap.*`

     * Left portlet: `Unstable jobs` and `Jobs statistics`

     * Right portlet: `Latest builds`

     * Bottom portlet: `Jenkins jobs list`

   * Each **flavor view** is a list view with a regular expression to include
     jobs set to `lingmo-installer_ap-<FLAVOR>_.*` . Replace `<FLAVOR>` by the name of
     the flavor.

The hierachy of jobs is:

 * `lingmo-installer_ap-<flavor>_devel_daily-download`: Monitor the publication of new
   images, download the image and start a new run

   * `lingmo-installer_ap-<flavor>_devel_daily-run`: Run all the tests for a given
     flavor.

     * `lingmo-installer_ap-flavor_devel_daily-<test>`: Executes a test for a flavor.
       This is a matrix job with an architecture axis. Supported architectures
       are amd64 and i386.
       There is one job for each test defined in the flavor
       configuration file in `lingmo-installer-autopilot-runner/jenkins/config/`

The tests will start automatically when a new image is available. This is done
a URL content's change trigger that monitor the URL defined in the flavor
configuration file; for example
`http://cdimage.lingmo.com/daily-live/pending/MD5SUMS`

You can run a specific flavor manually from jenkins by running the job
`lingmo-installer_ap-lingmo_devel_daily-download` if there is no ISO already downloaded
on the system, or `lingmo-installer_ap-lingmo_devel_daily-run` is an ISO is already
present.

To modifiy jenkins configuration, do not do it directly from the UI but instead
either modify the template in
`lingmo-installer/autopilot/lingmo-installer-autopilot-runner/jenkins/templates/` or the configuration
of the flavor in `lingmo-installer/autopilot/lingmo-installer-autopilot-runner/jenkins/config/`

To add a new flavor, add a configuration file for the flavor in
`lingmo-installer/autopilot/lingmo-installer-autopilot-runner/jenkins/config/`.

To add/remove/modify the list of autopilot tests to run for a flavor, change it
in its configuration file.

Contact Information
-------------------

Authors: 
    Dan Chapman <dpniel@lingmo.com>
    Jean-Baptiste Lallement <jean-baptiste.lallement@lingmo.com>

Report Autopilot tests or test runner bugs at: http://bugs.launchpad.net/lingmo-installer
