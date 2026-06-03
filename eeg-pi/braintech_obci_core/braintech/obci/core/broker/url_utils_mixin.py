# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module defines Mixin :class:`UrlUtilsMixin` and small helper method `split_ipv4_address`."""
import urllib.parse
from typing import Iterable, Optional, Set, Tuple

import zmq

from . import ObciException
from braintech.obci.core.utils.net import get_all_ip4_addresses
from braintech.obci.core.utils.zmq import (bind_to_urls,
                                           determine_new_urls_to_bind,
                                           normalize_urls)


def split_ipv4_address(ip4_address: str, default_port: int) -> Tuple[str, int]:
    """
    A helper method to split ip address and port and return it as a tuple[``str``, ``int``].

    :return: broker address and port
    :raises: ObciException if TCP/IP address is invalid
    """
    broker_address = ip4_address.strip().split(':')
    if len(broker_address) == 1:
        return broker_address[0], default_port
    elif len(broker_address) == 2:
        return broker_address[0], int(broker_address[1])
    else:
        raise ObciException('Invalid TCP/IP address: {}'
                            .format(broker_address))


class UrlUtilsMixin:
    """When Peer and Broker will be merged this will be in BasicPeer."""

    def __init__(self) -> None:
        """Mixin :class:`UrlUtilsMixin` assumes ``self._logger`` exists."""
        super().__init__()

    def _bind_to_urls(self,
                      socket: zmq.Socket,
                      urls: Iterable[str],
                      current_urls: Optional[Iterable[str]] = None
                      ) -> Set[str]:
        current_urls = set() if current_urls is None else normalize_urls(current_urls)
        urls_to_bind = determine_new_urls_to_bind(urls, current_urls)
        exceptions, new_urls = bind_to_urls(socket, urls_to_bind)
        if exceptions:
            for ex in exceptions:
                self._logger.warning('Error in bind_to_urls: %s', ex)
        return current_urls.union(new_urls)

    @staticmethod
    def _normalize_url_set(url_set: Set[str]) -> None:
        all_ipv4_addresses = get_all_ip4_addresses()
        for url_str in list(url_set):
            url = urllib.parse.urlparse(url_str)
            if url.scheme != 'tcp':
                continue
            elif url.hostname == '0.0.0.0':
                url_set.remove(url_str)
                for ip in all_ipv4_addresses:
                    url_set.add('tcp://{}:{}'.format(ip, url.port))

    @staticmethod
    def _split_ipv4_address(ip4_address: str, default_port: int) -> Tuple[str, int]:
        return split_ipv4_address(ip4_address, default_port)

    @staticmethod
    def _find_port_for_ip(urls, ip):
        """
        Given ``ip`` address and ``urls`` list find port number for specified `ip`.

        :param urls: list of URLs
        :param ip: IP to search
        :return: port number or None
        """
        for url_str in urls:
            url = urllib.parse.urlparse(url_str)
            if url.hostname == ip or url.hostname == '0.0.0.0':
                return url.port
        return None
