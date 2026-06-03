# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

""""Module defines a single class OBCIServerPeer."""
from typing import Union

from braintech.obci.core.broker import messages
from ..messages.launcher_msg_types import KillExperimentMsg
from braintech.obci.core.broker.peer import Peer, PeerInitUrls

END_LOG = 'end_logs'
__all__ = ('OBCIServerPeer',)


class OBCIServerPeer(Peer):
    """Peer subscribes for LOG and SENTRY msgs."""

    def __init__(self, urls: Union[str, PeerInitUrls], experiment_id, obci_server,
                 log_source_name: str = '', **kwargs):
        """Create a new OBCIServerPeer every time when experiment is fired."""
        self.obci_server = obci_server
        self.experiment_id = experiment_id
        self.log_source_name = log_source_name
        self.message_handler = {KillExperimentMsg.type: self._handle_kill_experiment}
        self.peer_id = 'obci_server_{}'.format(self.experiment_id)
        kwargs['peer_id'] = self.peer_id
        super().__init__(urls, **kwargs)

    async def _connections_established(self) -> None:
        await super()._connections_established()
        for msg_type, handler in self.message_handler.items():
            self.subscribe_for_all_msg_subtype(msg_type, self._handle_obci_message)

    def _handle_obci_message(self, msg: messages.BaseMessage):
        msg.source = self.log_source_name
        self.message_handler[msg.type](msg)

    def _handle_kill_experiment(self, msg):
        msg.strname = self.experiment_id

        class SocketMock:
            # Workaround: handler on obci_server is meant for old message types and requires socket.
            socket_type = 'other_type'
            _msg = ''

            def send_multipart(self, msg, flags=0):
                self._msg = msg

        mock_socket = SocketMock()
        self.obci_server.handle_kill_experiment(msg, mock_socket)
        return mock_socket._msg

    # This peer is being shutdown AFTER broker is closed, so it might try to send heartbeats to
    # non existing broker and fail horribly
    async def _heartbeat(self):
        try:
            await super()._heartbeat()
        except Exception:
            pass
