"""
Performance metrics and SLA tracking implementation.

This module provides incident resolution time tracking, team performance metrics,
capacity monitoring, and SLA violation alerts with escalation triggers.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import statistics

from ..models.incident import Incident, IncidentStatus, IncidentSeverity
from ..storage.incident_store import IncidentStore
from ..core.notification_manager import NotificationManager

logger = logging.getLogger(__name__)


class SLALevel(Enum):
    """SLA severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SLATarget:
    """SLA target configuration."""
    severity: IncidentSeverity
    response_time_minutes: int  # Time to first response
    resolution_time_minutes: int  # Time to resolution
    escalation_time_minutes: int  # Time before escalation


@dataclass
class PerformanceMetrics:
    """Team performance metrics."""
    team_name: str
    period_start: datetime
    period_end: datetime
    
    # Incident counts
    total_incidents: int
    resolved_incidents: int
    escalated_incidents: int
    
    # Response times
    avg_response_time_minutes: Optional[float]
    avg_resolution_time_minutes: Optional[float]
    median_resolution_time_minutes: Optional[float]
    
    # SLA compliance
    sla_compliance_rate: float  # Percentage
    sla_violations: int
    
    # Capacity metrics
    current_active_incidents: int
    max_concurrent_incidents: int
    team_utilization_rate: float  # Percentage
    
    # Quality metrics
    reopened_incidents: int
    false_positive_rate: float


@dataclass
class TeamCapacity:
    """Team capacity information."""
    team_name: str
    max_capacity: int
    current_load: int
    available_capacity: int
    utilization_rate: float
    members_count: int
    members_on_duty: int


@dataclass
class SLAViolation:
    """SLA violation record."""
    incident_id: str
    team_name: str
    violation_type: str  # "response" or "resolution"
    target_minutes: int
    actual_minutes: int
    severity: IncidentSeverity
    created_at: datetime
    escalated: bool = False


