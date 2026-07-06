from enum import Enum


class Channel(Enum):
    ALPHA = 1
    BETA = 2


def channel_default() -> Channel:
    return Channel.ALPHA
