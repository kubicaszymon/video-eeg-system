# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module proving utility base class for writing singleton apps."""
from braintech.utils.singleton_app import SingleInstanceException, SingleApplicationInstance

# for compatability reasons - reexport it here
__all__ = ('SingleInstanceException', 'SingleApplicationInstance')
