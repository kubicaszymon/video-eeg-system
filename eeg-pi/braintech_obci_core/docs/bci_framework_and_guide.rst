BCI Framework programming and directory guide
====================================

Peers
-----

.. |Peer| replace:: :class:`~obci.core.peer.Peer`
.. |ConfiguredPeer| replace:: :class:`~obci.core.configured_peer.ConfiguredPeer`

Every Peer (that is a child of |ConfiguredPeer| or |Peer|)
which does some useful work is contained in :mod:`obci.peers` module.

File containing peer class code should be ``snake_case_named`` after the peer it provides. Peer classes should use
``CamelCase`` with last word being Peer.

Example:

We have Peer which does something really important: ::

    class VeryImportantPeer(Peer):
        pass

Which should be placed in appropriate sub-module inside module :mod:`obci.peers` inside file named: ::

    very_important_peer.py

Additionally such module should export that peer using ``__all__`` mechanism, at the start of file there should be code: ::

    __all__ = ('VeryImportantPeer', )

In order to extend peer functionality you have to do the following:

1. Create |Peer| subclass
  - Override :meth:`__init__` to perform some basic initialization, without outside communication
  - Override (async) :meth:`_connection_established` to perform custom initialization, which might take some time ie.
    communicate with other peers (like in |ConfiguredPeer|), or initialize resources. After this method finishes, peer is
    considered to be ready to work. If your additional configuration requires talking to other peers, especialy
    own launch_dependencies, you should use :meth:`_dependencies_are_ready`.
  - Override (async) :meth:`_shutting_down` to perform long cleaunup task ie. inform other peers about something, send messages.
  - Override :meth:`_cleanup` free up acquired resources.
  - Override (async) :meth:`_start` to initialize |Peer| main task (ie start generating and sending data or
    save data to file)
  - Override (async) :meth:`_stop` to stop |Peer| main task (ie turn off amplifier, close file on disk)

2. Write your message handlers methods
  - message handlers should be coroutines
  - message handlers for queries must return response messages
  - message handlers can use (async) :meth:`_send_message` for immediate message sending (:meth:`send_message`
    puts messages on the queue)

3. Register message handlers and subscribe
  - You should register message handler for message types you want to receive by using
    :func:`~obci.core.message_handler_mixin.register_message_handler` decorator on handler method. After that you will be
    able to handle sync (your method must return response message) and async messages
  - In order to receive all async messages of that type  messages you should use :func:`~obci.core.message_handler_mixin.subscribe_message_handler`
    on handler method
  - If you only want to receive messages from certain peer you have to use
    :meth:`~obci.core.message_handler_mixin.MessageHandlerMixin.subscribe_for_specific_msg_subtype` method in
    :meth:`_connections_established`

You can also use peers without subclassing, just instantiate it, wait for connection and use methods:
- :meth:`~obci.core.message_handler_mixin.MessageHandlerMixin.register_message_handler`
- :meth:`~obci.core.message_handler_mixin.MessageHandlerMixin.subscribe`
- :meth:`~obci.core.base_peer.BasePeer.send_message` - to send messages through pub and sub
- :meth:`~obci.core.base_peer.BasePeer.create_task` - to run background asyncio tasks

See :ref:`peer-states` for more info.


Example:

Simple peer which averages signal across channels: ::

    class AveragingPeer(ConfiguredPeer):

        async def _connections_established(self):
            await super()._connections_established()

            # subscribe to signal going from amplifier peer
            # for every SignalMessage self.signal_message_handler function will be called
            self.subscribe_for_specific_msg_subtype(SignalMessage, 'amplifier', self.signal_message_handler)

        async def signal_message_handler(self, msg):
            input = msg.data  # retrieve SamplePacket

            # create new SamplePacket averaged across channels
            output = SamplePacket(ts=input.ts, samples=numpy.mean(input.samples, axis=1, keepdims=True))

            # send created SamplePacket in a SignalMessage
            msg = SignalMessage(data=output)
            await self._send_message(msg)  # every peer subscribed to AveragingPeers SignalMessages will receive this
            # new message and could for example display it
            # such peer could be running on a different computer.




Amplifier drivers
-----------------

Drivers for amplifiers are split between amplifier classes, which derive from
:class:`~obci.drivers.eeg.eeg_amplifier.EEGAmplifier`, and amplifier peers which
utilize those classes derive from :class:`~braintech.obci.experiment.peers.drivers.amplifiers.amplifier_peer.AmplifierPeer`.

Drivers should be placed inside :mod:`obci.drivers.eeg` module and corresponding peers
inside :mod:`obci.peers.drivers.amplifiers` module.

If your driver implements :class:`~obci.drivers.eeg.eeg_amplifier.EEGAmplifier` API and doesn't need any
additional external parameters it is very likely that code for the peer will very concise: ::

    from braintech.obci.experiment.peers.drivers.amplifiers.amplifier_peer import AmplifierPeer
    from braintech.obci.core.drivers.eeg.my_great_amp import MyGreatAmplifier

    __all__ = ('MyGreatAmplifierPeer',)


    class MyGreatAmplifierPeer(AmplifierPeer):
        AmplifierClass = RandomAmplifier

AmplifierPeer class has its own underlying mechanisms to retrieve samples from EEGAmplifier type classes and send
those samples as messages.

BCI Framework driver discovery
---------------------

To make your driver discoverable by BCI Framework driver discovery (i.e. visible in Svarog)
you should do following:

- add amplifier class inside :func:`obci.drivers.eeg.driver_discovery.get_amp_classes_defs`
- additionally add path to the amplifier peer
- add path to the template scenario which can run your amplifier


Scenarios
---------

Scenarios internally for BCI Framework should abide by these rules:
- Scenarios for amplifiers and peers should be located inside ``obci/scenarios/``
- Scenarios which run only amplifiers in different configurations
  (ex to be viewed in Svarog) should be placed in ``obci/scenarios/amplifier/amp_name/``
- Scenarios which save data from your amplifier should be placed in
  ``obci/scenarios/acquisition/amp_name/``
- If you want those scenarios to be visible in obci_gui you should edit
  ``obci/control/gui/presets/default.ini`` file appropriately.

For example scenario which saves signal from Random amplifier: ::

    [peers]
    scenario_dir=
    ;***********************************************


    ;***********************************************
    [peers.config_server]
    path=peers/control/config_server.py


    ;***********************************************
    ; here peers.SOMETHING - SOMETHING is the peer_id for the loaded peer.
    [peers.amplifier]
    path=braintech.obci.experiment.peers.drivers.amplifiers.random_amplifier_peer


    ;***********************************************
    [peers.signal_saver]
    ; path to peers are looked up:
    ; - first: peer .py files:
    ;   * first in the main obci directory
    ;   * directory relative to scenario location
    ;   * global path (including ~ expansion)
    ; - next: importable Python 3 path:
    ;   * like this: path=obci.peers.acquisition.signal_saver_peer
    path=peers/acquisition/signal_saver_peer.py

    [peers.signal_saver.launch_dependencies]
    ; signal saver has external params depending on signal_source
    ; signal source could be any peer, in this case it is random_amplifier_peer
    signal_source=amplifier

