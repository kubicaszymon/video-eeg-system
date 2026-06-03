New peer architecture
=====================

:class:`~obci.core.peer.Peer` and :class:`~obci.core.broker.Broker` derive from
:class:`~obci.core.base_peer.BasePeer` class.
:class:`~obci.core.base_peer.BasePeer` is derived from
:class:`~obci.core.zmq_asyncio_task_manager.ZmqAsyncioTaskManager`.
:class:`~obci.core.zmq_asyncio_task_manager.ZmqAsyncioTaskManager` is derived
from :class:`~obci.core.asyncio_task_manager.AsyncioTaskManager`.

:class:`~obci.core.asyncio_task_manager.AsyncioTaskManager` manages a set of
tasks running inside :mod:`asyncio` message loop. Message loop can be owned by
:class:`~obci.core.asyncio_task_manager.AsyncioTaskManager` or borrowed. When
message loop is owned new message loop is started in a new thread.

:class:`~obci.core.zmq_asyncio_task_manager.ZmqAsyncioTaskManager` adds ZMQ
asyncio context lifetime management to
:class:`~obci.core.asyncio_task_manager.AsyncioTaskManager`. ZMQ context can be
borrowed or owned.

:class:`~obci.core.base_peer.BasePeer` extends
:class:`~obci.core.zmq_asyncio_task_manager.ZmqAsyncioTaskManager` by adding
three ZMQ sockets:

* SUB used to receive broadcast messages, connects to Broker's XPUB
* PUB used to send broadcast messages, connects to Broker's XSUB
* REP used to answer synchronous messages (messages requiring an answer)

In ZMQ 3+ messages are filtered on PUB socket, so no redundant messages will be
sent to clients.

:class:`~obci.core.broker.Broker` extends
:class:`~obci.core.base_peer.BasePeer` by adding:

* XPUB/XSUB message proxy
* centralized peer registration authority
* query authority
* heartbeat monitor

:class:`~obci.core.peer.Peer` extends :class:`~obci.core.base_peer.BasePeer` by
adding:

* initialization code/Broker connection code
* heartbeat message sending
