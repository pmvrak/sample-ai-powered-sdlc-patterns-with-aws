"""
Formatting utilities for incident management messages and displays.
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta

from models.incident import Incident, IncidentSeverity, IncidentStatus
from models.remediation import RemediationTask, TaskStatus
from models.analysis import AnalysisResult


def format_incident_message(incident: Incident, message_type: str = "notification") -> str:
    """
    Format incident information for display in notifications or messages.
    
    Args:
        incident: The incident to format
        message_type: Type of message ('notification', 'summary', 'detailed')
    
    Returns:
        Formatted message string
    """
    severity_emoji = {
        IncidentSeverity.CRITICAL: "🔴",
        IncidentSeverity.HIGH: "🟠", 
        IncidentSeverity.MEDIUM: "🟡",
        IncidentSeverity.LOW: "🟢"
    }
    
    status_emoji = {
        IncidentStatus.DETECTED: "🔍",
        IncidentStatus.ASSIGNED: "👤",
        IncidentStatus.IN_PROGRESS: "⚙️",
        IncidentStatus.RESOLVED: "✅",
        IncidentStatus.CLOSED: "🔒"
    }
    
    emoji = severity_emoji.get(incident.severity, "⚪")
    status_icon = status_emoji.get(incident.status, "❓")
    
    if message_type == "notification":
        return f"{emoji} **{incident.title}**\n" \
               f"{status_icon} Status: {incident.status.value.title()}\n" \
               f"📊 Severity: {incident.severity.value.title()}\n" \
               f"🆔 ID: `{incident.id}`\n" \
               f"⏰ Created: {format_timestamp(incident.created_at)}"
    
    elif message_type == "summary":
        assigned_info = ""
        if incident.assigned_team:
            assigned_info = f"\n👥 Team: {incident.assigned_team}"
            if incident.assigned_user:
                assigned_info += f" ({incident.assigned_user})"
        
        return f"{emoji} **{incident.title}**\n" \
               f"{status_icon} {incident.status.value.title()} | " \
               f"📊 {incident.severity.value.title()}{assigned_info}\n" \
               f"🆔 `{incident.id}` | ⏰ {format_timestamp(incident.created_at)}"
    
    elif message_type == "detailed":
        assigned_info = "Not assigned"
        if incident.assigned_team:
            assigned_info = incident.assigned_team
            if incident.assigned_user:
                assigned_info += f" ({incident.assigned_user})"
        
        affected_systems = ", ".join(incident.affected_systems) if incident.affected_systems else "None specified"
        tags = ", ".join(incident.tags) if incident.tags else "None"
        
        duration = ""
        if incident.resolved_at:
            duration = f"\n⏱️ Duration: {format_duration(incident.resolved_at - incident.created_at)}"
        
        return f"{emoji} **{incident.title}**\n" \
               f"📝 {incident.description}\n\n" \
               f"{status_icon} **Status:** {incident.status.value.title()}\n" \
               f"📊 **Severity:** {incident.severity.value.title()}\n" \
               f"👥 **Assigned:** {assigned_info}\n" \
               f"🖥️ **Affected Systems:** {affected_systems}\n" \
               f"🏷️ **Tags:** {tags}\n" \
               f"🆔 **ID:** `{incident.id}`\n" \
               f"⏰ **Created:** {format_timestamp(incident.created_at)}" \
               f"{duration}"
    
    return f"{emoji} {incident.title} ({incident.severity.value})"


def format_task_summary(task: RemediationTask) -> str:
    """
    Format remediation task information for display.
    
    Args:
        task: The task to format
    
    Returns:
        Formatted task summary string
    """
    status_emoji = {
        TaskStatus.PENDING: "⏳",
        TaskStatus.APPROVED: "✅",
        TaskStatus.RUNNING: "⚙️",
        TaskStatus.COMPLETED: "✅",
        TaskStatus.FAILED: "❌",
        TaskStatus.CANCELLED: "🚫",
        TaskStatus.REQUIRES_APPROVAL: "⏸️"
    }
    
    emoji = status_emoji.get(task.status, "❓")
    
    approval_info = ""
    if task.approval_required:
        approval_info = " 🔐"
    
    duration_info = f"⏱️ Est: {format_duration(task.estimated_duration)}"
    
    return f"{emoji} **{task.name}**{approval_info}\n" \
           f"📝 {task.description}\n" \
           f"🔧 Type: {task.task_type.value.replace('_', ' ').title()}\n" \
           f"{duration_info} | 🆔 `{task.id}`"


def format_analysis_summary(analysis: AnalysisResult) -> str:
    """
    Format analysis result for display.
    
    Args:
        analysis: The analysis result to format
    
    Returns:
        Formatted analysis summary string
    """
    confidence_bar = "█" * int(analysis.confidence_score * 10)
    confidence_empty = "░" * (10 - int(analysis.confidence_score * 10))
    
    root_causes = "\n".join([f"• {cause}" for cause in analysis.root_causes[:3]])
    if len(analysis.root_causes) > 3:
        root_causes += f"\n• ... and {len(analysis.root_causes) - 3} more"
    
    actions = "\n".join([f"• {action}" for action in analysis.suggested_actions[:3]])
    if len(analysis.suggested_actions) > 3:
        actions += f"\n... and {len(analysis.suggested_actions) - 3} more"
    
    return f"🤖 **AI Analysis Results**\n\n" \
           f"📊 **Confidence:** {analysis.confidence_score:.1%} {confidence_bar}{confidence_empty}\n" \
           f"⚠️ **Risk Level:** {analysis.risk_assessment.value.title()}\n" \
           f"⏱️ **Est. Resolution:** {format_duration(analysis.estimated_resolution_time)}\n\n" \
           f"🔍 **Root Causes:**\n{root_causes}\n\n" \
           f"💡 **Suggested Actions:**\n{actions}"


def format_timestamp(timestamp: datetime) -> str:
    """
    Format timestamp for display.
    
    Args:
        timestamp: Datetime to format
    
    Returns:
        Formatted timestamp string
    """
    now = datetime.utcnow()
    diff = now - timestamp
    
    if diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours}h ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes}m ago"
    else:
        return "Just now"


def format_duration(duration: timedelta) -> str:
    """
    Format duration for display.
    
    Args:
        duration: Timedelta to format
    
    Returns:
        Formatted duration string
    """
    total_seconds = int(duration.total_seconds())
    
    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m {seconds}s" if seconds > 0 else f"{minutes}m"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
    else:
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        return f"{days}d {hours}h" if hours > 0 else f"{days}d"


def format_incident_list(incidents: List[Incident], max_items: int = 10) -> str:
    """
    Format a list of incidents for display.
    
    Args:
        incidents: List of incidents to format
        max_items: Maximum number of items to display
    
    Returns:
        Formatted incident list string
    """
    if not incidents:
        return "No incidents found."
    
    lines = []
    for i, incident in enumerate(incidents[:max_items]):
        summary = format_incident_message(incident, "summary")
        lines.append(f"{i+1}. {summary}")
    
    result = "\n\n".join(lines)
    
    if len(incidents) > max_items:
        result += f"\n\n... and {len(incidents) - max_items} more incidents"
    
    return result


def format_team_capacity(team: str, capacity_info: Dict[str, Any]) -> str:
    """
    Format team capacity information for display.
    
    Args:
        team: Team name
        capacity_info: Capacity information dictionary
    
    Returns:
        Formatted capacity string
    """
    current = capacity_info.get("current_incidents", 0)
    max_capacity = capacity_info.get("max_capacity", 10)
    available = capacity_info.get("available_members", 0)
    overloaded = capacity_info.get("overloaded", False)
    
    status_emoji = "🔴" if overloaded else "🟢"
    capacity_bar = "█" * min(10, int((current / max_capacity) * 10))
    capacity_empty = "░" * (10 - min(10, int((current / max_capacity) * 10)))
    
    return f"{status_emoji} **{team}**\n" \
           f"📊 Load: {current}/{max_capacity} {capacity_bar}{capacity_empty}\n" \
           f"👥 Available: {available} members"