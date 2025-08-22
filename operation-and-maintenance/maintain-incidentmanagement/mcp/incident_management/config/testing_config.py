"""
Testing configuration for incident management system.
Ensures all remediation actions require approval during testing phase.
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from enum import Enum


class TestingMode(Enum):
    """Testing mode configuration"""
    STRICT_APPROVAL = "strict_approval"  # All actions require approval
    SAFE_TESTING = "safe_testing"        # Only safe actions allowed
    DRY_RUN_ONLY = "dry_run_only"       # No actual execution


@dataclass
class TestingConfig:
    """Configuration for testing environment"""
    
    # Testing mode
    mode: TestingMode = TestingMode.STRICT_APPROVAL
    
    # Approval requirements
    require_approval_for_all_actions: bool = True
    require_dual_approval: bool = True  # Two approvers needed
    approval_timeout_minutes: int = 30
    
    # Slack integration
    slack_approval_channel: str = "#incident-approvals"
    slack_notification_channel: str = "#incident-testing"
    notify_all_actions: bool = True
    
    # Safety overrides
    force_dry_run: bool = False
    enable_rollback: bool = True
    max_concurrent_actions: int = 3
    
    # Allowed approvers (for testing)
    approved_users: List[str] = None
    admin_users: List[str] = None
    
    # Action restrictions
    blocked_actions: List[str] = None
    allowed_environments: List[str] = None
    
    def __post_init__(self):
        """Initialize default values"""
        if self.approved_users is None:
            self.approved_users = [
                "test-admin",
                "incident-manager", 
                "ops-lead"
            ]
        
        if self.admin_users is None:
            self.admin_users = [
                "test-admin",
                "system-admin"
            ]
        
        if self.blocked_actions is None:
            self.blocked_actions = [
                "DELETE_RESOURCE",
                "TERMINATE_INSTANCE", 
                "DROP_DATABASE"
            ]
        
        if self.allowed_environments is None:
            self.allowed_environments = [
                "testing",
                "staging", 
                "development"
            ]
    
    def is_action_allowed(self, action_type: str, environment: str = "testing") -> bool:
        """Check if action is allowed in testing"""
        if action_type in self.blocked_actions:
            return False
        
        if environment not in self.allowed_environments:
            return False
        
        return True
    
    def requires_approval(self, action_type: str, user_id: str) -> bool:
        """Check if action requires approval"""
        if self.require_approval_for_all_actions:
            return True
        
        # Admin users might bypass some approvals in non-strict mode
        if user_id in self.admin_users and self.mode != TestingMode.STRICT_APPROVAL:
            return False
        
        return True
    
    def get_required_approvers(self, action_type: str) -> int:
        """Get number of required approvers"""
        if self.require_dual_approval:
            return 2
        return 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'mode': self.mode.value,
            'require_approval_for_all_actions': self.require_approval_for_all_actions,
            'require_dual_approval': self.require_dual_approval,
            'approval_timeout_minutes': self.approval_timeout_minutes,
            'slack_approval_channel': self.slack_approval_channel,
            'slack_notification_channel': self.slack_notification_channel,
            'notify_all_actions': self.notify_all_actions,
            'force_dry_run': self.force_dry_run,
            'enable_rollback': self.enable_rollback,
            'max_concurrent_actions': self.max_concurrent_actions,
            'approved_users': self.approved_users,
            'admin_users': self.admin_users,
            'blocked_actions': self.blocked_actions,
            'allowed_environments': self.allowed_environments
        }


# Global testing configuration instance
TESTING_CONFIG = TestingConfig()


def get_testing_config() -> TestingConfig:
    """Get the current testing configuration"""
    return TESTING_CONFIG


def update_testing_config(**kwargs) -> None:
    """Update testing configuration"""
    global TESTING_CONFIG
    for key, value in kwargs.items():
        if hasattr(TESTING_CONFIG, key):
            setattr(TESTING_CONFIG, key, value)


def is_testing_mode() -> bool:
    """Check if system is in testing mode"""
    import os
    return os.getenv('ENVIRONMENT', 'production').lower() in ['testing', 'test', 'dev', 'development']