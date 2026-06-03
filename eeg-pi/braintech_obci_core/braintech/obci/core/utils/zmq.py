# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""This module implements some utility functions associated with ZMQ and managing IP addresses."""

import socket
import urllib.parse
from typing import List, Optional, Tuple, Iterable, Set, Dict

import zmq
import zmq.asyncio

from braintech.obci.core.broker import ObciException


def normalize_urls(urls: Iterable[str]) -> Set[str]:
    """
    Normalize ZMQ specific URLs to the form parsable by `urllib.parse.urlparse`.

    Hostname and port wildcards ('*') are normalized to respectively '0.0.0.0'
    and '0'.

    :param urls: list of URLs to normalize
    :return: set containing normalized URLs
    """
    normalized_urls = set()
    for url_str in urls:
        url = urllib.parse.urlparse(url_str)

        if url.scheme != 'tcp':
            normalized_urls.add(url_str)
            continue

        # replace ZMQ specific '*' in hostname with '0.0.0.0'
        hostname = '0.0.0.0' if url.hostname in {'*', '0.0.0.0', '0.0.0', '0.0', '0'} else url.hostname
        ip = socket.gethostbyname(hostname)

        # cannot directly access url.port, because url lib expects it to be int
        port = url.netloc.split(':')[-1] if ':' in url.netloc else '0'

        # normalize undefined port to '0', so that
        # urllib.parse.urlparse can properly parse
        # port number
        port = '0' if port in {'', '*'} else port

        normalized_urls.add('tcp://{}:{}'.format(ip, port))
    return normalized_urls


def _split_and_process_urls(urls: Iterable[str]
                            ) -> Tuple[Dict[str, Set[int]], Set[str]]:
    unique_ips = {}
    other_urls = set()
    for url_str in urls:
        url = urllib.parse.urlparse(url_str)
        if url.scheme != 'tcp':
            other_urls.add(url_str)
            continue
        ip = url.hostname
        if ip in unique_ips:
            unique_ips[ip].add(url.port)
        else:
            unique_ips[ip] = {url.port}
    return unique_ips, other_urls


def determine_new_urls_to_bind(urls: Iterable[str],
                               current_urls: Optional[Iterable[str]] = None
                               ) -> Set[str]:
    """
    Determine minimal subset of URLs to bind.

    :param urls: URLs to bound
    :param current_urls: list of currently bound URLs
    :return: new URLs to bind
    """
    urls = normalize_urls(urls)
    current_urls = set() if current_urls is None else normalize_urls(current_urls)
    unique_ips, other_urls = _split_and_process_urls(current_urls)

    # determine a list of URLs to bind
    urls_to_bind = set()
    for url_str in urls:
        url = urllib.parse.urlparse(url_str)

        if url.scheme != 'tcp' and url_str not in other_urls:
            urls_to_bind.add(url_str)
            continue

        if url.hostname in unique_ips:
            if url.port == '0' and len(unique_ips[url.hostname]) > 0:
                # skip, because we are already bound to some port on this IP
                continue
            elif url.port not in unique_ips[url.hostname]:
                # we are not bound to specified port on this IP
                urls_to_bind.add(url_str)
        else:
            # this is new IP
            urls_to_bind.add(url_str)
    return urls_to_bind


def bind_to_urls(zmq_socket: zmq.Socket,
                 urls_to_bind: Iterable[str],
                 ) -> Tuple[List[Exception], Set[str]]:
    """
    Bind ZMQ socket to a given list of URLs.

    List of exceptions and a list newly bounded URLs is returned.

    `urls_to_bind` are assumed to contain only IP addresses, not hostnames.
    Name resolution must be performed before calling this function.

    TCP URLs form `urls` list CAN contain host or port as specified as wildcard '*'.

    :param zmq_socket: ZMQ socket to bind
    :param urls_to_bind: list of URLs to bind to
    :return: 2-tuple: fist element - list of exceptions, second element - list of newly bounded URLs
    """
    new_listening_urls = set()
    exceptions = []
    for url in urls_to_bind:
        try:
            zmq_socket.bind(url)
            real_url = zmq_socket.getsockopt(zmq.LAST_ENDPOINT)
            if real_url:
                new_listening_urls.add(real_url.decode())
        except Exception as ex:
            exceptions.append(ex)
    return exceptions, new_listening_urls


class TimeoutException(ObciException):
    """Raised by `recv_multipart_with_timeout` when timeout is reached."""
