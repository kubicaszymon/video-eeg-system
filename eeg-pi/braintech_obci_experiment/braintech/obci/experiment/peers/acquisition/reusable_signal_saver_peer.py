# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from braintech.obci.experiment import messages
from braintech.obci.core.broker import messages as messages_core
from braintech.obci.core.broker.message_handler_mixin import subscribe_message_handler
from braintech.obci.experiment.peers.acquisition import signal_saver_peer

__all__ = ('ReusableSignalSaver',)


class ReusableSignalSaver(signal_saver_peer.SignalSaver):
    FILE_EXTENSIONS = {
        'data': '.raw',
        'info': '.xml',
        'tag': '.tag'
    }

    def __init__(self, urls, *args, **kwargs):
        super().__init__(urls, *args, **kwargs)
        assert self.config.local_params['autostart'] == '0'
        assert self.config.local_params['autoshutdown'] == '0'

    @subscribe_message_handler(messages.StartSavingSignal)
    async def _start_saving_signal(self, message):
        if self._session_is_active:
            self._logger.error("Got StartSavingSignal while still processing "
                               "another job.")
            return messages.SignalSavingError("Signal saving is already in "
                                              "progress.")
        else:
            self._set_save_path_prefix(message)
            self._logger.info('Got StartSavingSignal {}. Will save files in: "{}". '
                              'Prefix: "{}".'
                              .format(vars(message),
                                      self.get_param('save_file_path'),
                                      self.get_param('save_file_name')))
            await self._start()
            return messages.SignalSavingStarted()

    def _set_save_path_prefix(self, message):
        self.set_param('save_file_path', message.save_file_path)
        if message.save_file_name:
            self.set_param('save_file_name', message.save_file_name)

    async def _handle_tag(self, msg: messages_core.TagMsg):
        await super()._handle_tag(msg)
        return messages_core.OkMsg()

    async def _signal_message_handler(self, msg):
        try:
            await super()._signal_message_handler(msg)
        except Exception as e:
            await self._stop()
            message = messages.SignalSavingError(details=str(e))
            self.send_message(message)

    @subscribe_message_handler(messages.StopSavingSignal)
    async def _stop_saving_signal(self, _):
        if self._session_is_active:
            self._logger.info('Got StopSavingSignal. Saving files in: "{}". '
                              'Prefix: "{}".'
                              .format(self.get_param('save_file_path'),
                                      self.get_param('save_file_name')))
            await self._stop()
            return messages.SavingSignalStopped()
        else:
            was_processing = bool(self.get_param('save_file_path'))
            if was_processing:
                self._logger.warning("Got StopSavingSignal when not "
                                     "processing anymore.")
                return messages.SavingSignalStopped()
            else:
                return messages.SignalSavingError("Trying to stop never "
                                                  "started saving.")
