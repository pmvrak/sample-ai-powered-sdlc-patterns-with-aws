"""
Base storage interface for incident management system.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..models.incident import Incident, IncidentStatus, IncidentSeverity


class BaseStore(ABC):
    """
    Abstract base class for incident storage implementations.
    
    Defines the interface that all storage backends must implement
    for incident persistence and retrieval operations.
    """
    
    @abstractmethod
    async def create_incident(self, incident: Incident) -> bool:
        """
        Create a new incident in storage.
        
        Args:
            incident: The incident to create
            
        Returns:
            bool: True if creation was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_incident(self, incident_id: str) -> Optional[Incident]:
        """
        Retrieve an incident by ID.
        
        Args:
            incident_id: The unique incident identifier
            
        Returns:
            Optional[Incident]: The incident if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def update_incident(self, incident: Incident) -> bool:
        """
        Update an existing incident in storage.
        
        Args:
            incident: The incident with updated information
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def delete_incident(self, incident_id: str) -> bool:
        """
        Delete an incident from storage.
        
        Args:
            incident_id: The unique incident identifier
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def list_incidents(
        self,
        status: Optional[IncidentStatus] = None,
        team: Optional[str] = None,
        severity: Optional[IncidentSeverity] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Incident]:
        """
        List incidents with optional filtering.
        
        Args:
            status: Filter by incident status
            team: Filter by assigned team
            severity: Filter by incident severity
            limit: Maximum number of incidents to return
            offset: Number of incidents to skip
            
        Returns:
            List[Incident]: List of matching incidents
        """
        pass
    
    @abstractmethod
    async def get_incidents_by_status(self, status: IncidentStatus) -> List[Incident]:
        """
        Get all incidents with a specific status.
        
        Args:
            status: The incident status to filter by
            
        Returns:
            List[Incident]: List of incidents with the specified status
        """
        pass
    
    @abstractmethod
    async def get_incidents_by_team(self, team: str) -> List[Incident]:
        """
        Get all incidents assigned to a specific team.
        
        Args:
            team: The team name to filter by
            
        Returns:
            List[Incident]: List of incidents assigned to the team
        """
        pass
    
    @abstractmethod
    async def get_incidents_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[Incident]:
        """
        Get incidents created within a specific time range.
        
        Args:
            start_time: Start of the time range
            end_time: End of the time range
            
        Returns:
            List[Incident]: List of incidents in the time range
        """
        pass
    
    @abstractmethod
    async def get_active_incidents(self) -> List[Incident]:
        """
        Get all active (non-resolved, non-closed) incidents.
        
        Returns:
            List[Incident]: List of active incidents
        """
        pass
    
    @abstractmethod
    async def search_incidents(self, query: str) -> List[Incident]:
        """
        Search incidents by text query.
        
        Args:
            query: Search query string
            
        Returns:
            List[Incident]: List of matching incidents
        """
        pass
    
    @abstractmethod
    async def get_incident_count(
        self,
        status: Optional[IncidentStatus] = None,
        team: Optional[str] = None,
        severity: Optional[IncidentSeverity] = None
    ) -> int:
        """
        Get count of incidents matching criteria.
        
        Args:
            status: Filter by incident status
            team: Filter by assigned team
            severity: Filter by incident severity
            
        Returns:
            int: Number of matching incidents
        """
        pass