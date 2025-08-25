"""
Storage module for incident management system.

This module provides persistent storage capabilities for incidents,
including in-memory storage with file persistence and storage interfaces.
"""

from .incident_store import IncidentStore
from .memory_store import MemoryIncidentStore
from .base_store import BaseStore

__all__ = ['IncidentStore', 'MemoryIncidentStore', 'BaseStore']