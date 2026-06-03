# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""
Module providing dummy tag sender peer.

Author:
     Mateusz Kruszyński <mateusz.kruszynski@gmail.com>
"""
import asyncio
import random
import time

from braintech.obci.experiment.peer.configured_peer import ConfiguredPeer
from braintech.obci.core.utils.message_helpers import send_tag

COLORS = ['czerwony', 'zielony', 'niebieski', 'bialy']
NAMES = ['pozytywny', 'negatywny', 'neutralny']
__all__ = ('AutoTagGenerator',)


class AutoTagGenerator(ConfiguredPeer):
    """Peer which randomly sends meaningless tags."""

    async def _start(self):
        await super()._start()
        self.create_task(self._run())

    async def _run(self):
        while True:
            await asyncio.sleep(1.0 + random.random() * 10.0)
            name = NAMES[random.randint(0, len(NAMES) - 1)]

            t = time.time()
            self._logger.info("SEND TAG name " + name + " with time: " + repr(t))
            if name == 'pozytywny' or name == 'negatywny':
                await send_tag(self, t, t + 1.0, name,
                               {'czestosc': random.randint(0, 10),
                                'liczba': random.random(),
                                'wypelnienie': COLORS[random.randint(0, len(COLORS) - 1)],
                                'tekst': " d jfsld fkjew lkgjew lkgjewlkg jewg ldsj glkds jglkdsg jlkdsg jds"
                                }
                               )
            else:
                await send_tag(self, t, t + 1.0, name, {'czestosc': random.randint(0, 10),
                                                        'wypelnienie': COLORS[random.randint(0, len(COLORS) - 1)],
                                                        'poziom': random.randint(100, 1000)
                                                        }
                               )
