"""
Intelligent Incident Management System

This package provides AI-powered incident detection, routing, and automated remediation
capabilities that extend the existing Splunk MCP server.
"""

from .models.incident import Incident, IncidentSeverity, IncidentStatus
from .models.analysis import AnalysisResult, RiskLevel
from .models.remediation import RemediationTask, TaskType, ExecutionResult
from .interfaces.base import BaseIncidentManager, BaseAnalyzer, BaseRouter

__version__ = "1.0.0"
__all__ = [
    "Incident",
    "IncidentSeverity", 
    "IncidentStatus",
    "AnalysisResult",
    "RiskLevel",
    "RemediationTask",
    "TaskType",
    "ExecutionResult",
    "BaseIncidentManager",
    "BaseAnalyzer",
    "BaseRouter"
]