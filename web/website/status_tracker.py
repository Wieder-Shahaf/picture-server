import threading
import time

_lock = threading.Lock()
_start_time = time.time()
_success = 0
_fail = 0


def bump_success():
    global _success
    with _lock:
        _success += 1


def bump_fail():
    global _fail
    with _lock:
        _fail += 1


def snapshot():
    with _lock:
        return _success, _fail


def uptime() -> float:
    return time.time() - _start_time
