"""
Approval workflow system for high-risk automation tasks.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import uuid

from ..models.remediation import RemediationTask, TaskStatus
from ..models.audit import AuditEvent, AuditEventType


class ApprovalStatus(Enum):
    """Status of approval requests"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalLevel(Enum):
    """Levels of approval required"""
    SINGLE = "single"          # Single approver required
    DUAL = "dual"              # Two approvers required
    MULTI_LEVEL = "multi_level"  # Multiple levels of approval


class RiskLevel(Enum):
    """Risk levels for automation tasks"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ApprovalRule:
    """Rule defining when approval is required"""
    rule_id: str
    name: str
    description: str
    conditions: Dict[str, Any]  # Conditions that trigger this rule
    approval_level: ApprovalLevel
    required_approvers: List[str]  # User IDs or roles
    timeout_minutes: int = 60
    auto_approve_conditions: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalRequest:
    """Request for task approval"""
    request_id: str
    task_id: str
    task: RemediationTask
    requester_id: str
    approval_level: ApprovalLevel
    required_approvers: List[str]
    status: ApprovalStatus
    created_at: datetime
    expires_at: datetime
    approved_by: List[str] = field(default_factory=list)
    rejected_by: List[str] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    approval_comments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization processing"""
        if not self.request_id:
            self.request_id = self.generate_request_id()
    
    @staticmethod
    def generate_request_id() -> str:
        """Generate a unique approval request ID"""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        unique_suffix = str(uuid.uuid4())[:8]
        return f"APPROVAL-{timestamp}-{unique_suffix.upper()}"
    
    def is_expired(self) -> bool:
        """Check if approval request has expired"""
        return datetime.utcnow() > self.expires_at
    
    def can_approve(self, user_id: str) -> bool:
        """Check if user can approve this request"""
        return (user_id in self.required_approvers and 
                user_id not in self.approved_by and 
                user_id not in self.rejected_by and
                self.status == ApprovalStatus.PENDING and
                not self.is_expired())
    
    def add_approval(self, user_id: str, comment: Optional[str] = None) -> bool:
        """Add approval from user"""
        if not self.can_approve(user_id):
            return False
        
        self.approved_by.append(user_id)
        
        if comment:
            self.approval_comments.append({
                "user_id": user_id,
                "action": "approved",
                "comment": comment,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Check if we have enough approvals
        if self._has_sufficient_approvals():
            self.status = ApprovalStatus.APPROVED
        
        return True
    
    def add_rejection(self, user_id: str, reason: str) -> bool:
        """Add rejection from user"""
        if not self.can_approve(user_id):
            return False
        
        self.rejected_by.append(user_id)
        self.rejection_reason = reason
        self.status = ApprovalStatus.REJECTED
        
        self.approval_comments.append({
            "user_id": user_id,
            "action": "rejected",
            "comment": reason,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return True
    
    def _has_sufficient_approvals(self) -> bool:
        """Check if request has sufficient approvals"""
        if self.approval_level == ApprovalLevel.SINGLE:
            return len(self.approved_by) >= 1
        elif self.approval_level == ApprovalLevel.DUAL:
            return len(self.approved_by) >= 2
        elif self.approval_level == ApprovalLevel.MULTI_LEVEL:
            # For multi-level, we need at least one approval from each required level
            # This is a simplified implementation
            return len(self.approved_by) >= len(self.required_approvers)
        
        return False
    
    def get_pending_approvers(self) -> List[str]:
        """Get list of users who still need to approve"""
        return [user for user in self.required_approvers 
                if user not in self.approved_by and user not in self.rejected_by]


class ApprovalWorkflowManager:
    """
    Manages approval workflows for high-risk automation tasks.
    """
    
    def __init__(self, audit_logger=None, notification_manager=None):
        self.logger = logging.getLogger(__name__)
        self.audit_logger = audit_logger
        self.notification_manager = notification_manager
        
        # Active approval requests
        self.active_requests: Dict[str, ApprovalRequest] = {}
        self.completed_requests: Dict[str, ApprovalRequest] = {}
        
        # Approval rules
        self.approval_rules: List[ApprovalRule] = []
        
        # Configuration
        self.default_timeout_minutes = 60
        self.max_active_requests = 1000
        
        # Initialize default approval rules
        self._initialize_default_rules()
        
        # Start background task for cleanup
        self._cleanup_task = None
    
    def _initialize_default_rules(self):
        """Initialize default approval rules"""
        
        # Critical operations require dual approval
        critical_rule = ApprovalRule(
            rule_id="critical-operations",
            name="Critical Operations",
            description="Critical operations that can cause service outages",
            conditions={
                "task_types": ["ROLLBACK_DEPLOYMENT", "UPDATE_CONFIG"],
                "parameters": {
                    "environment": ["production", "prod"],
                    "service_type": ["database", "critical-service"]
                }
            },
            approval_level=ApprovalLevel.DUAL,
            required_approvers=["ops-manager", "senior-engineer"],
            timeout_minutes=30
        )
        
        # High-risk scaling operations
        scaling_rule = ApprovalRule(
            rule_id="high-risk-scaling",
            name="High-Risk Scaling",
            description="Large-scale resource changes",
            conditions={
                "task_types": ["SCALE_RESOURCE"],
                "parameters": {
                    "target_capacity": {"min": 100}  # Scaling to more than 100 instances
                }
            },
            approval_level=ApprovalLevel.SINGLE,
            required_approvers=["ops-manager"],
            timeout_minutes=15
        )
        
        # Production service restarts
        restart_rule = ApprovalRule(
            rule_id="production-restarts",
            name="Production Service Restarts",
            description="Service restarts in production environment",
            conditions={
                "task_types": ["RESTART_SERVICE"],
                "parameters": {
                    "environment": ["production", "prod"]
                }
            },
            approval_level=ApprovalLevel.SINGLE,
            required_approvers=["ops-engineer"],
            timeout_minutes=10,
            auto_approve_conditions={
                "incident_severity": ["CRITICAL", "HIGH"],
                "business_hours": False
            }
        )
        
        self.approval_rules.extend([critical_rule, scaling_rule, restart_rule])
    
    async def evaluate_approval_requirement(self, task: RemediationTask, context: Dict[str, Any]) -> Optional[ApprovalRequest]:
        """
        Evaluate if a task requires approval and create approval request if needed.
        
        Args:
            task: The remediation task to evaluate
            context: Additional context for evaluation
            
        Returns:
            ApprovalRequest if approval is required, None otherwise
        """
        try:
            # Check if task already requires approval
            if task.approval_required and task.status != TaskStatus.APPROVED:
                # Find matching approval rule
                matching_rule = self._find_matching_rule(task, context)
                
                if matching_rule:
                    # Check auto-approve conditions
                    if self._check_auto_approve_conditions(matching_rule, task, context):
                        # Auto-approve the task
                        task.approve("system-auto-approval")
                        await self._log_audit_event(
                            AuditEventType.TASK_APPROVED,
                            f"Task {task.id} auto-approved based on conditions",
                            {
                                "task_id": task.id,
                                "rule_id": matching_rule.rule_id,
                                "auto_approved": True
                            }
                        )
                        return None
                    
                    # Create approval request
                    approval_request = ApprovalRequest(
                        request_id="",  # Will be generated in __post_init__
                        task_id=task.id,
                        task=task,
                        requester_id=context.get("user_id", "system"),
                        approval_level=matching_rule.approval_level,
                        required_approvers=matching_rule.required_approvers.copy(),
                        status=ApprovalStatus.PENDING,
                        created_at=datetime.utcnow(),
                        expires_at=datetime.utcnow() + timedelta(minutes=matching_rule.timeout_minutes),
                        metadata={
                            "rule_id": matching_rule.rule_id,
                            "rule_name": matching_rule.name
                        }
                    )
                    
                    # Store the request
                    self.active_requests[approval_request.request_id] = approval_request
                    
                    # Update task status
                    task.status = TaskStatus.REQUIRES_APPROVAL
                    
                    # Send notifications to approvers
                    await self._notify_approvers(approval_request)
                    
                    # Log audit event
                    await self._log_audit_event(
                        AuditEventType.TASK_APPROVAL_REQUESTED,
                        f"Approval requested for task {task.id}",
                        {
                            "task_id": task.id,
                            "request_id": approval_request.request_id,
                            "required_approvers": approval_request.required_approvers,
                            "approval_level": approval_request.approval_level.value
                        }
                    )
                    
                    return approval_request
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error evaluating approval requirement for task {task.id}: {str(e)}")
            return None
    
    async def process_approval(self, request_id: str, user_id: str, action: str, 
                             comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Process an approval action from a user.
        
        Args:
            request_id: ID of the approval request
            user_id: ID of the user taking action
            action: "approve" or "reject"
            comment: Optional comment
            
        Returns:
            Result dictionary with success status and details
        """
        try:
            # Get the approval request
            request = self.active_requests.get(request_id)
            if not request:
                return {
                    "success": False,
                    "error": "Approval request not found or already completed"
                }
            
            # Check if request has expired
            if request.is_expired():
                request.status = ApprovalStatus.EXPIRED
                self._move_to_completed(request)
                return {
                    "success": False,
                    "error": "Approval request has expired"
                }
            
            # Check if user can approve
            if not request.can_approve(user_id):
                return {
                    "success": False,
                    "error": "User cannot approve this request"
                }
            
            # Process the action
            if action.lower() == "approve":
                success = request.add_approval(user_id, comment)
                if success:
                    await self._log_audit_event(
                        AuditEventType.TASK_APPROVED,
                        f"Task {request.task_id} approved by {user_id}",
                        {
                            "task_id": request.task_id,
                            "request_id": request_id,
                            "approved_by": user_id,
                            "comment": comment
                        }
                    )
                    
                    # Check if task is fully approved
                    if request.status == ApprovalStatus.APPROVED:
                        request.task.approve(user_id)
                        self._move_to_completed(request)
                        
                        await self._log_audit_event(
                            AuditEventType.TASK_APPROVED,
                            f"Task {request.task_id} fully approved and ready for execution",
                            {
                                "task_id": request.task_id,
                                "request_id": request_id,
                                "final_status": "approved"
                            }
                        )
                        
                        return {
                            "success": True,
                            "message": "Task approved and ready for execution",
                            "status": "approved"
                        }
                    else:
                        return {
                            "success": True,
                            "message": f"Approval recorded. Still need approval from: {', '.join(request.get_pending_approvers())}",
                            "status": "pending",
                            "pending_approvers": request.get_pending_approvers()
                        }
                
            elif action.lower() == "reject":
                success = request.add_rejection(user_id, comment or "No reason provided")
                if success:
                    self._move_to_completed(request)
                    
                    await self._log_audit_event(
                        AuditEventType.TASK_REJECTED,
                        f"Task {request.task_id} rejected by {user_id}",
                        {
                            "task_id": request.task_id,
                            "request_id": request_id,
                            "rejected_by": user_id,
                            "reason": comment
                        }
                    )
                    
                    return {
                        "success": True,
                        "message": "Task rejected",
                        "status": "rejected"
                    }
            
            else:
                return {
                    "success": False,
                    "error": "Invalid action. Must be 'approve' or 'reject'"
                }
            
            return {
                "success": False,
                "error": "Failed to process approval action"
            }
            
        except Exception as e:
            self.logger.error(f"Error processing approval {request_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Internal error: {str(e)}"
            }
    
    async def get_pending_approvals(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get pending approval requests, optionally filtered by user.
        
        Args:
            user_id: Optional user ID to filter by
            
        Returns:
            List of pending approval request summaries
        """
        try:
            pending_requests = []
            
            for request in self.active_requests.values():
                if request.status != ApprovalStatus.PENDING:
                    continue
                
                if request.is_expired():
                    request.status = ApprovalStatus.EXPIRED
                    self._move_to_completed(request)
                    continue
                
                # Filter by user if specified
                if user_id and user_id not in request.required_approvers:
                    continue
                
                request_summary = {
                    "request_id": request.request_id,
                    "task_id": request.task_id,
                    "task_name": request.task.name,
                    "task_description": request.task.description,
                    "requester_id": request.requester_id,
                    "approval_level": request.approval_level.value,
                    "required_approvers": request.required_approvers,
                    "approved_by": request.approved_by,
                    "pending_approvers": request.get_pending_approvers(),
                    "created_at": request.created_at.isoformat(),
                    "expires_at": request.expires_at.isoformat(),
                    "time_remaining": str(request.expires_at - datetime.utcnow()),
                    "can_approve": user_id and request.can_approve(user_id),
                    "metadata": request.metadata
                }
                
                pending_requests.append(request_summary)
            
            return pending_requests
            
        except Exception as e:
            self.logger.error(f"Error getting pending approvals: {str(e)}")
            return []
    
    async def cancel_approval_request(self, request_id: str, user_id: str, reason: str) -> Dict[str, Any]:
        """Cancel an approval request"""
        try:
            request = self.active_requests.get(request_id)
            if not request:
                return {
                    "success": False,
                    "error": "Approval request not found"
                }
            
            # Only requester or admin can cancel
            if request.requester_id != user_id and not self._is_admin(user_id):
                return {
                    "success": False,
                    "error": "Only requester or admin can cancel approval request"
                }
            
            request.status = ApprovalStatus.CANCELLED
            request.rejection_reason = reason
            self._move_to_completed(request)
            
            await self._log_audit_event(
                AuditEventType.TASK_CANCELLED,
                f"Approval request {request_id} cancelled by {user_id}",
                {
                    "request_id": request_id,
                    "task_id": request.task_id,
                    "cancelled_by": user_id,
                    "reason": reason
                }
            )
            
            return {
                "success": True,
                "message": "Approval request cancelled"
            }
            
        except Exception as e:
            self.logger.error(f"Error cancelling approval request {request_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Internal error: {str(e)}"
            }
    
    def _find_matching_rule(self, task: RemediationTask, context: Dict[str, Any]) -> Optional[ApprovalRule]:
        """Find approval rule that matches the task"""
        for rule in self.approval_rules:
            if self._rule_matches_task(rule, task, context):
                return rule
        return None
    
    def _rule_matches_task(self, rule: ApprovalRule, task: RemediationTask, context: Dict[str, Any]) -> bool:
        """Check if a rule matches a task"""
        conditions = rule.conditions
        
        # Check task type
        if "task_types" in conditions:
            if task.task_type.value not in conditions["task_types"]:
                return False
        
        # Check parameters
        if "parameters" in conditions:
            for param_name, param_conditions in conditions["parameters"].items():
                task_param_value = task.parameters.get(param_name)
                
                if isinstance(param_conditions, list):
                    if task_param_value not in param_conditions:
                        return False
                elif isinstance(param_conditions, dict):
                    if "min" in param_conditions:
                        if not task_param_value or task_param_value < param_conditions["min"]:
                            return False
                    if "max" in param_conditions:
                        if not task_param_value or task_param_value > param_conditions["max"]:
                            return False
        
        return True
    
    def _check_auto_approve_conditions(self, rule: ApprovalRule, task: RemediationTask, context: Dict[str, Any]) -> bool:
        """Check if auto-approve conditions are met"""
        if not rule.auto_approve_conditions:
            return False
        
        conditions = rule.auto_approve_conditions
        
        # Check incident severity
        if "incident_severity" in conditions:
            incident_severity = context.get("incident_severity")
            if incident_severity not in conditions["incident_severity"]:
                return False
        
        # Check business hours
        if "business_hours" in conditions:
            is_business_hours = self._is_business_hours()
            if conditions["business_hours"] != is_business_hours:
                return False
        
        return True
    
    def _is_business_hours(self) -> bool:
        """Check if current time is during business hours"""
        now = datetime.utcnow()
        # Simple implementation: Monday-Friday, 9 AM - 5 PM UTC
        return (now.weekday() < 5 and 9 <= now.hour < 17)
    
    def _is_admin(self, user_id: str) -> bool:
        """Check if user is admin"""
        # Simple implementation - in real system this would check user roles
        return user_id in ["admin", "ops-manager", "system-admin"]
    
    def _move_to_completed(self, request: ApprovalRequest):
        """Move request from active to completed"""
        if request.request_id in self.active_requests:
            del self.active_requests[request.request_id]
            self.completed_requests[request.request_id] = request
            
            # Clean up old completed requests
            if len(self.completed_requests) > 1000:
                oldest_requests = sorted(
                    self.completed_requests.keys(),
                    key=lambda x: self.completed_requests[x].created_at
                )[:100]
                for req_id in oldest_requests:
                    del self.completed_requests[req_id]
    
    async def _notify_approvers(self, request: ApprovalRequest):
        """Send notifications to required approvers"""
        if not self.notification_manager:
            return
        
        try:
            message = f"""
Approval Required: {request.task.name}

Task: {request.task.description}
Requester: {request.requester_id}
Approval Level: {request.approval_level.value}
Expires: {request.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}

Please review and approve/reject this automation task.
Request ID: {request.request_id}
"""
            
            for approver in request.required_approvers:
                await self.notification_manager.send_custom_message(
                    channel=f"@{approver}",
                    message=message,
                    metadata={
                        "request_id": request.request_id,
                        "task_id": request.task_id,
                        "message_type": "approval_request"
                    }
                )
                
        except Exception as e:
            self.logger.error(f"Error sending approval notifications: {str(e)}")
    
    async def _log_audit_event(self, event_type: AuditEventType, message: str, details: Dict[str, Any]):
        """Log audit event if audit logger is available"""
        if self.audit_logger:
            event = AuditEvent(
                event_type=event_type,
                message=message,
                details=details,
                timestamp=datetime.utcnow()
            )
            await self.audit_logger.log_event(event)
    
    async def start_cleanup_task(self):
        """Start background cleanup task"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_requests())
    
    async def stop_cleanup_task(self):
        """Stop background cleanup task"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
    
    async def _cleanup_expired_requests(self):
        """Background task to clean up expired requests"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                expired_requests = []
                for request_id, request in self.active_requests.items():
                    if request.is_expired() and request.status == ApprovalStatus.PENDING:
                        request.status = ApprovalStatus.EXPIRED
                        expired_requests.append(request)
                
                for request in expired_requests:
                    self._move_to_completed(request)
                    await self._log_audit_event(
                        AuditEventType.TASK_EXPIRED,
                        f"Approval request {request.request_id} expired",
                        {
                            "request_id": request.request_id,
                            "task_id": request.task_id
                        }
                    )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cleanup task: {str(e)}")
                await asyncio.sleep(60)