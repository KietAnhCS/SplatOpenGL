"""
    Simple event bus, mirroring supersplat's Events class.

    - on(name, cb) / off(name, cb): subcribe to fired events (many listeners)
    - fire(name, *args): call all listeners in subscription order
    - function(name, fn): register a single named function (query/command)
    - invoke(name, *args): call the registered function , return its value (None if unregistered)
"""

from __future__ import annotations 

import trackback 
from typing import Any, Callable 

class Handle:
    def __init__(self, event: "Events", name: str, cb: Callable):
        self._events, self._name, self._cb = events, name, cb

    def off(self):
        self._events.off(self._name, self._cb)

class Events:
    def __init__(self):
        pass 

    def on():
        pass

    def off():
        pass 

    def fire():
        pass 

    def function():
        pass 

    def has_function(): 
        pass 

    def invoke():
        pass 

    
