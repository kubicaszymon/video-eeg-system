BCI Framework commands
================

Following commands are available from command line:

* ``obci srv`` - start BCI Framework Server
* ``obci srv_kill`` - shutdown BCI Framework Server and all experiments it is running
* ``obci gui`` - GUI for starting/stopping and monitoring experiments
* ``obci launch`` - launch experiment by specifying **scenario file**
* ``obci add`` - add a peer to a currently running experiment
* ``obci remove`` - remove a peer from a currently running experiment
* ``obci kill`` - shutdown BCI Framework experiment
 * additional ``--force`` flag shutdowns experiment immediately, peers hove no chance to react and finalize their work
* ``obci info`` - display information about BCI Framework Servers and experiments
  running on current machine and on nearby hosts
* ``obci report_error`` Show window for reporting error to Braintech.