class PerformanceTracker:
    """Tracks incident resolution times and team performance metrics."""
    
    def __init__(self, incident_store: IncidentStore, notification_manager: NotificationManager):
        self.incident_store = incident_store
        self.notification_manager = notification_manager
        
        # Default SLA targets (can be configured)
        self.sla_targets = {
            IncidentSeverity.CRITICAL: SLATarget(
                severity=IncidentSeverity.CRITICAL,
                response_time_minutes=15,
                resolution_time_minutes=240,  # 4 hours
                escalation_time_minutes=60
            ),
            IncidentSeverity.HIGH: SLATarget(
                severity=IncidentSeverity.HIGH,
                response_time_minutes=30,
                resolution_time_minutes=480,  # 8 hours
                escalation_time_minutes=120
            ),
            IncidentSeverity.MEDIUM: SLATarget(
                severity=IncidentSeverity.MEDIUM,
                response_time_minutes=60,
                resolution_time_minutes=1440,  # 24 hours
                escalation_time_minutes=240
            ),
            IncidentSeverity.LOW: SLATarget(
                severity=IncidentSeverity.LOW,
                response_time_minutes=120,
                resolution_time_minutes=2880,  # 48 hours
                escalation_time_minutes=480
            )
        }
        
        # Team capacity configuration (can be loaded from config)
        self.team_capacities = {
            "backend-team": 10,
            "frontend-team": 8,
            "infrastructure-team": 12,
            "security-team": 6,
            "database-team": 8
        }
        
        self.sla_violations: List[SLAViolation] = []
        self._monitoring_task = None
    
    async def track_incident_resolution_time(self, incident: Incident) -> Dict[str, Any]:
        """Track resolution time for a specific incident."""
        if not incident.resolved_at:
            return {"error": "Incident not resolved yet"}
        
        resolution_time = incident.resolved_at - incident.created_at
        resolution_minutes = resolution_time.total_seconds() / 60
        
        # Get SLA target for this severity
        sla_target = self.sla_targets.get(incident.severity)
        if not sla_target:
            return {"error": f"No SLA target for severity {incident.severity}"}
        
        # Check SLA compliance
        sla_met = resolution_minutes <= sla_target.resolution_time_minutes
        
        # Calculate response time if available (when incident was first assigned)
        response_time_minutes = None
        if incident.assigned_team and hasattr(incident, 'first_assigned_at'):
            response_time = incident.first_assigned_at - incident.created_at
            response_time_minutes = response_time.total_seconds() / 60
        
        tracking_data = {
            "incident_id": incident.id,
            "severity": incident.severity.value,
            "team": incident.assigned_team,
            "resolution_time_minutes": resolution_minutes,
            "response_time_minutes": response_time_minutes,
            "sla_target_minutes": sla_target.resolution_time_minutes,
            "sla_met": sla_met,
            "sla_breach_minutes": max(0, resolution_minutes - sla_target.resolution_time_minutes),
            "created_at": incident.created_at.isoformat(),
            "resolved_at": incident.resolved_at.isoformat()
        }
        
        # Record SLA violation if applicable
        if not sla_met:
            violation = SLAViolation(
                incident_id=incident.id,
                team_name=incident.assigned_team or "unassigned",
                violation_type="resolution",
                target_minutes=sla_target.resolution_time_minutes,
                actual_minutes=int(resolution_minutes),
                severity=incident.severity,
                created_at=datetime.utcnow()
            )
            self.sla_violations.append(violation)
            
            # Send violation alert
            await self._send_sla_violation_alert(violation, incident)
        
        logger.info(f"Tracked resolution time for incident {incident.id}: {resolution_minutes:.1f} minutes")
        return tracking_data
    
    async def get_team_performance_metrics(
        self, 
        team_name: str, 
        period_days: int = 30
    ) -> PerformanceMetrics:
        """Get comprehensive performance metrics for a team."""
        period_start = datetime.utcnow() - timedelta(days=period_days)
        period_end = datetime.utcnow()
        
        # Get incidents for the team in the period
        team_incidents = await self.incident_store.get_incidents(
            filters={"assigned_team": team_name},
            limit=1000
        )
        
        # Filter by period
        period_incidents = [
            incident for incident in team_incidents
            if incident.created_at >= period_start
        ]
        
        resolved_incidents = [
            incident for incident in period_incidents
            if incident.status == IncidentStatus.RESOLVED and incident.resolved_at
        ]
        
        # Calculate response times (if available)
        response_times = []
        for incident in resolved_incidents:
            if hasattr(incident, 'first_assigned_at') and incident.first_assigned_at:
                response_time = (incident.first_assigned_at - incident.created_at).total_seconds() / 60
                response_times.append(response_time)
        
        # Calculate resolution times
        resolution_times = []
        for incident in resolved_incidents:
            resolution_time = (incident.resolved_at - incident.created_at).total_seconds() / 60
            resolution_times.append(resolution_time)
        
        # Calculate SLA compliance
        sla_compliant = 0
        total_sla_checked = 0
        
        for incident in resolved_incidents:
            sla_target = self.sla_targets.get(incident.severity)
            if sla_target:
                total_sla_checked += 1
                resolution_time = (incident.resolved_at - incident.created_at).total_seconds() / 60
                if resolution_time <= sla_target.resolution_time_minutes:
                    sla_compliant += 1
        
        sla_compliance_rate = (sla_compliant / total_sla_checked * 100) if total_sla_checked > 0 else 0
        
        # Get current capacity info
        capacity_info = await self.get_team_capacity(team_name)
        
        # Count escalated incidents
        escalated_incidents = len([
            incident for incident in period_incidents
            if hasattr(incident, 'escalated') and incident.escalated
        ])
        
        # Count reopened incidents (simplified - would need audit trail in real implementation)
        reopened_incidents = 0  # Would track from audit logs
        
        # Calculate false positive rate (simplified)
        false_positive_rate = 0.0  # Would calculate from incident classifications
        
        metrics = PerformanceMetrics(
            team_name=team_name,
            period_start=period_start,
            period_end=period_end,
            total_incidents=len(period_incidents),
            resolved_incidents=len(resolved_incidents),
            escalated_incidents=escalated_incidents,
            avg_response_time_minutes=statistics.mean(response_times) if response_times else None,
            avg_resolution_time_minutes=statistics.mean(resolution_times) if resolution_times else None,
            median_resolution_time_minutes=statistics.median(resolution_times) if resolution_times else None,
            sla_compliance_rate=sla_compliance_rate,
            sla_violations=total_sla_checked - sla_compliant,
            current_active_incidents=capacity_info.current_load,
            max_concurrent_incidents=max(capacity_info.current_load, capacity_info.max_capacity),
            team_utilization_rate=capacity_info.utilization_rate,
            reopened_incidents=reopened_incidents,
            false_positive_rate=false_positive_rate
        )
        
        logger.info(f"Generated performance metrics for team {team_name}")
        return metrics
    
    async def get_team_capacity(self, team_name: str) -> TeamCapacity:
        """Get current team capacity and utilization."""
        # Get current active incidents for the team
        active_incidents = await self.incident_store.get_incidents(
            filters={
                "assigned_team": team_name,
                "status": [IncidentStatus.DETECTED, IncidentStatus.ASSIGNED, IncidentStatus.IN_PROGRESS]
            },
            limit=100
        )
        
        current_load = len(active_incidents)
        max_capacity = self.team_capacities.get(team_name, 10)  # Default capacity
        available_capacity = max(0, max_capacity - current_load)
        utilization_rate = (current_load / max_capacity * 100) if max_capacity > 0 else 0
        
        # In a real implementation, this would come from team management system
        members_count = max_capacity // 2  # Simplified assumption
        members_on_duty = members_count  # Simplified - would check actual schedules
        
        return TeamCapacity(
            team_name=team_name,
            max_capacity=max_capacity,
            current_load=current_load,
            available_capacity=available_capacity,
            utilization_rate=utilization_rate,
            members_count=members_count,
            members_on_duty=members_on_duty
        )
    
    async def check_sla_violations(self) -> List[SLAViolation]:
        """Check for current SLA violations and potential escalations."""
        current_violations = []
        
        # Get all active incidents
        active_incidents = await self.incident_store.get_incidents(
            filters={"status": [IncidentStatus.DETECTED, IncidentStatus.ASSIGNED, IncidentStatus.IN_PROGRESS]},
            limit=500
        )
        
        current_time = datetime.utcnow()
        
        for incident in active_incidents:
            sla_target = self.sla_targets.get(incident.severity)
            if not sla_target:
                continue
            
            # Check resolution time SLA
            incident_age_minutes = (current_time - incident.created_at).total_seconds() / 60
            
            if incident_age_minutes > sla_target.resolution_time_minutes:
                violation = SLAViolation(
                    incident_id=incident.id,
                    team_name=incident.assigned_team or "unassigned",
                    violation_type="resolution",
                    target_minutes=sla_target.resolution_time_minutes,
                    actual_minutes=int(incident_age_minutes),
                    severity=incident.severity,
                    created_at=current_time
                )
                current_violations.append(violation)
            
            # Check if escalation is needed
            elif incident_age_minutes > sla_target.escalation_time_minutes:
                # Check if already escalated
                existing_violation = next(
                    (v for v in self.sla_violations 
                     if v.incident_id == incident.id and v.violation_type == "escalation"),
                    None
                )
                
                if not existing_violation:
                    escalation_violation = SLAViolation(
                        incident_id=incident.id,
                        team_name=incident.assigned_team or "unassigned",
                        violation_type="escalation",
                        target_minutes=sla_target.escalation_time_minutes,
                        actual_minutes=int(incident_age_minutes),
                        severity=incident.severity,
                        created_at=current_time
                    )
                    current_violations.append(escalation_violation)
                    
                    # Trigger escalation
                    await self._trigger_escalation(incident, escalation_violation)
        
        return current_violations
    
    async def get_sla_compliance_report(self, period_days: int = 30) -> Dict[str, Any]:
        """Generate SLA compliance report."""
        period_start = datetime.utcnow() - timedelta(days=period_days)
        
        # Get all resolved incidents in the period
        all_incidents = await self.incident_store.get_incidents(limit=1000)
        period_incidents = [
            incident for incident in all_incidents
            if (incident.created_at >= period_start and 
                incident.status == IncidentStatus.RESOLVED and 
                incident.resolved_at)
        ]
        
        # Calculate compliance by severity
        compliance_by_severity = {}
        for severity in IncidentSeverity:
            severity_incidents = [i for i in period_incidents if i.severity == severity]
            if not severity_incidents:
                continue
            
            sla_target = self.sla_targets.get(severity)
            if not sla_target:
                continue
            
            compliant_count = 0
            for incident in severity_incidents:
                resolution_time = (incident.resolved_at - incident.created_at).total_seconds() / 60
                if resolution_time <= sla_target.resolution_time_minutes:
                    compliant_count += 1
            
            compliance_rate = (compliant_count / len(severity_incidents)) * 100
            compliance_by_severity[severity.value] = {
                "total_incidents": len(severity_incidents),
                "compliant_incidents": compliant_count,
                "compliance_rate": compliance_rate,
                "target_minutes": sla_target.resolution_time_minutes
            }
        
        # Calculate overall compliance
        total_incidents = len(period_incidents)
        total_compliant = sum(data["compliant_incidents"] for data in compliance_by_severity.values())
        overall_compliance = (total_compliant / total_incidents * 100) if total_incidents > 0 else 0
        
        # Get violations in period
        period_violations = [
            v for v in self.sla_violations
            if v.created_at >= period_start
        ]
        
        return {
            "period_start": period_start.isoformat(),
            "period_end": datetime.utcnow().isoformat(),
            "overall_compliance_rate": overall_compliance,
            "total_incidents": total_incidents,
            "total_violations": len(period_violations),
            "compliance_by_severity": compliance_by_severity,
            "violations_by_team": self._group_violations_by_team(period_violations),
            "escalations_triggered": len([v for v in period_violations if v.violation_type == "escalation"])
        }
    
    async def start_monitoring(self):
        """Start continuous SLA monitoring."""
        if self._monitoring_task:
            return
        
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Started SLA monitoring")
    
    async def stop_monitoring(self):
        """Stop SLA monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
            logger.info("Stopped SLA monitoring")
    
    async def _monitoring_loop(self):
        """Background monitoring loop for SLA violations."""
        try:
            while True:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                try:
                    violations = await self.check_sla_violations()
                    if violations:
                        logger.warning(f"Found {len(violations)} SLA violations")
                        
                        for violation in violations:
                            if violation not in self.sla_violations:
                                self.sla_violations.append(violation)
                                
                except Exception as e:
                    logger.error(f"Error in SLA monitoring loop: {e}")
                    
        except asyncio.CancelledError:
            logger.info("SLA monitoring loop cancelled")
    
    async def _send_sla_violation_alert(self, violation: SLAViolation, incident: Incident):
        """Send alert for SLA violation."""
        message = (
            f"🚨 SLA VIOLATION ALERT\n\n"
            f"Incident: {incident.id}\n"
            f"Title: {incident.title}\n"
            f"Severity: {violation.severity.value}\n"
            f"Team: {violation.team_name}\n"
            f"Violation Type: {violation.violation_type}\n"
            f"Target: {violation.target_minutes} minutes\n"
            f"Actual: {violation.actual_minutes} minutes\n"
            f"Breach: {violation.actual_minutes - violation.target_minutes} minutes\n"
        )
        
        # Send to team and management
        channels = [f"#{violation.team_name}", "#incident-management", "#sla-alerts"]
        
        for channel in channels:
            try:
                await self.notification_manager.send_notification(
                    channel=channel,
                    message=message,
                    priority="high"
                )
            except Exception as e:
                logger.error(f"Failed to send SLA violation alert to {channel}: {e}")
    
    async def _trigger_escalation(self, incident: Incident, violation: SLAViolation):
        """Trigger incident escalation."""
        escalation_message = (
            f"⚠️ INCIDENT ESCALATION REQUIRED\n\n"
            f"Incident: {incident.id}\n"
            f"Title: {incident.title}\n"
            f"Severity: {incident.severity.value}\n"
            f"Current Team: {incident.assigned_team}\n"
            f"Age: {violation.actual_minutes} minutes\n"
            f"Escalation Threshold: {violation.target_minutes} minutes\n\n"
            f"Please review and escalate to next level support."
        )
        
        # Send escalation alert
        escalation_channels = ["#incident-escalation", "#management", f"#{incident.assigned_team}-leads"]
        
        for channel in escalation_channels:
            try:
                await self.notification_manager.send_notification(
                    channel=channel,
                    message=escalation_message,
                    priority="critical"
                )
            except Exception as e:
                logger.error(f"Failed to send escalation alert to {channel}: {e}")
        
        violation.escalated = True
        logger.warning(f"Triggered escalation for incident {incident.id}")
    
    def _group_violations_by_team(self, violations: List[SLAViolation]) -> Dict[str, Dict]:
        """Group violations by team for reporting."""
        team_violations = {}
        
        for violation in violations:
            team = violation.team_name
            if team not in team_violations:
                team_violations[team] = {
                    "total_violations": 0,
                    "resolution_violations": 0,
                    "escalation_violations": 0,
                    "by_severity": {}
                }
            
            team_violations[team]["total_violations"] += 1
            
            if violation.violation_type == "resolution":
                team_violations[team]["resolution_violations"] += 1
            elif violation.violation_type == "escalation":
                team_violations[team]["escalation_violations"] += 1
            
            severity = violation.severity.value
            if severity not in team_violations[team]["by_severity"]:
                team_violations[team]["by_severity"][severity] = 0
            team_violations[team]["by_severity"][severity] += 1
        
        return team_violations
    
    def configure_sla_targets(self, targets: Dict[IncidentSeverity, SLATarget]):
        """Configure custom SLA targets."""
        self.sla_targets.update(targets)
        logger.info("Updated SLA targets configuration")
    
    def configure_team_capacities(self, capacities: Dict[str, int]):
        """Configure team capacity limits."""
        self.team_capacities.update(capacities)
        logger.info("Updated team capacity configuration")


async def create_performance_tracker(
    incident_store: IncidentStore, 
    notification_manager: NotificationManager
) -> PerformanceTracker:
    """Create and start performance tracker."""
    tracker = PerformanceTracker(incident_store, notification_manager)
    await tracker.start_monitoring()
    return tracker