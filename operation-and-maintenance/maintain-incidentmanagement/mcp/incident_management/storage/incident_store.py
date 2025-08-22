"""
Incident storage implementation.

This module provides the main IncidentStore class which is currently
implemented using in-memory storage with optional file persistence.
"""

from .memory_store import MemoryIncidentStore

# Use MemoryIncidentStore as the default implementation
IncidentStore = MemoryIncidentStore

__all__ = ['IncidentStore']