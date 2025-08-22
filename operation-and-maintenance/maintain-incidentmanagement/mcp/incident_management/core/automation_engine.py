"""
Automation engine for executing remediation tasks with safety validation.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import uuid

from ..interfaces.base import BaseAutomationEngine
from ..models.remediation import (
    RemediationTask, ExecutionResult, TaskStatus, TaskType, 
    SafetyCheck, SafetyCheckType
)
from ..models.audit import AuditEvent, AuditEventType


class ValidationResult(Enum):
    """Result of safety validation"""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class SafetyValidationResult:
    """Result of a safety check validation"""
    check: SafetyCheck
    result: ValidationResult
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    execution_time: Optional[timedelta] = None
    
    def is_blocking_failure(self) -> bool:
        """Check if this is a blocking failure"""
        return self.check.is_blocking and self.result == ValidationResult.FAILED


@dataclass
class ExecutionContext:
    """Context for task execution"""
    task: RemediationTask
    user_id: str
    incident_id: Optional[str] = None
    dry_run: bool = False
    force_execution: bool = False
    timeout_seconds: int = 300
    environment: str = "production"
    metadata: Dict[str, Any] = field(default_factory=dict)


class AutomationEngine(BaseAutomationEngine):
    """
    Main automation engine for executing remediation tasks with comprehensive
    safety validation and rollback mechanisms.
    """
    
    def __init__(self, audit_logger=None, config_manager=None, approval_workflow_manager=None):
        self.logger = logging.getLogger(__name__)
        self.audit_logger = audit_logger
        self.config_manager = config_manager
        self.approval_workflow_manager = approval_workflow_manager
        
        # Import testing configuration
        try:
            from ..config.testing_config import get_testing_config, is_testing_mode
            self.testing_config = get_testing_config()
            self.is_testing = is_testing_mode()
        except ImportError:
            self.testing_config = None
            self.is_testing = False
        
        # Task execution tracking
        self.running_tasks: Dict[str, ExecutionContext] = {}
        self.completed_tasks: Dict[str, ExecutionResult] = {}
        
        # Safety validators registry
        self.safety_validators: Dict[SafetyCheckType, Callable] = {}
        self.task_executors: Dict[TaskType, Callable] = {}
        self.rollback_handlers: Dict[TaskType, Callable] = {}
        
        # Initialize built-in validators and executors
        self._register_built_in_validators()
        self._register_built_in_executors()
        
        # Configuration
        self.max_concurrent_tasks = 10
        self.default_timeout = 300
        self.enable_rollback = True
        
    def _register_built_in_validators(self):
        """Register built-in safety validators"""
        self.safety_validators[SafetyCheckType.RESOURCE_AVAILABILITY] = self._validate_resource_availability
        self.safety_validators[SafetyCheckType.DEPENDENCY_CHECK] = self._validate_dependencies
        self.safety_validators[SafetyCheckType.BACKUP_VERIFICATION] = self._validate_backup
        self.safety_validators[SafetyCheckType.PERMISSION_CHECK] = self._validate_permissions
        self.safety_validators[SafetyCheckType.IMPACT_ASSESSMENT] = self._validate_impact
        self.safety_validators[SafetyCheckType.ROLLBACK_READINESS] = self._validate_rollback_readiness
    
    def _register_built_in_executors(self):
        """Register built-in task executors"""
        self.task_executors[TaskType.RESTART_SERVICE] = self._execute_service_restart
        self.task_executors[TaskType.SCALE_RESOURCE] = self._execute_resource_scaling
        self.task_executors[TaskType.UPDATE_CONFIG] = self._execute_config_update
        self.task_executors[TaskType.ROLLBACK_DEPLOYMENT] = self._execute_rollback
        self.task_executors[TaskType.COLLECT_LOGS] = self._execute_log_collection
        self.task_executors[TaskType.RUN_HEALTH_CHECK] = self._execute_health_check
        self.task_executors[TaskType.EXECUTE_SCRIPT] = self._execute_script
        
        # Register rollback handlers
        self.rollback_handlers[TaskType.RESTART_SERVICE] = self._rollback_service_restart
        self.rollback_handlers[TaskType.SCALE_RESOURCE] = self._rollback_resource_scaling
        self.rollback_handlers[TaskType.UPDATE_CONFIG] = self._rollback_config_update
    
    async def execute_task(self, task: RemediationTask, context: Optional[ExecutionContext] = None) -> ExecutionResult:
        """
        Execute a remediation task with full safety validation and rollback support.
        
        Args:
            task: The remediation task to execute
            context: Execution context (optional)
            
        Returns:
            ExecutionResult with execution details
        """
        if context is None:
            context = ExecutionContext(task=task, user_id="system")
        
        # Create execution result
        result = ExecutionResult(
            task_id=task.id,
            status=TaskStatus.RUNNING,
            started_at=datetime.utcnow()
        )
        
        try:
            # Check if we can execute (not too many concurrent tasks)
            if len(self.running_tasks) >= self.max_concurrent_tasks:
                result.mark_failed("Maximum concurrent tasks limit reached")
                return result
            
            # Add to running tasks
            self.running_tasks[task.id] = context
            
            # Log task start
            await self._log_audit_event(
                AuditEventType.AUTOMATION_STARTED,
                f"Started execution of task {task.id}",
                {"task_id": task.id, "task_type": task.task_type.value, "user_id": context.user_id}
            )
            
            # Step 1: Validate task requirements
            validation_result = await self.validate_task(task)
            if not validation_result.get("valid", False):
                result.mark_failed(f"Task validation failed: {validation_result.get('message', 'Unknown error')}")
                return result
            
            # Step 1.5: Check approval workflow (ALWAYS required in testing)
            requires_approval = task.requires_approval()
            
            # In testing mode, ALL actions require approval
            if self.is_testing and self.testing_config:
                requires_approval = self.testing_config.requires_approval(
                    task.task_type.value, 
                    context.user_id
                )
                
                # Check if action is allowed in testing
                if not self.testing_config.is_action_allowed(task.task_type.value, context.environment):
                    result.mark_failed(f"Action {task.task_type.value} is not allowed in testing environment")
                    return result
            
            if self.approval_workflow_manager and requires_approval:
                approval_context = {
                    "user_id": context.user_id,
                    "incident_id": context.incident_id,
                    "environment": context.environment,
                    "incident_severity": context.metadata.get("incident_severity"),
                    "is_testing": self.is_testing,
                    "required_approvers": self.testing_config.get_required_approvers(task.task_type.value) if self.testing_config else 1
                }
                
                approval_request = await self.approval_workflow_manager.evaluate_approval_requirement(task, approval_context)
                if approval_request:
                    result.mark_failed("Task requires approval before execution")
                    result.metadata["approval_request_id"] = approval_request.request_id
                    result.metadata["required_approvers"] = approval_request.required_approvers
                    result.metadata["is_testing_mode"] = self.is_testing
                    
                    # Send Slack notification for approval request
                    if self.testing_config and self.testing_config.notify_all_actions:
                        await self._send_slack_approval_request(task, approval_request, context)
                    
                    return result
            
            # Step 2: Run safety checks
            safety_results = await self._run_safety_checks(task, context)
            blocking_failures = [r for r in safety_results if r.is_blocking_failure()]
            
            if blocking_failures and not context.force_execution:
                failure_messages = [f"{r.check.check_type.value}: {r.message}" for r in blocking_failures]
                result.mark_failed(f"Safety checks failed: {'; '.join(failure_messages)}")
                result.metadata["safety_check_failures"] = [r.__dict__ for r in blocking_failures]
                return result
            
            # Step 3: Execute the task
            if context.dry_run:
                result.mark_completed("Dry run completed successfully")
                result.output = "Task would execute successfully (dry run mode)"
            else:
                execution_result = await self._execute_task_implementation(task, context)
                result.output = execution_result.get("output", "")
                result.exit_code = execution_result.get("exit_code", 0)
                result.metadata.update(execution_result.get("metadata", {}))
                
                if execution_result.get("success", False):
                    result.mark_completed(result.output, result.exit_code)
                else:
                    result.mark_failed(
                        execution_result.get("error", "Task execution failed"),
                        execution_result.get("exit_code", 1)
                    )
                    
                    # Check if rollback is needed
                    if self.enable_rollback and execution_result.get("rollback_required", False):
                        result.rollback_required = True
                        rollback_result = await self._execute_rollback(task, context, result)
                        result.rollback_completed = rollback_result
            
            # Log completion
            await self._log_audit_event(
                AuditEventType.AUTOMATION_COMPLETED if result.is_successful() else AuditEventType.AUTOMATION_FAILED,
                f"Task {task.id} {'completed successfully' if result.is_successful() else 'failed'}",
                {
                    "task_id": task.id,
                    "status": result.status.value,
                    "duration": result.get_duration().total_seconds() if result.get_duration() else None,
                    "exit_code": result.exit_code
                }
            )
            
            # Send Slack notification for action completion
            if self.is_testing and self.testing_config and self.testing_config.notify_all_actions:
                await self._send_slack_action_notification(task, result, context)
            
        except Exception as e:
            self.logger.error(f"Unexpected error executing task {task.id}: {str(e)}")
            result.mark_failed(f"Unexpected error: {str(e)}")
            
            await self._log_audit_event(
                AuditEventType.AUTOMATION_FAILED,
                f"Task {task.id} failed with unexpected error",
                {"task_id": task.id, "error": str(e)}
            )
        
        finally:
            # Remove from running tasks and add to completed
            self.running_tasks.pop(task.id, None)
            self.completed_tasks[task.id] = result
            
            # Clean up old completed tasks (keep last 1000)
            if len(self.completed_tasks) > 1000:
                oldest_tasks = sorted(self.completed_tasks.keys())[:100]
                for task_id in oldest_tasks:
                    self.completed_tasks.pop(task_id, None)
        
        return result
    
    async def validate_task(self, task: RemediationTask) -> Dict[str, Any]:
        """
        Validate task before execution.
        
        Args:
            task: Task to validate
            
        Returns:
            Validation result dictionary
        """
        try:
            # Basic validation
            if not task.id:
                return {"valid": False, "message": "Task ID is required"}
            
            if not task.name:
                return {"valid": False, "message": "Task name is required"}
            
            if task.task_type not in self.task_executors:
                return {"valid": False, "message": f"Unsupported task type: {task.task_type.value}"}
            
            # Check if task requires approval and is approved
            if task.requires_approval() and task.status != TaskStatus.APPROVED:
                return {"valid": False, "message": "Task requires approval before execution"}
            
            # Validate parameters based on task type
            param_validation = await self._validate_task_parameters(task)
            if not param_validation.get("valid", False):
                return param_validation
            
            return {
                "valid": True,
                "message": "Task validation passed",
                "checks_performed": ["basic_validation", "parameter_validation"]
            }
            
        except Exception as e:
            self.logger.error(f"Error validating task {task.id}: {str(e)}")
            return {"valid": False, "message": f"Validation error: {str(e)}"}
    
    async def _run_safety_checks(self, task: RemediationTask, context: ExecutionContext) -> List[SafetyValidationResult]:
        """Run all safety checks for a task"""
        results = []
        
        for safety_check in task.safety_checks:
            try:
                start_time = datetime.utcnow()
                
                # Get validator for this check type
                validator = self.safety_validators.get(safety_check.check_type)
                if not validator:
                    result = SafetyValidationResult(
                        check=safety_check,
                        result=ValidationResult.SKIPPED,
                        message=f"No validator available for {safety_check.check_type.value}"
                    )
                else:
                    # Run the validator with timeout
                    try:
                        validation_result = await asyncio.wait_for(
                            validator(safety_check, task, context),
                            timeout=safety_check.timeout_seconds
                        )
                        result = SafetyValidationResult(
                            check=safety_check,
                            result=validation_result.get("result", ValidationResult.FAILED),
                            message=validation_result.get("message", "No message"),
                            details=validation_result.get("details", {})
                        )
                    except asyncio.TimeoutError:
                        result = SafetyValidationResult(
                            check=safety_check,
                            result=ValidationResult.FAILED,
                            message=f"Safety check timed out after {safety_check.timeout_seconds} seconds"
                        )
                
                result.execution_time = datetime.utcnow() - start_time
                results.append(result)
                
                # Log safety check result
                await self._log_audit_event(
                    AuditEventType.SAFETY_CHECK_COMPLETED,
                    f"Safety check {safety_check.check_type.value} {result.result.value}",
                    {
                        "task_id": task.id,
                        "check_type": safety_check.check_type.value,
                        "result": result.result.value,
                        "message": result.message,
                        "execution_time": result.execution_time.total_seconds() if result.execution_time else None
                    }
                )
                
            except Exception as e:
                self.logger.error(f"Error running safety check {safety_check.check_type.value}: {str(e)}")
                result = SafetyValidationResult(
                    check=safety_check,
                    result=ValidationResult.FAILED,
                    message=f"Safety check error: {str(e)}"
                )
                results.append(result)
        
        return results
    
    async def _execute_task_implementation(self, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Execute the actual task implementation"""
        executor = self.task_executors.get(task.task_type)
        if not executor:
            return {
                "success": False,
                "error": f"No executor available for task type {task.task_type.value}"
            }
        
        try:
            return await executor(task, context)
        except Exception as e:
            self.logger.error(f"Error executing task {task.id}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "rollback_required": True
            }
    
    async def _execute_rollback(self, task: RemediationTask, context: ExecutionContext, original_result: ExecutionResult) -> bool:
        """Execute rollback for a failed task"""
        try:
            await self._log_audit_event(
                AuditEventType.ROLLBACK_STARTED,
                f"Starting rollback for task {task.id}",
                {"task_id": task.id, "original_error": original_result.error_message}
            )
            
            # Try automated rollback first
            rollback_handler = self.rollback_handlers.get(task.task_type)
            if rollback_handler:
                rollback_result = await rollback_handler(task, context, original_result)
                if rollback_result.get("success", False):
                    await self._log_audit_event(
                        AuditEventType.ROLLBACK_COMPLETED,
                        f"Automated rollback completed for task {task.id}",
                        {"task_id": task.id}
                    )
                    return True
            
            # Try manual rollback procedure if available
            if task.rollback_procedure:
                # This would typically involve notifying operators or executing predefined steps
                await self._log_audit_event(
                    AuditEventType.ROLLBACK_MANUAL_REQUIRED,
                    f"Manual rollback required for task {task.id}",
                    {"task_id": task.id, "rollback_procedure": task.rollback_procedure}
                )
                # For now, we'll consider this as rollback initiated but not completed
                return False
            
            await self._log_audit_event(
                AuditEventType.ROLLBACK_FAILED,
                f"No rollback mechanism available for task {task.id}",
                {"task_id": task.id}
            )
            return False
            
        except Exception as e:
            self.logger.error(f"Error during rollback for task {task.id}: {str(e)}")
            await self._log_audit_event(
                AuditEventType.ROLLBACK_FAILED,
                f"Rollback failed for task {task.id}: {str(e)}",
                {"task_id": task.id, "error": str(e)}
            )
            return False
    
    # Safety validators (placeholder implementations)
    async def _validate_resource_availability(self, check: SafetyCheck, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Validate that required resources are available"""
        # Placeholder implementation
        return {
            "result": ValidationResult.PASSED,
            "message": "Resource availability check passed",
            "details": {"resources_checked": ["cpu", "memory", "disk"]}
        }
    
    async def _validate_dependencies(self, check: SafetyCheck, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Validate task dependencies"""
        return {
            "result": ValidationResult.PASSED,
            "message": "Dependency check passed"
        }
    
    async def _validate_backup(self, check: SafetyCheck, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Validate backup availability"""
        return {
            "result": ValidationResult.PASSED,
            "message": "Backup verification passed"
        }
    
    async def _validate_permissions(self, check: SafetyCheck, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Validate user permissions"""
        return {
            "result": ValidationResult.PASSED,
            "message": "Permission check passed"
        }
    
    async def _validate_impact(self, check: SafetyCheck, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Validate potential impact of task"""
        return {
            "result": ValidationResult.PASSED,
            "message": "Impact assessment passed"
        }
    
    async def _validate_rollback_readiness(self, check: SafetyCheck, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Validate rollback readiness"""
        return {
            "result": ValidationResult.PASSED,
            "message": "Rollback readiness check passed"
        }
    
    # Task executors with AWS integrations
    async def _execute_service_restart(self, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Execute service restart using AWS Lambda or ECS"""
        try:
            service_name = task.parameters.get('service_name')
            service_type = task.parameters.get('service_type', 'ecs')  # ecs, lambda, ec2
            
            if not service_name:
                return {
                    "success": False,
                    "error": "service_name parameter is required",
                    "exit_code": 1
                }
            
            if context.dry_run:
                return {
                    "success": True,
                    "output": f"[DRY RUN] Would restart {service_type} service: {service_name}",
                    "exit_code": 0
                }
            
            if service_type == 'ecs':
                return await self._restart_ecs_service(service_name, task.parameters)
            elif service_type == 'lambda':
                return await self._restart_lambda_function(service_name, task.parameters)
            elif service_type == 'ec2':
                return await self._restart_ec2_instance(service_name, task.parameters)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported service type: {service_type}",
                    "exit_code": 1
                }
                
        except Exception as e:
            self.logger.error(f"Error restarting service {service_name}: {str(e)}")
            return {
                "success": False,
                "error": f"Service restart failed: {str(e)}",
                "rollback_required": True,
                "exit_code": 1
            }
    
    async def _execute_resource_scaling(self, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Execute resource scaling for AWS services"""
        try:
            resource_type = task.parameters.get('resource_type')  # ecs, asg, lambda
            resource_name = task.parameters.get('resource_name')
            target_capacity = task.parameters.get('target_capacity')
            
            if not all([resource_type, resource_name, target_capacity]):
                return {
                    "success": False,
                    "error": "resource_type, resource_name, and target_capacity parameters are required",
                    "exit_code": 1
                }
            
            if context.dry_run:
                return {
                    "success": True,
                    "output": f"[DRY RUN] Would scale {resource_type} {resource_name} to {target_capacity}",
                    "exit_code": 0
                }
            
            if resource_type == 'ecs':
                return await self._scale_ecs_service(resource_name, target_capacity, task.parameters)
            elif resource_type == 'asg':
                return await self._scale_auto_scaling_group(resource_name, target_capacity, task.parameters)
            elif resource_type == 'lambda':
                return await self._scale_lambda_concurrency(resource_name, target_capacity, task.parameters)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported resource type: {resource_type}",
                    "exit_code": 1
                }
                
        except Exception as e:
            self.logger.error(f"Error scaling resource: {str(e)}")
            return {
                "success": False,
                "error": f"Resource scaling failed: {str(e)}",
                "rollback_required": True,
                "exit_code": 1
            }
    
    async def _execute_config_update(self, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Execute configuration update"""
        try:
            config_type = task.parameters.get('config_type')  # ssm, secrets_manager, env_vars
            config_key = task.parameters.get('config_key')
            config_value = task.parameters.get('config_value')
            
            if not all([config_type, config_key]):
                return {
                    "success": False,
                    "error": "config_type and config_key parameters are required",
                    "exit_code": 1
                }
            
            if context.dry_run:
                return {
                    "success": True,
                    "output": f"[DRY RUN] Would update {config_type} config {config_key}",
                    "exit_code": 0
                }
            
            if config_type == 'ssm':
                return await self._update_ssm_parameter(config_key, config_value, task.parameters)
            elif config_type == 'secrets_manager':
                return await self._update_secret(config_key, config_value, task.parameters)
            elif config_type == 'env_vars':
                return await self._update_environment_variables(config_key, config_value, task.parameters)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported config type: {config_type}",
                    "exit_code": 1
                }
                
        except Exception as e:
            self.logger.error(f"Error updating configuration: {str(e)}")
            return {
                "success": False,
                "error": f"Configuration update failed: {str(e)}",
                "rollback_required": True,
                "exit_code": 1
            }
    
    async def _execute_rollback(self, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Execute deployment rollback"""
        try:
            deployment_type = task.parameters.get('deployment_type')  # ecs, lambda, codedeploy
            service_name = task.parameters.get('service_name')
            target_revision = task.parameters.get('target_revision', 'previous')
            
            if not all([deployment_type, service_name]):
                return {
                    "success": False,
                    "error": "deployment_type and service_name parameters are required",
                    "exit_code": 1
                }
            
            if context.dry_run:
                return {
                    "success": True,
                    "output": f"[DRY RUN] Would rollback {deployment_type} deployment for {service_name} to {target_revision}",
                    "exit_code": 0
                }
            
            if deployment_type == 'ecs':
                return await self._rollback_ecs_deployment(service_name, target_revision, task.parameters)
            elif deployment_type == 'lambda':
                return await self._rollback_lambda_deployment(service_name, target_revision, task.parameters)
            elif deployment_type == 'codedeploy':
                return await self._rollback_codedeploy_deployment(service_name, target_revision, task.parameters)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported deployment type: {deployment_type}",
                    "exit_code": 1
                }
                
        except Exception as e:
            self.logger.error(f"Error rolling back deployment: {str(e)}")
            return {
                "success": False,
                "error": f"Deployment rollback failed: {str(e)}",
                "exit_code": 1
            }
    
    async def _execute_log_collection(self, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Execute log collection and analysis"""
        try:
            log_source = task.parameters.get('log_source')  # cloudwatch, s3, splunk
            log_group = task.parameters.get('log_group')
            time_range = task.parameters.get('time_range', '1h')
            query = task.parameters.get('query', '')
            
            if not all([log_source, log_group]):
                return {
                    "success": False,
                    "error": "log_source and log_group parameters are required",
                    "exit_code": 1
                }
            
            if context.dry_run:
                return {
                    "success": True,
                    "output": f"[DRY RUN] Would collect logs from {log_source}:{log_group} for {time_range}",
                    "exit_code": 0
                }
            
            if log_source == 'cloudwatch':
                return await self._collect_cloudwatch_logs(log_group, time_range, query, task.parameters)
            elif log_source == 's3':
                return await self._collect_s3_logs(log_group, time_range, query, task.parameters)
            elif log_source == 'splunk':
                return await self._collect_splunk_logs(log_group, time_range, query, task.parameters)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported log source: {log_source}",
                    "exit_code": 1
                }
                
        except Exception as e:
            self.logger.error(f"Error collecting logs: {str(e)}")
            return {
                "success": False,
                "error": f"Log collection failed: {str(e)}",
                "exit_code": 1
            }
    
    async def _execute_health_check(self, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Execute health check"""
        try:
            check_type = task.parameters.get('check_type')  # http, tcp, aws_service
            target = task.parameters.get('target')
            timeout = task.parameters.get('timeout', 30)
            
            if not all([check_type, target]):
                return {
                    "success": False,
                    "error": "check_type and target parameters are required",
                    "exit_code": 1
                }
            
            if context.dry_run:
                return {
                    "success": True,
                    "output": f"[DRY RUN] Would perform {check_type} health check on {target}",
                    "exit_code": 0
                }
            
            if check_type == 'http':
                return await self._perform_http_health_check(target, timeout, task.parameters)
            elif check_type == 'tcp':
                return await self._perform_tcp_health_check(target, timeout, task.parameters)
            elif check_type == 'aws_service':
                return await self._perform_aws_service_health_check(target, timeout, task.parameters)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported check type: {check_type}",
                    "exit_code": 1
                }
                
        except Exception as e:
            self.logger.error(f"Error performing health check: {str(e)}")
            return {
                "success": False,
                "error": f"Health check failed: {str(e)}",
                "exit_code": 1
            }
    
    async def _execute_script(self, task: RemediationTask, context: ExecutionContext) -> Dict[str, Any]:
        """Execute custom script"""
        try:
            script_type = task.parameters.get('script_type', 'bash')  # bash, python, powershell
            script_content = task.parameters.get('script_content')
            script_path = task.parameters.get('script_path')
            working_directory = task.parameters.get('working_directory', '/tmp')
            
            if not (script_content or script_path):
                return {
                    "success": False,
                    "error": "Either script_content or script_path parameter is required",
                    "exit_code": 1
                }
            
            if context.dry_run:
                return {
                    "success": True,
                    "output": f"[DRY RUN] Would execute {script_type} script",
                    "exit_code": 0
                }
            
            return await self._execute_custom_script(
                script_type, script_content, script_path, working_directory, task.parameters
            )
                
        except Exception as e:
            self.logger.error(f"Error executing script: {str(e)}")
            return {
                "success": False,
                "error": f"Script execution failed: {str(e)}",
                "rollback_required": True,
                "exit_code": 1
            }
    
    # Rollback handlers (placeholder implementations)
    async def _rollback_service_restart(self, task: RemediationTask, context: ExecutionContext, original_result: ExecutionResult) -> Dict[str, Any]:
        """Rollback service restart"""
        return {"success": True, "message": "Service restart rollback completed"}
    
    async def _rollback_resource_scaling(self, task: RemediationTask, context: ExecutionContext, original_result: ExecutionResult) -> Dict[str, Any]:
        """Rollback resource scaling"""
        return {"success": True, "message": "Resource scaling rollback completed"}
    
    async def _rollback_config_update(self, task: RemediationTask, context: ExecutionContext, original_result: ExecutionResult) -> Dict[str, Any]:
        """Rollback configuration update"""
        return {"success": True, "message": "Configuration rollback completed"}
    
    async def _validate_task_parameters(self, task: RemediationTask) -> Dict[str, Any]:
        """Validate task parameters based on task type"""
        # Basic parameter validation - can be extended per task type
        if not task.parameters:
            return {"valid": False, "message": "Task parameters are required"}
        
        return {"valid": True, "message": "Parameter validation passed"}
    
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
    
    # AWS Service Integration Methods
    async def _restart_ecs_service(self, service_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Restart ECS service by updating task definition"""
        try:
            cluster_name = parameters.get('cluster_name', 'default')
            
            # Simulate ECS service restart
            # In real implementation, this would use boto3 ECS client
            await asyncio.sleep(0.1)  # Simulate API call
            
            return {
                "success": True,
                "output": f"ECS service {service_name} in cluster {cluster_name} restarted successfully",
                "exit_code": 0,
                "metadata": {
                    "service_name": service_name,
                    "cluster_name": cluster_name,
                    "restart_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to restart ECS service: {str(e)}",
                "exit_code": 1
            }
    
    async def _restart_lambda_function(self, function_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Restart Lambda function by updating configuration"""
        try:
            # Simulate Lambda function restart
            await asyncio.sleep(0.1)  # Simulate API call
            
            return {
                "success": True,
                "output": f"Lambda function {function_name} restarted successfully",
                "exit_code": 0,
                "metadata": {
                    "function_name": function_name,
                    "restart_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to restart Lambda function: {str(e)}",
                "exit_code": 1
            }
    
    async def _restart_ec2_instance(self, instance_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Restart EC2 instance"""
        try:
            restart_type = parameters.get('restart_type', 'reboot')  # reboot, stop_start
            
            # Simulate EC2 instance restart
            await asyncio.sleep(0.2)  # Simulate API call
            
            return {
                "success": True,
                "output": f"EC2 instance {instance_id} restarted using {restart_type}",
                "exit_code": 0,
                "metadata": {
                    "instance_id": instance_id,
                    "restart_type": restart_type,
                    "restart_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to restart EC2 instance: {str(e)}",
                "exit_code": 1
            }
    
    async def _scale_ecs_service(self, service_name: str, target_capacity: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Scale ECS service to target capacity"""
        try:
            cluster_name = parameters.get('cluster_name', 'default')
            current_capacity = parameters.get('current_capacity', 1)
            
            # Simulate ECS service scaling
            await asyncio.sleep(0.1)  # Simulate API call
            
            return {
                "success": True,
                "output": f"ECS service {service_name} scaled from {current_capacity} to {target_capacity} tasks",
                "exit_code": 0,
                "metadata": {
                    "service_name": service_name,
                    "cluster_name": cluster_name,
                    "previous_capacity": current_capacity,
                    "target_capacity": target_capacity,
                    "scale_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to scale ECS service: {str(e)}",
                "exit_code": 1
            }
    
    async def _scale_auto_scaling_group(self, asg_name: str, target_capacity: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Scale Auto Scaling Group to target capacity"""
        try:
            current_capacity = parameters.get('current_capacity', 1)
            
            # Simulate ASG scaling
            await asyncio.sleep(0.1)  # Simulate API call
            
            return {
                "success": True,
                "output": f"Auto Scaling Group {asg_name} scaled from {current_capacity} to {target_capacity} instances",
                "exit_code": 0,
                "metadata": {
                    "asg_name": asg_name,
                    "previous_capacity": current_capacity,
                    "target_capacity": target_capacity,
                    "scale_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to scale Auto Scaling Group: {str(e)}",
                "exit_code": 1
            }
    
    async def _scale_lambda_concurrency(self, function_name: str, target_concurrency: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Scale Lambda function concurrency"""
        try:
            current_concurrency = parameters.get('current_concurrency', 100)
            
            # Simulate Lambda concurrency scaling
            await asyncio.sleep(0.1)  # Simulate API call
            
            return {
                "success": True,
                "output": f"Lambda function {function_name} concurrency scaled from {current_concurrency} to {target_concurrency}",
                "exit_code": 0,
                "metadata": {
                    "function_name": function_name,
                    "previous_concurrency": current_concurrency,
                    "target_concurrency": target_concurrency,
                    "scale_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to scale Lambda concurrency: {str(e)}",
                "exit_code": 1
            }
    
    async def _update_ssm_parameter(self, parameter_name: str, parameter_value: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Update SSM parameter"""
        try:
            parameter_type = parameters.get('parameter_type', 'String')
            
            # Simulate SSM parameter update
            await asyncio.sleep(0.1)  # Simulate API call
            
            return {
                "success": True,
                "output": f"SSM parameter {parameter_name} updated successfully",
                "exit_code": 0,
                "metadata": {
                    "parameter_name": parameter_name,
                    "parameter_type": parameter_type,
                    "update_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to update SSM parameter: {str(e)}",
                "exit_code": 1
            }
    
    async def _update_secret(self, secret_name: str, secret_value: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Update AWS Secrets Manager secret"""
        try:
            # Simulate Secrets Manager update
            await asyncio.sleep(0.1)  # Simulate API call
            
            return {
                "success": True,
                "output": f"Secret {secret_name} updated successfully",
                "exit_code": 0,
                "metadata": {
                    "secret_name": secret_name,
                    "update_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to update secret: {str(e)}",
                "exit_code": 1
            }
    
    async def _update_environment_variables(self, var_name: str, var_value: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Update environment variables for Lambda or ECS"""
        try:
            service_type = parameters.get('service_type', 'lambda')
            service_name = parameters.get('service_name')
            
            # Simulate environment variable update
            await asyncio.sleep(0.1)  # Simulate API call
            
            return {
                "success": True,
                "output": f"Environment variable {var_name} updated for {service_type} service {service_name}",
                "exit_code": 0,
                "metadata": {
                    "variable_name": var_name,
                    "service_type": service_type,
                    "service_name": service_name,
                    "update_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to update environment variable: {str(e)}",
                "exit_code": 1
            }
    
    async def _rollback_ecs_deployment(self, service_name: str, target_revision: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Rollback ECS deployment to previous revision"""
        try:
            cluster_name = parameters.get('cluster_name', 'default')
            
            # Simulate ECS deployment rollback
            await asyncio.sleep(0.2)  # Simulate API call
            
            return {
                "success": True,
                "output": f"ECS service {service_name} rolled back to revision {target_revision}",
                "exit_code": 0,
                "metadata": {
                    "service_name": service_name,
                    "cluster_name": cluster_name,
                    "target_revision": target_revision,
                    "rollback_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to rollback ECS deployment: {str(e)}",
                "exit_code": 1
            }
    
    async def _rollback_lambda_deployment(self, function_name: str, target_revision: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Rollback Lambda deployment to previous version"""
        try:
            # Simulate Lambda deployment rollback
            await asyncio.sleep(0.1)  # Simulate API call
            
            return {
                "success": True,
                "output": f"Lambda function {function_name} rolled back to version {target_revision}",
                "exit_code": 0,
                "metadata": {
                    "function_name": function_name,
                    "target_revision": target_revision,
                    "rollback_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to rollback Lambda deployment: {str(e)}",
                "exit_code": 1
            }
    
    async def _rollback_codedeploy_deployment(self, application_name: str, target_revision: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Rollback CodeDeploy deployment"""
        try:
            deployment_group = parameters.get('deployment_group', 'default')
            
            # Simulate CodeDeploy rollback
            await asyncio.sleep(0.2)  # Simulate API call
            
            return {
                "success": True,
                "output": f"CodeDeploy application {application_name} rolled back to revision {target_revision}",
                "exit_code": 0,
                "metadata": {
                    "application_name": application_name,
                    "deployment_group": deployment_group,
                    "target_revision": target_revision,
                    "rollback_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to rollback CodeDeploy deployment: {str(e)}",
                "exit_code": 1
            }
    
    async def _collect_cloudwatch_logs(self, log_group: str, time_range: str, query: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Collect logs from CloudWatch"""
        try:
            region = parameters.get('region', 'us-east-1')
            
            # Simulate CloudWatch log collection
            await asyncio.sleep(0.2)  # Simulate API call
            
            # Mock log entries
            log_entries = [
                f"[{datetime.utcnow().isoformat()}] INFO: Sample log entry 1",
                f"[{datetime.utcnow().isoformat()}] ERROR: Sample error entry",
                f"[{datetime.utcnow().isoformat()}] INFO: Sample log entry 2"
            ]
            
            return {
                "success": True,
                "output": f"Collected {len(log_entries)} log entries from {log_group}",
                "exit_code": 0,
                "metadata": {
                    "log_group": log_group,
                    "time_range": time_range,
                    "query": query,
                    "region": region,
                    "log_entries": log_entries,
                    "collection_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to collect CloudWatch logs: {str(e)}",
                "exit_code": 1
            }
    
    async def _collect_s3_logs(self, bucket_name: str, time_range: str, query: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Collect logs from S3"""
        try:
            prefix = parameters.get('prefix', '')
            
            # Simulate S3 log collection
            await asyncio.sleep(0.2)  # Simulate API call
            
            return {
                "success": True,
                "output": f"Collected logs from S3 bucket {bucket_name} with prefix {prefix}",
                "exit_code": 0,
                "metadata": {
                    "bucket_name": bucket_name,
                    "prefix": prefix,
                    "time_range": time_range,
                    "query": query,
                    "collection_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to collect S3 logs: {str(e)}",
                "exit_code": 1
            }
    
    async def _collect_splunk_logs(self, index: str, time_range: str, query: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Collect logs from Splunk"""
        try:
            # Simulate Splunk log collection
            await asyncio.sleep(0.2)  # Simulate API call
            
            return {
                "success": True,
                "output": f"Collected logs from Splunk index {index}",
                "exit_code": 0,
                "metadata": {
                    "index": index,
                    "time_range": time_range,
                    "query": query,
                    "collection_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to collect Splunk logs: {str(e)}",
                "exit_code": 1
            }
    
    async def _perform_http_health_check(self, url: str, timeout: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Perform HTTP health check"""
        try:
            expected_status = parameters.get('expected_status', 200)
            
            # Simulate HTTP health check
            await asyncio.sleep(0.1)  # Simulate HTTP request
            
            # Mock successful response
            status_code = 200
            response_time = 0.1
            
            success = status_code == expected_status
            
            return {
                "success": success,
                "output": f"HTTP health check {'passed' if success else 'failed'}: {url} returned {status_code}",
                "exit_code": 0 if success else 1,
                "metadata": {
                    "url": url,
                    "status_code": status_code,
                    "expected_status": expected_status,
                    "response_time": response_time,
                    "check_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"HTTP health check failed: {str(e)}",
                "exit_code": 1
            }
    
    async def _perform_tcp_health_check(self, host_port: str, timeout: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Perform TCP health check"""
        try:
            # Parse host:port
            if ':' in host_port:
                host, port = host_port.split(':', 1)
                port = int(port)
            else:
                return {
                    "success": False,
                    "error": "Invalid host:port format",
                    "exit_code": 1
                }
            
            # Simulate TCP health check
            await asyncio.sleep(0.1)  # Simulate TCP connection
            
            return {
                "success": True,
                "output": f"TCP health check passed: {host}:{port} is reachable",
                "exit_code": 0,
                "metadata": {
                    "host": host,
                    "port": port,
                    "timeout": timeout,
                    "check_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"TCP health check failed: {str(e)}",
                "exit_code": 1
            }
    
    async def _perform_aws_service_health_check(self, service_name: str, timeout: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Perform AWS service health check"""
        try:
            region = parameters.get('region', 'us-east-1')
            
            # Simulate AWS service health check
            await asyncio.sleep(0.1)  # Simulate AWS API call
            
            return {
                "success": True,
                "output": f"AWS service {service_name} health check passed in region {region}",
                "exit_code": 0,
                "metadata": {
                    "service_name": service_name,
                    "region": region,
                    "timeout": timeout,
                    "check_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"AWS service health check failed: {str(e)}",
                "exit_code": 1
            }
    
    async def _execute_custom_script(self, script_type: str, script_content: str, script_path: str, 
                                   working_directory: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute custom script"""
        try:
            # Simulate script execution
            await asyncio.sleep(0.2)  # Simulate script execution time
            
            # Mock successful script execution
            output = f"Script executed successfully\nScript type: {script_type}\nWorking directory: {working_directory}"
            
            return {
                "success": True,
                "output": output,
                "exit_code": 0,
                "metadata": {
                    "script_type": script_type,
                    "working_directory": working_directory,
                    "execution_time": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Script execution failed: {str(e)}",
                "exit_code": 1
            }
    
    # BaseAutomationEngine interface implementation
    async def get_available_tasks(self, incident_type: str) -> List[RemediationTask]:
        """Get available tasks for incident type"""
        # Placeholder implementation
        return []
    
    async def schedule_task(self, task: RemediationTask, schedule_time: datetime) -> bool:
        """Schedule task for future execution"""
        # Placeholder implementation
        return True
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a scheduled or running task"""
        if task_id in self.running_tasks:
            # In a real implementation, this would cancel the running task
            return True
        return False
    
    async def get_task_status(self, task_id: str) -> Optional[ExecutionResult]:
        """Get status of a task execution"""
        return self.completed_tasks.get(task_id)    

    async def _send_slack_approval_request(self, task: RemediationTask, approval_request, context: ExecutionContext):
        """Send Slack notification for approval request"""
        try:
            from ..integrations.slack_bot import SlackBot
            
            if not self.testing_config:
                return
            
            slack_bot = SlackBot()
            
            # Create approval message
            message_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🚨 Remediation Action Approval Required"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Task ID:* {task.id}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Action:* {task.task_type.value}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Requested by:* {context.user_id}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Environment:* {context.environment}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Description:* {task.description}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Parameters:* ```{json.dumps(task.parameters, indent=2)}```"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Required Approvers:* {approval_request.required_approvers}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Approve"
                            },
                            "style": "primary",
                            "action_id": "approve_action",
                            "value": f"{task.id}|{approval_request.request_id}"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "❌ Reject"
                            },
                            "style": "danger",
                            "action_id": "reject_action",
                            "value": f"{task.id}|{approval_request.request_id}"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "ℹ️ Details"
                            },
                            "action_id": "view_details",
                            "value": task.id
                        }
                    ]
                }
            ]
            
            # Send to approval channel
            await slack_bot.send_message(
                channel=self.testing_config.slack_approval_channel,
                text=f"Approval required for {task.task_type.value} action",
                blocks=message_blocks
            )
            
            # Also send notification to general channel
            notification_text = (
                f"🔔 *Testing Mode Alert*\n"
                f"Remediation action `{task.task_type.value}` requested by {context.user_id}\n"
                f"Task ID: `{task.id}`\n"
                f"Approval pending in {self.testing_config.slack_approval_channel}"
            )
            
            await slack_bot.send_message(
                channel=self.testing_config.slack_notification_channel,
                text=notification_text
            )
            
            self.logger.info(f"Sent Slack approval request for task {task.id}")
            
        except Exception as e:
            self.logger.error(f"Failed to send Slack approval request: {str(e)}")
    
    async def _send_slack_action_notification(self, task: RemediationTask, result: ExecutionResult, context: ExecutionContext):
        """Send Slack notification for action completion"""
        try:
            from ..integrations.slack_bot import SlackBot
            
            if not self.testing_config or not self.testing_config.notify_all_actions:
                return
            
            slack_bot = SlackBot()
            
            # Determine status emoji and color
            if result.is_successful():
                status_emoji = "✅"
                color = "good"
                status_text = "COMPLETED"
            else:
                status_emoji = "❌"
                color = "danger"
                status_text = "FAILED"
            
            # Create notification message
            message_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{status_emoji} Remediation Action {status_text}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Task ID:* {task.id}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Action:* {task.task_type.value}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Status:* {result.status.value.upper()}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Duration:* {result.get_duration()}"
                        }
                    ]
                }
            ]
            
            # Add output or error details
            if result.is_successful() and result.output:
                message_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Output:* ```{result.output[:500]}```"
                    }
                })
            elif result.error_message:
                message_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Error:* ```{result.error_message[:500]}```"
                    }
                })
            
            # Add rollback info if needed
            if result.rollback_required:
                rollback_text = "✅ Completed" if result.rollback_completed else "⏳ Required"
                message_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Rollback:* {rollback_text}"
                    }
                })
            
            # Send notification
            await slack_bot.send_message(
                channel=self.testing_config.slack_notification_channel,
                text=f"Action {status_text.lower()}: {task.task_type.value}",
                blocks=message_blocks
            )
            
            self.logger.info(f"Sent Slack action notification for task {task.id}")
            
        except Exception as e:
            self.logger.error(f"Failed to send Slack action notification: {str(e)}")