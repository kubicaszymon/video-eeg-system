# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from braintech.obci.core.control.common import net


def diff_scenarios(old_config, new_config, leave_on):
    kill_list = []
    for peer in old_config.peers:
        if peer not in new_config.peers:
            kill_list.append(peer)
    launch_list = []
    for peer in new_config.peers:
        if peer not in old_config.peers:
            launch_list.append(peer)

    for peer in new_config.peers:
        if (peer in old_config.peers and peer not in leave_on and
                peer not in ['config_server']):
            kill_list.append(peer)
            launch_list.append(peer)

    return kill_list, launch_list


def validate_morph_leave_on(old_config, new_config, leave_on):
    for peer_id in leave_on:

        old_p = old_config.peers.get(peer_id, None)
        new_p = new_config.peers.get(peer_id, None)
        if old_p is None or new_p is None:
            message = ("Peer id {} present old config: {}, present in new "
                       "config: {}"
                       .format(peer_id, old_p is not None, new_p is not None))
            return False, message
        if old_p.path != new_p.path:
            message = ("Peer ids [{}] point to different programs: old: {}, "
                       "new: {}"
                       .format(peer_id, old_p.path, new_p.path))
            return False, message

        old_machine = old_p.machine if old_p.machine else net.gethostname()
        new_machine = new_p.machine if new_p.machine else net.gethostname()

        if old_machine != new_machine:
            message = ("Peer id {} is to be launched on a different machine: "
                       "old: {}, new:{}"
                       .format(peer_id, old_machine, new_machine))
            return False, message
        else:
            return True, ""
