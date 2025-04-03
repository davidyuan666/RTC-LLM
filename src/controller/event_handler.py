#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/8/17
# @Author  : david
# @Software: MUST
# @File    : event_handler.py
import asyncio
from threading import Lock

class SingletonMeta(type):
    _instances = {}
    _lock = Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
            return cls._instances[cls]

class EventManager(metaclass=SingletonMeta):
    def __init__(self):
        self.listeners = {}

    def subscribe(self, event_name, listener):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(listener)

    def publish(self, event_name, data=None):
        """
        Asynchronously publish an event to all subscribed listeners.
        """
        listeners = self.listeners.get(event_name, [])
        for listener in listeners:
            if data is not None:
                listener(data)
            else:
                listener()




