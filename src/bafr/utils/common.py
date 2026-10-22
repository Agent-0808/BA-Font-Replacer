# utils/common.py
"""
Adapted from [BA-Modding-Toolkit](https://github.com/Agent-0808/BA-Modding-Toolkit)
"""

from typing import Callable


def no_log(message):
    """A dummy logger that does nothing."""
    pass


LogFunc = Callable[[str], None]
