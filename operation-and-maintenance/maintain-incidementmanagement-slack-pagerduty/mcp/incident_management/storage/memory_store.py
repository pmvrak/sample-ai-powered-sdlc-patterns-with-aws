"""
In-memory incident storage implementation with optional file persistence.
"""

import json
import logging
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from .base_store import BaseStore
from ..models.incident import Incident, IncidentStatus, IncidentSeverity


logger = logging.getLogger(__name__)


class MemoryIncidentStore(BaseStore):
    """
    In-memory implementation of incident storage with optional file persistence.
    
    This is a simple storage implementation suitable for demos and development.
    Data is stored in memory and optionally persisted to JSON files.
    """
    
    def __init__(
        self,
        persist_to_file: bool = True,
        storage_dir: str = "/tmp",
        cache_file: str = "incident_cache.json",
        processed_file: str = "processed_incidents.json"
    ):
        """
        Initialize the memory incident store.
        
        Args:
            persist_to_file: Whether to persist data to files
            storage_dir: Directory for storage files
            cache_file: Name of the cache file
            processed_file: Name of the processed incidents file
        """
        self.persist_to_file = persist_to_file
        self.storage_dir = Path(storage_dir)
        self.cache_file = self.storage_dir / cache_file
        self.processed_file = self.storage_dir / processed_file
        
        # In-memory storage
        self.incidents: Dict[str, Incident] = {}
        self.detected_incidents: List[str] = []  # List of incident IDs
        self.incident_cache: Dict[str, Dict[str, Any]] = {}
        
        # Ensure storage directory exists
        if self.persist_to_file:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_files()
        
        logger.info(f"Initialized MemoryIncidentStore with file persistence: {persist_to_file}")
    
    async def create_incident(self, incident: Incident) -> bool:
        """
        Create a new incident in memory.
        
        Args:
            incident: The incident to create
            
        Returns:
            bool: True if creation was successful, False otherwise
        """
        try:
            if incident.id in self.incidents:
                logger.warning(f"Incident {incident.id} already exists")
                return False
            
            self.incidents[incident.id] = incident
            self.detected_incidents.append(incident.id)
            
            # Update cache
            self.incident_cache[incident.id] = {
                "id": incident.id,
                "title": incident.title,
                "status": incident.status.value,
                "severity": incident.severity.value,
                "created_at": incident.created_at.isoformat(),
                "updated_at": incident.updated_at.isoformat()
            }
            
            if self.persist_to_file:
                self._save_to_files()
            
            logger.info(f"Created incident: {incident.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create incident {incident.id}: {e}")
            return False
    
    async def get_incident(self, incident_id: str) -> Optional[Incident]:
        """
        Retrieve an incident by ID.
        
        Args:
            incident_id: The unique incident identifier
            
        Returns:
            Optional[Incident]: The incident if found, None otherwise
        """
        try:
            incident = self.incidents.get(incident_id)
            if incident:
                logger.debug(f"Retrieved incident: {incident_id}")
                return incident
            else:
                logger.debug(f"Incident not found: {incident_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get incident {incident_id}: {e}")
            return None
    
    async def update_incident(self, incident: Incident) -> bool:
        """
        Update an existing incident in memory.
        
        Args:
            incident: The incident with updated information
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            if incident.id not in self.incidents:
                logger.warning(f"Incident {incident.id} does not exist for update")
                return False
            
            # Update the updated_at timestamp
            incident.updated_at = datetime.utcnow()
            
            self.incidents[incident.id] = incident
            
            # Update cache
            self.incident_cache[incident.id] = {
                "id": incident.id,
                "title": incident.title,
                "status": incident.status.value,
                "severity": incident.severity.value,
                "created_at": incident.created_at.isoformat(),
                "updated_at": incident.updated_at.isoformat()
            }
            
            if self.persist_to_file:
                self._save_to_files()
            
            logger.info(f"Updated incident: {incident.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update incident {incident.id}: {e}")
            return False
    
    async def delete_incident(self, incident_id: str) -> bool:
        """
        Delete an incident from memory.
        
        Args:
            incident_id: The unique incident identifier
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            if incident_id not in self.incidents:
                logger.warning(f"Incident {incident_id} does not exist for deletion")
                return False
            
            del self.incidents[incident_id]
            
            if incident_id in self.detected_incidents:
                self.detected_incidents.remove(incident_id)
            
            if incident_id in self.incident_cache:
                del self.incident_cache[incident_id]
            
            if self.persist_to_file:
                self._save_to_files()
            
            logger.info(f"Deleted incident: {incident_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete incident {incident_id}: {e}")
            return False
    
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
        try:
            incidents = list(self.incidents.values())
            
            # Apply filters
            if status:
                incidents = [i for i in incidents if i.status == status]
            
            if team:
                incidents = [i for i in incidents if i.assigned_team == team]
            
            if severity:
                incidents = [i for i in incidents if i.severity == severity]
            
            # Sort by creation time (newest first)
            incidents.sort(key=lambda x: x.created_at, reverse=True)
            
            # Apply pagination
            start_idx = offset
            end_idx = offset + limit
            result = incidents[start_idx:end_idx]
            
            logger.debug(f"Listed {len(result)} incidents with filters")
            return result
            
        except Exception as e:
            logger.error(f"Failed to list incidents: {e}")
            return []
    
    async def get_incidents_by_status(self, status: IncidentStatus) -> List[Incident]:
        """
        Get all incidents with a specific status.
        
        Args:
            status: The incident status to filter by
            
        Returns:
            List[Incident]: List of incidents with the specified status
        """
        try:
            incidents = [
                incident for incident in self.incidents.values()
                if incident.status == status
            ]
            
            # Sort by creation time (newest first)
            incidents.sort(key=lambda x: x.created_at, reverse=True)
            
            logger.debug(f"Found {len(incidents)} incidents with status {status.value}")
            return incidents
            
        except Exception as e:
            logger.error(f"Failed to get incidents by status {status.value}: {e}")
            return []
    
    async def get_incidents_by_team(self, team: str) -> List[Incident]:
        """
        Get all incidents assigned to a specific team.
        
        Args:
            team: The team name to filter by
            
        Returns:
            List[Incident]: List of incidents assigned to the team
        """
        try:
            incidents = [
                incident for incident in self.incidents.values()
                if incident.assigned_team == team
            ]
            
            # Sort by creation time (newest first)
            incidents.sort(key=lambda x: x.created_at, reverse=True)
            
            logger.debug(f"Found {len(incidents)} incidents for team {team}")
            return incidents
            
        except Exception as e:
            logger.error(f"Failed to get incidents by team {team}: {e}")
            return []
    
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
        try:
            incidents = [
                incident for incident in self.incidents.values()
                if start_time <= incident.created_at <= end_time
            ]
            
            # Sort by creation time (newest first)
            incidents.sort(key=lambda x: x.created_at, reverse=True)
            
            logger.debug(f"Found {len(incidents)} incidents in time range")
            return incidents
            
        except Exception as e:
            logger.error(f"Failed to get incidents by time range: {e}")
            return []
    
    async def get_active_incidents(self) -> List[Incident]:
        """
        Get all active (non-resolved, non-closed) incidents.
        
        Returns:
            List[Incident]: List of active incidents
        """
        try:
            active_statuses = {
                IncidentStatus.DETECTED,
                IncidentStatus.ASSIGNED,
                IncidentStatus.IN_PROGRESS
            }
            
            incidents = [
                incident for incident in self.incidents.values()
                if incident.status in active_statuses
            ]
            
            # Sort by severity (critical first) then by creation time
            incidents.sort(key=lambda x: (
                self._severity_priority(x.severity),
                x.created_at
            ))
            
            logger.debug(f"Found {len(incidents)} active incidents")
            return incidents
            
        except Exception as e:
            logger.error(f"Failed to get active incidents: {e}")
            return []
    
    async def search_incidents(self, query: str) -> List[Incident]:
        """
        Search incidents by text query in title and description.
        
        Args:
            query: Search query string
            
        Returns:
            List[Incident]: List of matching incidents
        """
        try:
            query_lower = query.lower()
            
            incidents = [
                incident for incident in self.incidents.values()
                if (query_lower in incident.title.lower() or 
                    query_lower in incident.description.lower())
            ]
            
            # Sort by relevance (exact matches first, then by creation time)
            incidents.sort(key=lambda x: (
                query_lower not in x.title.lower(),  # Exact title matches first
                -x.created_at.timestamp()  # Then by creation time (newest first)
            ))
            
            logger.debug(f"Found {len(incidents)} incidents matching query: {query}")
            return incidents
            
        except Exception as e:
            logger.error(f"Failed to search incidents with query '{query}': {e}")
            return []
    
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
        try:
            incidents = list(self.incidents.values())
            
            # Apply filters
            if status:
                incidents = [i for i in incidents if i.status == status]
            
            if team:
                incidents = [i for i in incidents if i.assigned_team == team]
            
            if severity:
                incidents = [i for i in incidents if i.severity == severity]
            
            count = len(incidents)
            logger.debug(f"Counted {count} incidents with filters")
            return count
            
        except Exception as e:
            logger.error(f"Failed to count incidents: {e}")
            return 0
    
    def _severity_priority(self, severity: IncidentSeverity) -> int:
        """
        Get numeric priority for severity (lower number = higher priority).
        
        Args:
            severity: The incident severity
            
        Returns:
            int: Priority value
        """
        priority_map = {
            IncidentSeverity.CRITICAL: 0,
            IncidentSeverity.HIGH: 1,
            IncidentSeverity.MEDIUM: 2,
            IncidentSeverity.LOW: 3
        }
        return priority_map.get(severity, 4)
    
    def _load_from_files(self):
        """Load incidents from persistent files."""
        try:
            # Load incident cache
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    self.incident_cache = json.load(f)
                logger.debug(f"Loaded {len(self.incident_cache)} incidents from cache file")
            
            # Load detected incidents list
            if self.processed_file.exists():
                with open(self.processed_file, 'r') as f:
                    data = json.load(f)
                    self.detected_incidents = data.get('detected_incidents', [])
                logger.debug(f"Loaded {len(self.detected_incidents)} detected incidents from file")
            
            # Reconstruct incidents from cache (simplified - in real usage, 
            # you'd want to store full incident data)
            for incident_id, cache_data in self.incident_cache.items():
                try:
                    incident = Incident(
                        id=cache_data['id'],
                        title=cache_data['title'],
                        description=f"Incident loaded from cache: {cache_data['title']}",
                        severity=IncidentSeverity(cache_data['severity']),
                        status=IncidentStatus(cache_data['status']),
                        source_query="cached",
                        affected_systems=[],
                        created_at=datetime.fromisoformat(cache_data['created_at']),
                        updated_at=datetime.fromisoformat(cache_data['updated_at'])
                    )
                    self.incidents[incident_id] = incident
                except Exception as e:
                    logger.warning(f"Failed to reconstruct incident {incident_id}: {e}")
            
        except Exception as e:
            logger.warning(f"Failed to load from files: {e}")
    
    def _save_to_files(self):
        """Save incidents to persistent files."""
        try:
            # Save incident cache
            with open(self.cache_file, 'w') as f:
                json.dump(self.incident_cache, f, indent=2)
            
            # Save processed incidents
            processed_data = {
                'detected_incidents': self.detected_incidents,
                'last_updated': datetime.utcnow().isoformat()
            }
            with open(self.processed_file, 'w') as f:
                json.dump(processed_data, f, indent=2)
            
            logger.debug("Saved incidents to persistent files")
            
        except Exception as e:
            logger.warning(f"Failed to save to files: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dict[str, Any]: Storage statistics
        """
        return {
            "total_incidents": len(self.incidents),
            "detected_incidents": len(self.detected_incidents),
            "cached_incidents": len(self.incident_cache),
            "persist_to_file": self.persist_to_file,
            "storage_dir": str(self.storage_dir),
            "cache_file_exists": self.cache_file.exists() if self.persist_to_file else False,
            "processed_file_exists": self.processed_file.exists() if self.persist_to_file else False
        }