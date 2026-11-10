# Enum fixture: Channel's supertypes climb out of the project into the stdlib
# typeshed stubs, and usages of ALPHA include its own declaration line plus
# the member access in channel_default.
from enum import Enum


class Channel(Enum):
    ALPHA = 1
    BETA = 2


def channel_default() -> Channel:
    return Channel.ALPHA
