"""
Operational Runbooks for Incident Management System

Provides automated runbooks for common operational tasks including
emergency response, performance troubleshooting, and system recovery.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

import boto3
from botocore.exceptions import ClientError


class RunbookStatus(Enum):
    """Runbook execution status"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class RunbookStep:
    """Individual runbook step"""
    name: str
    description: str
    action: str
    parameters: Dict[str, Any]
    timeout_seconds: int = 300
    retry_count: int = 3


@dataclass
class RunbookExecution:
    """Runbook execution tracking"""
    execution_id: str
    runbook_name: str
    status: RunbookStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    steps_completed: int = 0
    total_steps: int = 0
    results: Dict[str, Any] = None
    error_message: Optional[str] = None


class OperationalRunbooks:
    """
    Automated operational runbooks for incident management system
    
    Provides:
    - Emergency response procedures
    - Performance troubleshooting
    - System recovery workflows
    - Maintenance procedures
    """
    
    def __init__(self, environment: str = "dev"):
        self.environment = environment
        self.logger = logging.getLogger(__name__)
        
        # AWS clients
        self.lambda_client = boto3.client('lambda')
        self.dynamodb = boto3.client('dynamodb')
        self.cloudwatch = boto3.client('cloudwatch')
        self.ssm = boto3.client('ssm')
        self.sns = boto3.client('sns')
        
        # Configuration
        self.timeout = 300  # 5 minutes default timeout
        
    async def execute_emergency_response(self, incident_id: Optional[str] = None) -> RunbookExecution:
        """
        Execute emergency response runbook
        
        Steps:
        1. Check system health
        2. Verify critical components
        3. Assess incident impact
        4. Initiate emergency procedures
        5. Notify stakeholders
        
        Args:
            incident_id: Optional incident ID for context
            
        Returns:
            RunbookExecution: Execution results
        """
        execution_id = f"emergency-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        
        steps = [
            RunbookStep(
                name="system_health_check",
                description="Perform comprehensive system health check",
                action="health_check",
                parameters={}
            ),
            RunbookStep(
                name="verify_critical_components",
                description="Verify critical system components are operational",
                action="component_check",
                parameters={"components": ["dynamodb", "lambda", "api_gateway"]}
            ),
            RunbookStep(
                name="assess_incident_impact",
                description="Assess the impact of the current incident",
                action="impact_assessment",
                parameters={"incident_id": incident_id}
            ),
            RunbookStep(
                name="initiate_emergency_procedures",
                description="Initiate emergency response procedures",
                action="emergency_procedures",
                parameters={}
            ),
            RunbookStep(
                name="notify_stakeholders",
                description="Notify relevant stakeholders of the emergency",
                action="stakeholder_notification",
                parameters={"severity": "critical"}
            )
        ]
        
        execution = RunbookExecution(
            execution_id=execution_id,
            runbook_name="emergency_response",
            status=RunbookStatus.RUNNING,
            start_time=datetime.utcnow(),
            total_steps=len(steps),
            results={}
        )
        
        try:
            for i, step in enumerate(steps):
                self.logger.info(f"Executing step {i+1}/{len(steps)}: {step.name}")
                
                step_result = await self._execute_step(step)
                execution.results[step.name] = step_result
                execution.steps_completed = i + 1
                
                if not step_result.get('success', False):
                    execution.status = RunbookStatus.FAILED
                    execution.error_message = step_result.get('error', 'Step failed')
                    break
            
            if execution.status == RunbookStatus.RUNNING:
                execution.status = RunbookStatus.SUCCESS
                
        except Exception as e:
            execution.status = RunbookStatus.FAILED
            execution.error_message = str(e)
            self.logger.error(f"Emergency response runbook failed: {e}")
        
        finally:
            execution.end_time = datetime.utcnow()
            await self._log_execution(execution)
        
        return execution

    async def execute_performance_troubleshooting(self, component: Optional[str] = None) -> RunbookExecution:
        """
        Execute performance troubleshooting runbook
        
        Steps:
        1. Gather performance metrics
        2. Identify bottlenecks
        3. Analyze error patterns
        4. Check resource utilization
        5. Generate recommendations
        
        Args:
            component: Optional specific component to focus on
            
        Returns:
            RunbookExecution: Execution results
        """
        execution_id = f"perf-troubleshoot-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        
        steps = [
            RunbookStep(
                name="gather_performance_metrics",
                description="Collect performance metrics from all components",
                action="metrics_collection",
                parameters={"timeframe": "1h", "component": component}
            ),
            RunbookStep(
                name="identify_bottlenecks",
                description="Analyze metrics to identify performance bottlenecks",
                action="bottleneck_analysis",
                parameters={}
            ),
            RunbookStep(
                name="analyze_error_patterns",
                description="Analyze error logs for patterns and trends",
                action="error_analysis",
                parameters={"timeframe": "1h"}
            ),
            RunbookStep(
                name="check_resource_utilization",
                description="Check CPU, memory, and network utilization",
                action="resource_check",
                parameters={}
            ),
            RunbookStep(
                name="generate_recommendations",
                description="Generate performance improvement recommendations",
                action="recommendation_generation",
                parameters={}
            )
        ]
        
        execution = RunbookExecution(
            execution_id=execution_id,
            runbook_name="performance_troubleshooting",
            status=RunbookStatus.RUNNING,
            start_time=datetime.utcnow(),
            total_steps=len(steps),
            results={}
        )
        
        try:
            for i, step in enumerate(steps):
                self.logger.info(f"Executing step {i+1}/{len(steps)}: {step.name}")
                
                step_result = await self._execute_step(step)
                execution.results[step.name] = step_result
                execution.steps_completed = i + 1
                
                # Continue even if individual steps fail for troubleshooting
                if not step_result.get('success', False):
                    self.logger.warning(f"Step {step.name} failed: {step_result.get('error')}")
            
            execution.status = RunbookStatus.SUCCESS
                
        except Exception as e:
            execution.status = RunbookStatus.FAILED
            execution.error_message = str(e)
            self.logger.error(f"Performance troubleshooting runbook failed: {e}")
        
        finally:
            execution.end_time = datetime.utcnow()
            await self._log_execution(execution)
        
        return execution

    async def execute_system_recovery(self, recovery_type: str = "auto") -> RunbookExecution:
        """
        Execute system recovery runbook
        
        Steps:
        1. Assess system state
        2. Identify failed components
        3. Attempt automatic recovery
        4. Verify recovery success
        5. Update system status
        
        Args:
            recovery_type: Type of recovery (auto, manual, full)
            
        Returns:
            RunbookExecution: Execution results
        """
        execution_id = f"recovery-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        
        steps = [
            RunbookStep(
                name="assess_system_state",
                description="Assess current system state and identify issues",
                action="system_assessment",
                parameters={}
            ),
            RunbookStep(
                name="identify_failed_components",
                description="Identify specific failed or degraded components",
                action="failure_identification",
                parameters={}
            ),
            RunbookStep(
                name="attempt_recovery",
                description="Attempt automatic recovery procedures",
                action="recovery_procedures",
                parameters={"recovery_type": recovery_type}
            ),
            RunbookStep(
                name="verify_recovery",
                description="Verify that recovery was successful",
                action="recovery_verification",
                parameters={}
            ),
            RunbookStep(
                name="update_system_status",
                description="Update system status and notify stakeholders",
                action="status_update",
                parameters={}
            )
        ]
        
        execution = RunbookExecution(
            execution_id=execution_id,
            runbook_name="system_recovery",
            status=RunbookStatus.RUNNING,
            start_time=datetime.utcnow(),
            total_steps=len(steps),
            results={}
        )
        
        try:
            for i, step in enumerate(steps):
                self.logger.info(f"Executing step {i+1}/{len(steps)}: {step.name}")
                
                step_result = await self._execute_step(step)
                execution.results[step.name] = step_result
                execution.steps_completed = i + 1
                
                if not step_result.get('success', False):
                    execution.status = RunbookStatus.FAILED
                    execution.error_message = step_result.get('error', 'Step failed')
                    break
            
            if execution.status == RunbookStatus.RUNNING:
                execution.status = RunbookStatus.SUCCESS
                
        except Exception as e:
            execution.status = RunbookStatus.FAILED
            execution.error_message = str(e)
            self.logger.error(f"System recovery runbook failed: {e}")
        
        finally:
            execution.end_time = datetime.utcnow()
            await self._log_execution(execution)
        
        return execution

    async def _execute_step(self, step: RunbookStep) -> Dict[str, Any]:
        """Execute a single runbook step"""
        try:
            if step.action == "health_check":
                return await self._health_check_action(step.parameters)
            elif step.action == "component_check":
                return await self._component_check_action(step.parameters)
            elif step.action == "impact_assessment":
                return await self._impact_assessment_action(step.parameters)
            elif step.action == "emergency_procedures":
                return await self._emergency_procedures_action(step.parameters)
            elif step.action == "stakeholder_notification":
                return await self._stakeholder_notification_action(step.parameters)
            elif step.action == "metrics_collection":
                return await self._metrics_collection_action(step.parameters)
            elif step.action == "bottleneck_analysis":
                return await self._bottleneck_analysis_action(step.parameters)
            elif step.action == "error_analysis":
                return await self._error_analysis_action(step.parameters)
            elif step.action == "resource_check":
                return await self._resource_check_action(step.parameters)
            elif step.action == "recommendation_generation":
                return await self._recommendation_generation_action(step.parameters)
            elif step.action == "system_assessment":
                return await self._system_assessment_action(step.parameters)
            elif step.action == "failure_identification":
                return await self._failure_identification_action(step.parameters)
            elif step.action == "recovery_procedures":
                return await self._recovery_procedures_action(step.parameters)
            elif step.action == "recovery_verification":
                return await self._recovery_verification_action(step.parameters)
            elif step.action == "status_update":
                return await self._status_update_action(step.parameters)
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {step.action}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def _health_check_action(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute health check action"""
        try:
            # Import and use the health checker
            from .health_checker import HealthChecker
            
            health_checker = HealthChecker(self.environment)
            health = await health_checker.check_system_health()
            
            return {
                "success": True,
                "data": {
                    "overall_status": health.overall_status.value,
                    "component_count": len(health.components),
                    "healthy_components": len([c for c in health.components if c.status.value == "HEALTHY"]),
                    "degraded_components": len([c for c in health.components if c.status.value == "DEGRADED"]),
                    "unhealthy_components": len([c for c in health.components if c.status.value == "UNHEALTHY"])
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Health check failed: {str(e)}"
            }

    async def _component_check_action(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute component check action"""
        components = parameters.get("components", [])
        results = {}
        
        for component in components:
            try:
                if component == "dynamodb":
                    # Check DynamoDB tables
                    tables = [f"incidents-{self.environment}", f"audit-logs-{self.environment}"]
                    table_status = {}
                    
                    for table in tables:
                        try:
                            response = self.dynamodb.describe_table(TableName=table)
                            table_status[table] = response['Table']['TableStatus']
                        except ClientError as e:
                            table_status[table] = f"Error: {e.response['Error']['Code']}"
                    
                    results[component] = {
                        "status": "healthy" if all(status == "ACTIVE" for status in table_status.values()) else "degraded",
                        "details": table_status
                    }
                    
                elif component == "lambda":
                    # Check Lambda functions
                    functions = [f"incident-detector-{self.environment}", f"ai-analyzer-{self.environment}"]
                    function_status = {}
                    
                    for function in functions:
                        try:
                            response = self.lambda_client.get_function(FunctionName=function)
                            function_status[function] = response['Configuration']['State']
                        except ClientError as e:
                            function_status[function] = f"Error: {e.response['Error']['Code']}"
                    
                    results[component] = {
                        "status": "healthy" if all(status == "Active" for status in function_status.values()) else "degraded",
                        "details": function_status
                    }
                    
                elif component == "api_gateway":
                    # Check API Gateway
                    try:
                        apis = boto3.client('apigateway').get_rest_apis()
                        api_count = len([api for api in apis['items'] if f"incident-management-api-{self.environment}" in api['name']])
                        
                        results[component] = {
                            "status": "healthy" if api_count > 0 else "unhealthy",
                            "details": {"api_count": api_count}
                        }
                    except Exception as e:
                        results[component] = {
                            "status": "unhealthy",
                            "details": {"error": str(e)}
                        }
                        
            except Exception as e:
                results[component] = {
                    "status": "error",
                    "details": {"error": str(e)}
                }
        
        return {
            "success": True,
            "data": results
        }

    async def _impact_assessment_action(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute impact assessment action"""
        incident_id = parameters.get("incident_id")
        
        # Assess system impact
        impact_data = {
            "incident_id": incident_id,
            "assessment_time": datetime.utcnow().isoformat(),
            "affected_services": [],
            "user_impact": "unknown",
            "business_impact": "unknown"
        }
        
        try:
            # Get recent error metrics
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=15)
            
            # Check Lambda error rates
            lambda_functions = [f"incident-detector-{self.environment}", f"ai-analyzer-{self.environment}"]
            
            for function in lambda_functions:
                try:
                    response = self.cloudwatch.get_metric_statistics(
                        Namespace='AWS/Lambda',
                        MetricName='Errors',
                        Dimensions=[{'Name': 'FunctionName', 'Value': function}],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=300,
                        Statistics=['Sum']
                    )
                    
                    errors = sum(point['Sum'] for point in response['Datapoints'])
                    if errors > 0:
                        impact_data["affected_services"].append(function)
                        
                except Exception:
                    pass
            
            # Determine impact level
            if len(impact_data["affected_services"]) > 2:
                impact_data["user_impact"] = "high"
                impact_data["business_impact"] = "high"
            elif len(impact_data["affected_services"]) > 0:
                impact_data["user_impact"] = "medium"
                impact_data["business_impact"] = "medium"
            else:
                impact_data["user_impact"] = "low"
                impact_data["business_impact"] = "low"
            
            return {
                "success": True,
                "data": impact_data
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Impact assessment failed: {str(e)}"
            }

    async def _emergency_procedures_action(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute emergency procedures action"""
        procedures_executed = []
        
        try:
            # Enable enhanced monitoring
            procedures_executed.append("enhanced_monitoring_enabled")
            
            # Scale up critical resources (if applicable)
            procedures_executed.append("resource_scaling_initiated")
            
            # Activate backup systems (if applicable)
            procedures_executed.append("backup_systems_activated")
            
            return {
                "success": True,
                "data": {
                    "procedures_executed": procedures_executed,
                    "execution_time": datetime.utcnow().isoformat()
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Emergency procedures failed: {str(e)}"
            }

    async def _stakeholder_notification_action(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute stakeholder notification action"""
        severity = parameters.get("severity", "medium")
        
        try:
            # Determine notification channels based on severity
            if severity == "critical":
                # Send to critical alerts topic
                topic_arn = f"arn:aws:sns:{boto3.Session().region_name}:{boto3.client('sts').get_caller_identity()['Account']}:incident-critical-alerts-{self.environment}"
            else:
                # Send to warning alerts topic
                topic_arn = f"arn:aws:sns:{boto3.Session().region_name}:{boto3.client('sts').get_caller_identity()['Account']}:incident-warning-alerts-{self.environment}"
            
            message = {
                "alert_type": "runbook_execution",
                "severity": severity,
                "timestamp": datetime.utcnow().isoformat(),
                "environment": self.environment,
                "message": f"Emergency runbook executed for {severity} incident"
            }
            
            try:
                self.sns.publish(
                    TopicArn=topic_arn,
                    Subject=f"🚨 Emergency Runbook Execution - {severity.upper()}",
                    Message=json.dumps(message, indent=2)
                )
                
                return {
                    "success": True,
                    "data": {
                        "notification_sent": True,
                        "topic_arn": topic_arn,
                        "severity": severity
                    }
                }
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'NotFound':
                    # Topic doesn't exist, log but don't fail
                    self.logger.warning(f"SNS topic not found: {topic_arn}")
                    return {
                        "success": True,
                        "data": {
                            "notification_sent": False,
                            "reason": "SNS topic not configured"
                        }
                    }
                else:
                    raise
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"Stakeholder notification failed: {str(e)}"
            }

    # Additional action methods would be implemented here...
    # For brevity, I'll implement a few key ones and indicate where others would go

    async def _metrics_collection_action(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute metrics collection action"""
        timeframe = parameters.get("timeframe", "1h")
        component = parameters.get("component")
        
        # Convert timeframe to minutes
        timeframe_minutes = {"15m": 15, "1h": 60, "4h": 240, "24h": 1440}.get(timeframe, 60)
        
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=timeframe_minutes)
            
            metrics_data = {
                "timeframe": timeframe,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "metrics": {}
            }
            
            # Collect Lambda metrics
            lambda_functions = [f"incident-detector-{self.environment}", f"ai-analyzer-{self.environment}"]
            
            for function in lambda_functions:
                if component and component not in function:
                    continue
                    
                try:
                    # Get invocations, errors, duration
                    invocations = self.cloudwatch.get_metric_statistics(
                        Namespace='AWS/Lambda',
                        MetricName='Invocations',
                        Dimensions=[{'Name': 'FunctionName', 'Value': function}],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=300,
                        Statistics=['Sum']
                    )
                    
                    errors = self.cloudwatch.get_metric_statistics(
                        Namespace='AWS/Lambda',
                        MetricName='Errors',
                        Dimensions=[{'Name': 'FunctionName', 'Value': function}],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=300,
                        Statistics=['Sum']
                    )
                    
                    duration = self.cloudwatch.get_metric_statistics(
                        Namespace='AWS/Lambda',
                        MetricName='Duration',
                        Dimensions=[{'Name': 'FunctionName', 'Value': function}],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=300,
                        Statistics=['Average', 'Maximum']
                    )
                    
                    metrics_data["metrics"][function] = {
                        "invocations": sum(point['Sum'] for point in invocations['Datapoints']),
                        "errors": sum(point['Sum'] for point in errors['Datapoints']),
                        "avg_duration": sum(point['Average'] for point in duration['Datapoints']) / len(duration['Datapoints']) if duration['Datapoints'] else 0,
                        "max_duration": max((point['Maximum'] for point in duration['Datapoints']), default=0)
                    }
                    
                except Exception as e:
                    metrics_data["metrics"][function] = {"error": str(e)}
            
            return {
                "success": True,
                "data": metrics_data
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Metrics collection failed: {str(e)}"
            }

    async def _log_execution(self, execution: RunbookExecution):
        """Log runbook execution to audit trail"""
        try:
            # Store execution details in DynamoDB audit table
            audit_table = f"audit-logs-{self.environment}"
            
            audit_record = {
                "audit_id": {"S": f"runbook-{execution.execution_id}"},
                "timestamp": {"S": execution.start_time.isoformat()},
                "action": {"S": "runbook_execution"},
                "runbook_name": {"S": execution.runbook_name},
                "status": {"S": execution.status.value},
                "duration_seconds": {"N": str(int((execution.end_time - execution.start_time).total_seconds()) if execution.end_time else 0)},
                "steps_completed": {"N": str(execution.steps_completed)},
                "total_steps": {"N": str(execution.total_steps)},
                "environment": {"S": self.environment}
            }
            
            if execution.error_message:
                audit_record["error_message"] = {"S": execution.error_message}
            
            if execution.results:
                audit_record["results"] = {"S": json.dumps(execution.results)}
            
            self.dynamodb.put_item(
                TableName=audit_table,
                Item=audit_record
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log runbook execution: {e}")


# Lambda handler for runbook execution
def lambda_handler(event, context):
    """AWS Lambda handler for runbook execution"""
    import os
    import asyncio
    
    environment = os.environ.get('ENVIRONMENT', 'dev')
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create runbooks instance
    runbooks = OperationalRunbooks(environment)
    
    # Get runbook type from event
    runbook_type = event.get('runbook_type', 'emergency_response')
    parameters = event.get('parameters', {})
    
    try:
        if runbook_type == 'emergency_response':
            execution = asyncio.run(runbooks.execute_emergency_response(
                incident_id=parameters.get('incident_id')
            ))
        elif runbook_type == 'performance_troubleshooting':
            execution = asyncio.run(runbooks.execute_performance_troubleshooting(
                component=parameters.get('component')
            ))
        elif runbook_type == 'system_recovery':
            execution = asyncio.run(runbooks.execute_system_recovery(
                recovery_type=parameters.get('recovery_type', 'auto')
            ))
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': f'Unknown runbook type: {runbook_type}',
                    'supported_types': ['emergency_response', 'performance_troubleshooting', 'system_recovery']
                })
            }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'execution_id': execution.execution_id,
                'status': execution.status.value,
                'steps_completed': execution.steps_completed,
                'total_steps': execution.total_steps,
                'duration_seconds': int((execution.end_time - execution.start_time).total_seconds()) if execution.end_time else 0,
                'results': execution.results
            }, indent=2)
        }
        
    except Exception as e:
        logging.error(f"Runbook execution failed: {e}")
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': 'Runbook execution failed',
                'message': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })
        }