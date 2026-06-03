#!/usr/bin/env python3
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module providing url/ip utility functions."""
from typing import List, Union

import netifaces


def get_all_ip4_addresses() -> List[str]:
    """Return list of all available ipv4 addresses on this machine."""
    ip_list = []
    for interface in netifaces.interfaces():
        addr = netifaces.ifaddresses(interface)
        if netifaces.AF_INET in addr:
            for link in addr[netifaces.AF_INET]:
                if 'addr' in link:
                    ip_list.append(link['addr'])
    return ip_list


def change_ports_of_addrs(address: str, port: Union[str, int]) -> str:
    """
    Change port in address to a new port.

    :param address: string of address with port
    :param port: string or int with new port number
    :return: address with new port
    """
    port = str(port)
    addr_l = address.split(':')[:-1]  # list of address parts without port
    addr_l.append(port)
    new_address = ':'.join(addr_l)
    return new_address


if __name__ == '__main__':
    print('IPv4:', get_all_ip4_addresses())
