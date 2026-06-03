SignalMessage
=============

One of the most crucial message types is
:class:`~obci.core.messages.types.SignalMessage`. It is responsible for
transferring data from amplifier to all concerned obci peers and components.
It has one attribute :class:`~obci.core.messages.types.SignalMessage.data` which is an instance of
:class:`~braintech.obci.signal_processing.signal.data_generic_write_proxy.SamplePacket`
sent by an amplifier.

SamplePacket
------------

SamplePacket is a structure responsible for encoding and decoding data from
an amplifier. The encoded data varies depending on the number of channels,
the number of samples per channel which were send, whether or not amplifier
supports impedance computation, impedance per channel (if present) and
timestamps.

If amplifier does not support impedance or impedance is not applicable /
unknown for the active channels then the impedance data won't be sent.

If amplifier does not support impedance then the impedance flags won't be sent.

Types of data being sent:

* HEADER (type: ushort[])

  - SAMPLE_COUNT: number of samples per packet
  - CHANNEL_COUNT: number of channels per packet

* TIMESTAMPS (type: float64[])
* SAMPLES (type: float32[])

  - IMPEDANCE_FLAGS (type: int8[])
  - UNKNOWN == 0
  - NOT_APPLICABLE == 1
  - PRESENT == 2

* IMPEDANCE_DATA (type: float32[])

The structure of a SamplePacket should look like this:

.. code-block:: none

    *-------------------------------*
    |            HEADER             |
    | (SAMPLE_COUNT, CHANNEL_COUNT) | <- ushort[]
    |                               |
    *-------------------------------*
    |          TIMESTAMPS           | <- float64[]
    *-------------------------------*
    |                               |
    |                               |
    |           SAMPLES             | <- float32[]
    |                               |
    |                               |
    *-------------------------------*
    |       IMPEDANCE_FLAGS         | <- int8[]
    |                               |
    |     (may not be present)      |
    *-------------------------------*
    |                               |
    |        IMPEDANCE_DATA         | <- float32[]
    |                               |
    |     (may not be present)      |
    |                               |
    *-------------------------------*

There is one amplifier in obci which sends impedance data for every second
channel - this is :class:`~obci.core.drivers.eeg.random_amplifier.RandomAmplifier`.
It is recommended to use :class:`~braintech.obci.experiment.peers.drivers.amplifiers.random_amplifier_peer.RandomAmplifierPeer` with it.