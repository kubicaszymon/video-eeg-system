# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module defines helper methods for tag 'pack_tag_from_tag', and 'unpack_tag', and 'pack_tag'."""
from braintech.obci.core.broker import messages
from braintech.obci.core.utils import openbci_logging as logger

LOGGER = logger.get_logger('tags_helper', 'info')


def pack_tag_from_tag(tag_dict):
    """Return serializes tag with given values."""
    return pack_tag(tag_dict['start_timestamp'], tag_dict['end_timestamp'],
                    tag_dict['name'], tag_dict['desc'], tag_dict['channels'])


def pack_tag(p_start_timestamp, p_end_timestamp,
             p_tag_name, p_tag_desc=None, p_tag_channels=""):
    """
    Return tag with given values.

    :param float p_start_timestamp:
    :param float p_end_timestamp:
    :param string p_tag_name:
    :param dict p_tag_desc:
    :param string like "0 6 7" p_tag_channels: numbers of channels

    :return l_tag: serialised to string
    """
    p_tag_desc = p_tag_desc or {}
    l_tag = messages.TagMsg(start_timestamp=p_start_timestamp,
                            end_timestamp=p_end_timestamp,
                            name=p_tag_name,
                            channels=p_tag_channels,
                            desc=p_tag_desc)
    return l_tag
