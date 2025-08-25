"""
Data validation utilities for incident management.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from models.incident import IncidentSeverity, IncidentStatus
from models.remediation import TaskType, TaskStatus


def validate_incident_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate incident data and return validation result.
    
    Returns:
        Dict with 'valid' boolean and 'errors' list
    """
    errors = []
    
    # Required fields
    required_fields = ['title', 'description', 'severity', 'source_query']
    for field in required_fields:
        if field not in data or not data[field]:
            errors.append(f"Missing required field: {field}")
    
    # Validate severity
    if 'severity' in data:
        if isinstance(data['severity'], str):
            try:
                IncidentSeverity(data['severity'])
            except ValueError:
                errors.append(f"Invalid severity: {data['severity']}")
        elif not isinstance(data['severity'], IncidentSeverity):
            errors.append("Severity must be string or IncidentSeverity enum")
    
    # Validate status if provided
    if 'status' in data:
        if isinstance(data['status'], str):
            try:
                IncidentStatus(data['status'])
            except ValueError:
                errors.append(f"Invalid status: {data['status']}")
        elif not isinstance(data['status'], IncidentStatus):
            errors.append("Status must be string or IncidentStatus enum")
    
    # Validate affected_systems if provided
    if 'affected_systems' in data:
        if not isinstance(data['affected_systems'], list):
            errors.append("affected_systems must be a list")
        elif not all(isinstance(system, str) for system in data['affected_systems']):
            errors.append("All affected_systems must be strings")
    
    # Validate tags if provided
    if 'tags' in data:
        if not isinstance(data['tags'], list):
            errors.append("tags must be a list")
        elif not all(isinstance(tag, str) for tag in data['tags']):
            errors.append("All tags must be strings")
    
    # Validate title length
    if 'title' in data and len(data['title']) > 200:
        errors.append("Title must be 200 characters or less")
    
    # Validate description length
    if 'description' in data and len(data['description']) > 2000:
        errors.append("Description must be 2000 characters or less")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }


def validate_task_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate remediation task data.
    
    Returns:
        Dict with 'valid' boolean and 'errors' list
    """
    errors = []
    
    # Required fields
    required_fields = ['name', 'description', 'task_type', 'parameters']
    for field in required_fields:
        if field not in data or data[field] is None:
            errors.append(f"Missing required field: {field}")
    
    # Validate task_type
    if 'task_type' in data:
        if isinstance(data['task_type'], str):
            try:
                TaskType(data['task_type'])
            except ValueError:
                errors.append(f"Invalid task_type: {data['task_type']}")
        elif not isinstance(data['task_type'], TaskType):
            errors.append("task_type must be string or TaskType enum")
    
    # Validate status if provided
    if 'status' in data:
        if isinstance(data['status'], str):
            try:
                TaskStatus(data['status'])
            except ValueError:
                errors.append(f"Invalid status: {data['status']}")
        elif not isinstance(data['status'], TaskStatus):
            errors.append("status must be string or TaskStatus enum")
    
    # Validate parameters
    if 'parameters' in data:
        if not isinstance(data['parameters'], dict):
            errors.append("parameters must be a dictionary")
    
    # Validate safety_checks if provided
    if 'safety_checks' in data:
        if not isinstance(data['safety_checks'], list):
            errors.append("safety_checks must be a list")
    
    # Validate approval_required if provided
    if 'approval_required' in data:
        if not isinstance(data['approval_required'], bool):
            errors.append("approval_required must be a boolean")
    
    # Validate estimated_duration if provided
    if 'estimated_duration' in data:
        if not isinstance(data['estimated_duration'], (int, float)):
            errors.append("estimated_duration must be a number (seconds)")
        elif data['estimated_duration'] < 0:
            errors.append("estimated_duration must be positive")
    
    # Validate name length
    if 'name' in data and len(data['name']) > 100:
        errors.append("Name must be 100 characters or less")
    
    # Validate description length
    if 'description' in data and len(data['description']) > 1000:
        errors.append("Description must be 1000 characters or less")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }


def validate_analysis_result_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate analysis result data.
    
    Returns:
        Dict with 'valid' boolean and 'errors' list
    """
    errors = []
    
    # Required fields
    required_fields = ['incident_id', 'confidence_score', 'risk_assessment']
    for field in required_fields:
        if field not in data or data[field] is None:
            errors.append(f"Missing required field: {field}")
    
    # Validate confidence_score
    if 'confidence_score' in data:
        score = data['confidence_score']
        if not isinstance(score, (int, float)):
            errors.append("confidence_score must be a number")
        elif not 0.0 <= score <= 1.0:
            errors.append("confidence_score must be between 0.0 and 1.0")
    
    # Validate lists
    list_fields = ['root_causes', 'affected_components', 'suggested_actions', 'similar_incidents']
    for field in list_fields:
        if field in data:
            if not isinstance(data[field], list):
                errors.append(f"{field} must be a list")
            elif not all(isinstance(item, str) for item in data[field]):
                errors.append(f"All items in {field} must be strings")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }


def validate_audit_event_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate audit event data.
    
    Returns:
        Dict with 'valid' boolean and 'errors' list
    """
    errors = []
    
    # Required fields
    required_fields = ['event_type', 'action', 'details']
    for field in required_fields:
        if field not in data or data[field] is None:
            errors.append(f"Missing required field: {field}")
    
    # Validate details is a dict
    if 'details' in data and not isinstance(data['details'], dict):
        errors.append("details must be a dictionary")
    
    # Validate timestamp if provided
    if 'timestamp' in data:
        if isinstance(data['timestamp'], str):
            try:
                datetime.fromisoformat(data['timestamp'])
            except ValueError:
                errors.append("timestamp must be a valid ISO format datetime string")
        elif not isinstance(data['timestamp'], datetime):
            errors.append("timestamp must be datetime object or ISO string")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }


def validate_user_permissions(user_id: str, required_permissions: List[str]) -> bool:
    """
    Validate if a user has the required permissions.
    
    Args:
        user_id: The user ID to check
        required_permissions: List of required permissions
        
    Returns:
        True if user has all required permissions, False otherwise
    """
    # For now, return True for all users (basic implementation)
    # In a real implementation, this would check against a user permission system
    return True


def validate_incident_id(incident_id: str) -> bool:
    """
    Validate incident ID format.
    
    Args:
        incident_id: The incident ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not incident_id or not isinstance(incident_id, str):
        return False
    
    # Basic validation - should be non-empty string
    return len(incident_id.strip()) > 0