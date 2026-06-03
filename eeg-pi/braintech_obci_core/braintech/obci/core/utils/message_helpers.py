# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""
Module with coroutines for sending specific messages using Peer class.

Author:
     Mateusz Kruszyński <mateusz.kruszynski@titanis.pl>
     Marian Dovgialo <marian.dowgialo@braintech.pl>
"""
from braintech.obci.core.broker import messages
from .tags_helper import LOGGER


async def send_finish_saving(peer):
    """
    Send finish saving command to signal savers from peer (Peer class) event loop.

    Doesn't wait for saving to finish.
    :param peer: Peer or child of Peer
    """
    peer.send_message(messages.AcquisitionControlMessage(sender=peer.peer_id, data='finish'))


async def send_finish_video_saving(peer):
    """
    Send finish saving command to video savers from peer (Peer class) event loop.

    Doesn't wait for saving to finish.
    :param peer: Peer or child of Peer
    """
    peer.send_message(messages.FinishSavingVideoMsg(sender=peer.id))


async def send_start_video_saving(peer, path, url):
    """
    Method sends start saving video command to video savers from peer (Peer class) event loop.

    Doesn't wait for saving to finish.
    :param peer: Peer or child of Peer
    """
    peer.send_message(messages.SaveVideoMsg(sender=peer.id, URL=url, PATH=path))


async def send_tag(peer, p_start_timestamp, p_end_timestamp, p_tag_name, p_tag_desc=None, p_tag_channels: str="",
                   p_tag_id: str=""):
    """
    For given parameters create tag and send it to mx.

    :param peer: Peer or child of Peer
    :param p_start_timestamp: float
    :param p_end_timestamp: float
    :param p_tag_name: string
    :param p_tag_desc: dictionary
    :param p_tag_channels: string like "0 6 7" - numbers of channels
    :param p_tag_id: string (UUID) for completing incomplete tags, can be an empty string for no ID
    """
    p_tag_desc = p_tag_desc or {}
    l_info_desc = ''.join(
        ["Sending tag:\n",
         "start:", repr(p_start_timestamp),
         ", end:", repr(p_end_timestamp),
         ", name:", p_tag_name,
         ", channels:", p_tag_channels])
    LOGGER.debug(l_info_desc + "DESC: " + str(p_tag_desc))
    msg_data = {
        'id': p_tag_id,
        'sender': peer.id,
        'start_timestamp': p_start_timestamp,
        'end_timestamp': p_end_timestamp,
        'name': p_tag_name,
        'desc': p_tag_desc
    }
    tag_msg_type = messages.IncompleteTagMsg if p_end_timestamp is None else messages.TagMsg
    msg = tag_msg_type(**msg_data)
    peer.send_message(msg)


async def send_unpacked_tag(peer, p_tag_dict):
    """
    A helper method to send tag in dictionary format.

    :param peer: Peer or child of Peer
    :param p_tag_dict: dictionary with items: start_timestamp, end_timestamp,
                       name, desc(dict), channels, as in send_tag helper
                       function
    """
    await send_tag(peer, p_tag_dict['start_timestamp'],
                   p_tag_dict['end_timestamp'],
                   p_tag_dict['name'],
                   p_tag_dict.get('desc', {}),
                   p_tag_dict.get('channels', ''),
                   p_tag_dict.get('id', ''))
