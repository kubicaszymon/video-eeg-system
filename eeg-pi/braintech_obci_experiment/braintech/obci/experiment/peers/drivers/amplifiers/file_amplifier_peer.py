# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module providing File Amplifier."""
import os

from braintech.obci.core.drivers.eeg.read_manager_amplifier import ReadManagerAmplifier
from braintech.obci.core.utils.message_helpers import send_unpacked_tag
from braintech.obci.experiment.peers.drivers.amplifiers.amplifier_peer import AmplifierPeer, register_amplifier_peer

__all__ = ('FileAmplifierPeer',)


@register_amplifier_peer
class FileAmplifierPeer(AmplifierPeer):
    """Amplifier Peer, which uses raw EEG file as data source."""

    AmplifierClass = ReadManagerAmplifier

    def _manage_files(self):
        self.f_data = os.path.expanduser(os.path.join(
            self.config.get_param('data_file_dir'),
            self.config.get_param('data_file_name')) + '.obci.raw')

        i_dir = self.config.get_param('info_file_dir')
        if len(i_dir) == 0:
            i_dir = self.config.get_param('data_file_dir')
        i_name = self.config.get_param('info_file_name')
        if len(i_name) == 0:
            i_name = self.config.get_param('data_file_name')
        self.f_info = os.path.expanduser(os.path.join(i_dir, i_name) + '.obci.xml')

        t_dir = self.config.get_param('tags_file_dir')
        if len(t_dir) == 0:
            t_dir = self.config.get_param('data_file_dir')
        t_name = self.config.get_param('tags_file_name')
        if len(t_name) == 0:
            t_name = self.config.get_param('data_file_name')
        self.f_tags = os.path.expanduser(os.path.join(t_dir, t_name) + '.obci.tag')

    def _manage_params(self):
        self._manage_files()
        self._amplifier.info_source = self.f_info
        self._amplifier.data_source = self.f_data
        self._amplifier.tags_source = self.f_tags
        if self.autostart:
            self._amplifier.init()
        self.sampling_rate = self._amplifier.sampling_rate
        self.active_channels = self._amplifier.active_channels
        super()._manage_params()

    def reset(self):
        """Reset the amplifier."""
        self._amplifier.init()
        self._amplifier.sampling_rate = self.sampling_rate

    async def _post_send(self):
        tags = self._amplifier.get_tags()
        if tags:
            for tag in tags:
                await send_unpacked_tag(self, tag)
