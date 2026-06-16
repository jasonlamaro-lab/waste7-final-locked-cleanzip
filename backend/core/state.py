import threading

_STATE_LOCK = threading.Lock()

STATE = {
    "markets": {},
    "engines": {},
    "last_cycle": None,
    "status": "RUNNING",
    "paused": False,
}


def state_get(key, default=None):
    with _STATE_LOCK:
        return STATE.get(key, default)


def state_set(key, value):
    with _STATE_LOCK:
        STATE[key] = value


def state_update(key, subkey, value):
    with _STATE_LOCK:
        if key not in STATE or not isinstance(STATE[key], dict):
            STATE[key] = {}
        STATE[key][subkey] = value
