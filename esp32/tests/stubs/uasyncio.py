# Stub CPython: fa sembrare asyncio come uasyncio MicroPython.
from asyncio import (sleep, create_task, run, gather, wait_for,  # noqa: F401
                     TimeoutError, CancelledError)


def sleep_ms(ms):
    return sleep(ms / 1000.0)
