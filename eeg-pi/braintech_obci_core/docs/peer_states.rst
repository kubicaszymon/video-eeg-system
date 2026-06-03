.. _peer-states:

Peer States
===========

.. |Peer| replace:: :class:`~obci.core.peer.Peer`
.. |ConfiguredPeer| replace:: :class:`~obci.core.configured_peer.ConfiguredPeer`

Introduction
------------

Peer state it's its own thing and external classes should **not** make decision based on it's value.
It can change anytime. Only Peer itself should look into its own PeerState.

Implementation
--------------

Each peer has a private property :attr:`_state` and a private dictionary :attr:`_VALID_STATES_TRANSITIONS_`.

:attr:`_state` : indicates current internal state of the peer and
:attr:`_VALID_STATES_TRANSITIONS_ : dict[tuple]` where tuple is container of states to which transition is valid from the
given key state.

If your try to change it state to another, to which change is invalid from current one, then :exc:`AssertionError` will be
called. Currently they are 4 peer states, but each peer can implement it's own in accordance to necessity. Those
states are:

- ``initializing`` - it is a peer state during call of :meth:`__init__` method.
- ``connected`` - indicates that connection to broker has been established. |Peer| can now send,subscribe and  receive
  messages
- ``ready`` - indicates that initialization is complete. For |ConfiguredPeer| that means that all external
  params and config from :class:`ConfigServer` has been updated.
- ``running`` - indicates that peer is ready and that peer is currently working on its main task.
- ``shutting_down`` - indicates that peer is shutting down - :meth:`create_task` and :meth:`send_message`
  are not available.
- ``finished`` - indicates that peer already stopped working - it cannot do anything more, all resources are freed.

In order to find out the state of the peer you can use following methods:

- ``is_connected``
- ``is_ready``
- ``is_running``
- ``is_shutting_down``
- ``is_finished``

Possible changes in states
--------------------------

Valid state transitions declared in :attr:`_VALID_STATES_TRANSITIONS_` are represented in diagram below.

.. code-block:: none

       initializing -------------+
            |                    |
    *------------------------*   |
    |     connected         |    |
    |        |              |    |
    |*-->  ready ----------*|    |
    ||       |             ||    |
    |*--- running <--------*|    |
    |        |              |    |
    *--------|--------------*    |
        shutting down <----------+
             |
          finished

In addition identity transitions are valid.

Example
-------

This test serves as an example how to use peer states, it cycles through PeersStates and shows what function calls are
valid in given PeerStates:

.. literalinclude:: ../test/core/test_base_peer.py
   :pyobject: test_peer_state_flow


Messages
--------

There is one message which changes peer state - :class:`PeerControlMessage`.
In addition to `peer_id` (sender of message) it takes `action` parameter, which can take arbitrary (string) value.
Currently it is only checked against:

- ``start`` : peers :meth:`~obci.core.peer.Peer._start()` method is awaited, effectively changing peers state to ``running``
- ``stop``  : peers :meth:`~obci.core.peer.Peer._stop()` method is awaited, effectively changing peers state to ``ready``
- ``close`` : peers :meth:`~obci.core.peer.Peer.async_shutdown()` method is awaited, effectively closing the peer


There are also other messages, send by peer to inform others about state change:

- :class:`PeerReady` - sent by |ConfiguredPeer| when state changes from ``connected`` to ``ready``, to inform Broker
  and ConfigServer about finishing initialization.
- :class:`PanickMsg` - sent by |Peer| when it is shutting down with error
- :class:`BrokerGoodbyeMsg` - sent by |Peer| on shutdown

