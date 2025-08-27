"""
Health Check System for Incident Management

Provides comprehensive health monitoring for all system components
including local storage, Lambda functions, API Gateway, and external integrations.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

import boto3
from botocore.exceptions import ClientError, BotoCoreError


class HealthStatus(Enum):
    """Health status enumeration"""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass
class ComponentHealth:
    """Health status for a single component"""
    name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any]
    last_checked: datetime
    response_time_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass
class SystemHealth:
    """Overall system health status"""
    overall_status: HealthStatus
    components: List[ComponentHealth]
    timestamp: datetime
    environment: str
    version: str = "1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "overall_status": self.overall_status.value,
            "components": [
                {
                    **asdict(component),
                    "status": component.status.value,
                    "last_checked": component.last_checked.isoformat()
                }
                for component in self.components
            ],
            "timestamp": self.timestamp.isoformat(),
            "environment": self.environment,
            "version": self.version
        }


class HealthChecker:
    """
    Comprehensive health checker for incident management system
    
    Monitors:
    - Local storage and file system performance
    - Lambda functions and execution
    - API Gateway endpoints
    - External service integrations
    - System metrics and thresholds
    """
    
    def __init__(self, environment: str = "dev"):
        self.environment = environment
        self.logger = logging.getLogger(__name__)
        
        # AWS clients
        self.dynamodb = boto3.client('dynamodb')
        self.lambda_client = boto3.client('lambda')
        self.apigateway = boto3.client('apigateway')
        self.cloudwatch = boto3.client('cloudwatch')
        self.sns = boto3.client('sns')
        
        # Configuration
        self.timeout = 30  # seconds
        self.retry_count = 3
        
        # Component configurations
        self.components_config = {
            "dynamodb_tables": [
                f"incidents-{environment}",
                f"audit-logs-{environment}",
                f"incident-config-{environment}"
            ],
            "lambda_functions": [
                f"incident-detector-{environment}",
                f"ai-analyzer-{environment}",
                f"notification-manager-{environment}",
                f"automation-engine-{environment}"
            ],
            "api_gateways": [
                f"incident-management-api-{environment}"
            ]
        }

    async def check_system_health(self) -> SystemHealth:
        """
        Perform comprehensive system health check
        
        Returns:
            SystemHealth: Complete system health status
        """
        self.logger.info(f"Starting system health check for environment: {self.environment}")
        
        components = []
        start_time = time.time()
        
        # Check all components concurrently
        tasks = [
            self._check_dynamodb_health(),
            self._check_lambda_health(),
            self._check_api_gateway_health(),
            self._check_cloudwatch_health(),
            self._check_external_integrations()
        ]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Flatten results and handle exceptions
            for result in results:
                if isinstance(result, Exception):
                    components.append(ComponentHealth(
                        name="system_check",
                        status=HealthStatus.UNHEALTHY,
                        message=f"Health check failed: {str(result)}",
                        details={"error": str(result)},
                        last_checked=datetime.utcnow(),
                        error=str(result)
                    ))
                elif isinstance(result, list):
                    components.extend(result)
                else:
                    components.append(result)
        
        except Exception as e:
            self.logger.error(f"System health check failed: {e}")
            components.append(ComponentHealth(
                name="system_check",
                status=HealthStatus.UNHEALTHY,
                message=f"Critical system failure: {str(e)}",
                details={"error": str(e)},
                last_checked=datetime.utcnow(),
                error=str(e)
            ))
        
        # Determine overall status
        overall_status = self._calculate_overall_status(components)
        
        # Calculate total response time
        total_time = (time.time() - start_time) * 1000
        
        system_health = SystemHealth(
            overall_status=overall_status,
            components=components,
            timestamp=datetime.utcnow(),
            environment=self.environment
        )
        
        # Publish metrics
        await self._publish_health_metrics(system_health, total_time)
        
        self.logger.info(f"System health check completed: {overall_status.value} ({total_time:.2f}ms)")
        return system_health

    async def _check_dynamodb_health(self) -> List[ComponentHealth]:
        """Check DynamoDB table health and performance"""
        components = []
        
        for table_name in self.components_config["dynamodb_tables"]:
            start_time = time.time()
            
            try:
                # Check table status
                response = self.dynamodb.describe_table(TableName=table_name)
                table_status = response['Table']['TableStatus']
                
                # Check recent metrics
                metrics = await self._get_dynamodb_metrics(table_name)
                
                # Determine health status
                if table_status == 'ACTIVE':
                    if metrics.get('throttled_requests', 0) > 0:
                        status = HealthStatus.DEGRADED
                        message = f"Table active but experiencing throttling"
                    else:
                        status = HealthStatus.HEALTHY
                        message = f"Table active and performing well"
                else:
                    status = HealthStatus.UNHEALTHY
                    message = f"Table status: {table_status}"
                
                response_time = (time.time() - start_time) * 1000
                
                components.append(ComponentHealth(
                    name=f"dynamodb_{table_name}",
                    status=status,
                    message=message,
                    details={
                        "table_status": table_status,
                        "item_count": response['Table'].get('ItemCount', 0),
                        "table_size_bytes": response['Table'].get('TableSizeBytes', 0),
                        "metrics": metrics
                    },
                    last_checked=datetime.utcnow(),
                    response_time_ms=response_time
                ))
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'ResourceNotFoundException':
                    status = HealthStatus.UNHEALTHY
                    message = f"Table not found: {table_name}"
                else:
                    status = HealthStatus.UNHEALTHY
                    message = f"DynamoDB error: {error_code}"
                
                components.append(ComponentHealth(
                    name=f"dynamodb_{table_name}",
                    status=status,
                    message=message,
                    details={"error_code": error_code},
                    last_checked=datetime.utcnow(),
                    error=str(e)
                ))
            
            except Exception as e:
                components.append(ComponentHealth(
                    name=f"dynamodb_{table_name}",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Unexpected error checking table",
                    details={"error": str(e)},
                    last_checked=datetime.utcnow(),
                    error=str(e)
                ))
        
        return components

    async def _check_lambda_health(self) -> List[ComponentHealth]:
        """Check Lambda function health and performance"""
        components = []
        
        for function_name in self.components_config["lambda_functions"]:
            start_time = time.time()
            
            try:
                # Get function configuration
                response = self.lambda_client.get_function(FunctionName=function_name)
                config = response['Configuration']
                state = config['State']
                
                # Get recent metrics
                metrics = await self._get_lambda_metrics(function_name)
                
                # Determine health status
                if state == 'Active':
                    error_rate = metrics.get('error_rate', 0)
                    if error_rate > 5:  # 5% error rate threshold
                        status = HealthStatus.DEGRADED
                        message = f"Function active but high error rate: {error_rate:.1f}%"
                    elif metrics.get('throttles', 0) > 0:
                        status = HealthStatus.DEGRADED
                        message = f"Function active but experiencing throttling"
                    else:
                        status = HealthStatus.HEALTHY
                        message = f"Function active and performing well"
                else:
                    status = HealthStatus.UNHEALTHY
                    message = f"Function state: {state}"
                
                response_time = (time.time() - start_time) * 1000
                
                components.append(ComponentHealth(
                    name=f"lambda_{function_name}",
                    status=status,
                    message=message,
                    details={
                        "state": state,
                        "runtime": config.get('Runtime'),
                        "memory_size": config.get('MemorySize'),
                        "timeout": config.get('Timeout'),
                        "last_modified": config.get('LastModified'),
                        "metrics": metrics
                    },
                    last_checked=datetime.utcnow(),
                    response_time_ms=response_time
                ))
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                components.append(ComponentHealth(
                    name=f"lambda_{function_name}",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Lambda error: {error_code}",
                    details={"error_code": error_code},
                    last_checked=datetime.utcnow(),
                    error=str(e)
                ))
            
            except Exception as e:
                components.append(ComponentHealth(
                    name=f"lambda_{function_name}",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Unexpected error checking function",
                    details={"error": str(e)},
                    last_checked=datetime.utcnow(),
                    error=str(e)
                ))
        
        return components

    async def _check_api_gateway_health(self) -> List[ComponentHealth]:
        """Check API Gateway health and performance"""
        components = []
        
        for api_name in self.components_config["api_gateways"]:
            start_time = time.time()
            
            try:
                # Find API by name
                apis = self.apigateway.get_rest_apis()
                api = next((a for a in apis['items'] if a['name'] == api_name), None)
                
                if not api:
                    components.append(ComponentHealth(
                        name=f"apigateway_{api_name}",
                        status=HealthStatus.UNHEALTHY,
                        message=f"API not found: {api_name}",
                        details={},
                        last_checked=datetime.utcnow(),
                        error="API not found"
                    ))
                    continue
                
                # Get API metrics
                metrics = await self._get_api_gateway_metrics(api['id'])
                
                # Determine health status
                error_rate = metrics.get('4xx_error_rate', 0) + metrics.get('5xx_error_rate', 0)
                avg_latency = metrics.get('avg_latency', 0)
                
                if error_rate > 10:  # 10% error rate threshold
                    status = HealthStatus.DEGRADED
                    message = f"API active but high error rate: {error_rate:.1f}%"
                elif avg_latency > 5000:  # 5 second latency threshold
                    status = HealthStatus.DEGRADED
                    message = f"API active but high latency: {avg_latency:.0f}ms"
                else:
                    status = HealthStatus.HEALTHY
                    message = f"API active and performing well"
                
                response_time = (time.time() - start_time) * 1000
                
                components.append(ComponentHealth(
                    name=f"apigateway_{api_name}",
                    status=status,
                    message=message,
                    details={
                        "api_id": api['id'],
                        "created_date": api.get('createdDate', '').isoformat() if api.get('createdDate') else None,
                        "metrics": metrics
                    },
                    last_checked=datetime.utcnow(),
                    response_time_ms=response_time
                ))
                
            except Exception as e:
                components.append(ComponentHealth(
                    name=f"apigateway_{api_name}",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Error checking API Gateway",
                    details={"error": str(e)},
                    last_checked=datetime.utcnow(),
                    error=str(e)
                ))
        
        return components

    async def _check_cloudwatch_health(self) -> ComponentHealth:
        """Check CloudWatch service health"""
        start_time = time.time()
        
        try:
            # Test CloudWatch by listing recent log groups
            response = self.cloudwatch.describe_alarms(
                MaxRecords=1,
                StateValue='OK'
            )
            
            response_time = (time.time() - start_time) * 1000
            
            return ComponentHealth(
                name="cloudwatch",
                status=HealthStatus.HEALTHY,
                message="CloudWatch service accessible",
                details={
                    "alarms_checked": len(response.get('MetricAlarms', [])),
                    "service_available": True
                },
                last_checked=datetime.utcnow(),
                response_time_ms=response_time
            )
            
        except Exception as e:
            return ComponentHealth(
                name="cloudwatch",
                status=HealthStatus.UNHEALTHY,
                message="CloudWatch service unavailable",
                details={"error": str(e)},
                last_checked=datetime.utcnow(),
                error=str(e)
            )

    async def _check_external_integrations(self) -> List[ComponentHealth]:
        """Check external service integrations"""
        components = []
        
        # Check Bedrock service (for AI analysis)
        try:
            bedrock = boto3.client('bedrock')
            start_time = time.time()
            
            # Test Bedrock availability by listing models
            response = bedrock.list_foundation_models()
            response_time = (time.time() - start_time) * 1000
            
            components.append(ComponentHealth(
                name="bedrock_service",
                status=HealthStatus.HEALTHY,
                message="Bedrock service accessible",
                details={
                    "models_available": len(response.get('modelSummaries', [])),
                    "service_available": True
                },
                last_checked=datetime.utcnow(),
                response_time_ms=response_time
            ))
            
        except Exception as e:
            components.append(ComponentHealth(
                name="bedrock_service",
                status=HealthStatus.DEGRADED,
                message="Bedrock service unavailable",
                details={"error": str(e)},
                last_checked=datetime.utcnow(),
                error=str(e)
            ))
        
        # Check Secrets Manager (for chat tokens)
        try:
            secrets = boto3.client('secretsmanager')
            start_time = time.time()
            
            # Test by listing secrets (without retrieving values)
            response = secrets.list_secrets(MaxResults=1)
            response_time = (time.time() - start_time) * 1000
            
            components.append(ComponentHealth(
                name="secrets_manager",
                status=HealthStatus.HEALTHY,
                message="Secrets Manager accessible",
                details={
                    "service_available": True
                },
                last_checked=datetime.utcnow(),
                response_time_ms=response_time
            ))
            
        except Exception as e:
            components.append(ComponentHealth(
                name="secrets_manager",
                status=HealthStatus.DEGRADED,
                message="Secrets Manager unavailable",
                details={"error": str(e)},
                last_checked=datetime.utcnow(),
                error=str(e)
            ))
        
        return components

    async def _get_dynamodb_metrics(self, table_name: str) -> Dict[str, float]:
        """Get DynamoDB metrics for the last 5 minutes"""
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=5)
            
            # Get throttled requests
            throttle_response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/DynamoDB',
                MetricName='ThrottledRequests',
                Dimensions=[{'Name': 'TableName', 'Value': table_name}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=['Sum']
            )
            
            throttled_requests = sum(point['Sum'] for point in throttle_response['Datapoints'])
            
            return {
                "throttled_requests": throttled_requests
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to get DynamoDB metrics for {table_name}: {e}")
            return {}

    async def _get_lambda_metrics(self, function_name: str) -> Dict[str, float]:
        """Get Lambda metrics for the last 5 minutes"""
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=5)
            
            # Get invocations and errors
            invocations_response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Invocations',
                Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=['Sum']
            )
            
            errors_response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Errors',
                Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=['Sum']
            )
            
            throttles_response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Throttles',
                Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=['Sum']
            )
            
            invocations = sum(point['Sum'] for point in invocations_response['Datapoints'])
            errors = sum(point['Sum'] for point in errors_response['Datapoints'])
            throttles = sum(point['Sum'] for point in throttles_response['Datapoints'])
            
            error_rate = (errors / invocations * 100) if invocations > 0 else 0
            
            return {
                "invocations": invocations,
                "errors": errors,
                "throttles": throttles,
                "error_rate": error_rate
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to get Lambda metrics for {function_name}: {e}")
            return {}

    async def _get_api_gateway_metrics(self, api_id: str) -> Dict[str, float]:
        """Get API Gateway metrics for the last 5 minutes"""
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=5)
            
            # Get request count and errors
            count_response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/ApiGateway',
                MetricName='Count',
                Dimensions=[{'Name': 'ApiName', 'Value': api_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=['Sum']
            )
            
            latency_response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/ApiGateway',
                MetricName='Latency',
                Dimensions=[{'Name': 'ApiName', 'Value': api_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=['Average']
            )
            
            requests = sum(point['Sum'] for point in count_response['Datapoints'])
            avg_latency = sum(point['Average'] for point in latency_response['Datapoints']) / len(latency_response['Datapoints']) if latency_response['Datapoints'] else 0
            
            return {
                "requests": requests,
                "avg_latency": avg_latency,
                "4xx_error_rate": 0,  # Would need additional metric calls
                "5xx_error_rate": 0   # Would need additional metric calls
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to get API Gateway metrics for {api_id}: {e}")
            return {}

    def _calculate_overall_status(self, components: List[ComponentHealth]) -> HealthStatus:
        """Calculate overall system status based on component health"""
        if not components:
            return HealthStatus.UNKNOWN
        
        unhealthy_count = sum(1 for c in components if c.status == HealthStatus.UNHEALTHY)
        degraded_count = sum(1 for c in components if c.status == HealthStatus.DEGRADED)
        
        # If any critical component is unhealthy, system is unhealthy
        critical_components = [c for c in components if c.name.startswith(('dynamodb_incidents', 'lambda_incident-detector'))]
        if any(c.status == HealthStatus.UNHEALTHY for c in critical_components):
            return HealthStatus.UNHEALTHY
        
        # If more than 50% of components are unhealthy, system is unhealthy
        if unhealthy_count > len(components) * 0.5:
            return HealthStatus.UNHEALTHY
        
        # If any component is unhealthy or degraded, system is degraded
        if unhealthy_count > 0 or degraded_count > 0:
            return HealthStatus.DEGRADED
        
        return HealthStatus.HEALTHY

    async def _publish_health_metrics(self, health: SystemHealth, response_time: float):
        """Publish health metrics to CloudWatch"""
        try:
            # Overall health metric
            health_value = {
                HealthStatus.HEALTHY: 1.0,
                HealthStatus.DEGRADED: 0.5,
                HealthStatus.UNHEALTHY: 0.0,
                HealthStatus.UNKNOWN: -1.0
            }[health.overall_status]
            
            # Publish metrics
            self.cloudwatch.put_metric_data(
                Namespace='IncidentManagement/Health',
                MetricData=[
                    {
                        'MetricName': 'SystemHealth',
                        'Value': health_value,
                        'Unit': 'None',
                        'Dimensions': [
                            {'Name': 'Environment', 'Value': self.environment}
                        ]
                    },
                    {
                        'MetricName': 'HealthCheckDuration',
                        'Value': response_time,
                        'Unit': 'Milliseconds',
                        'Dimensions': [
                            {'Name': 'Environment', 'Value': self.environment}
                        ]
                    },
                    {
                        'MetricName': 'ComponentCount',
                        'Value': len(health.components),
                        'Unit': 'Count',
                        'Dimensions': [
                            {'Name': 'Environment', 'Value': self.environment}
                        ]
                    }
                ]
            )
            
            # Component-specific metrics
            for component in health.components:
                component_health_value = health_value = {
                    HealthStatus.HEALTHY: 1.0,
                    HealthStatus.DEGRADED: 0.5,
                    HealthStatus.UNHEALTHY: 0.0,
                    HealthStatus.UNKNOWN: -1.0
                }[component.status]
                
                metric_data = {
                    'MetricName': 'ComponentHealth',
                    'Value': component_health_value,
                    'Unit': 'None',
                    'Dimensions': [
                        {'Name': 'Environment', 'Value': self.environment},
                        {'Name': 'Component', 'Value': component.name}
                    ]
                }
                
                if component.response_time_ms:
                    metric_data['Timestamp'] = component.last_checked
                
                self.cloudwatch.put_metric_data(
                    Namespace='IncidentManagement/Health',
                    MetricData=[metric_data]
                )
                
        except Exception as e:
            self.logger.error(f"Failed to publish health metrics: {e}")


# Lambda handler for health checks
def lambda_handler(event, context):
    """AWS Lambda handler for health checks"""
    import os
    import asyncio
    
    environment = os.environ.get('ENVIRONMENT', 'dev')
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create health checker
    health_checker = HealthChecker(environment)
    
    # Run health check
    try:
        health = asyncio.run(health_checker.check_system_health())
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            'body': json.dumps(health.to_dict(), indent=2)
        }
        
    except Exception as e:
        logging.error(f"Health check failed: {e}")
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': 'Health check failed',
                'message': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })
        }