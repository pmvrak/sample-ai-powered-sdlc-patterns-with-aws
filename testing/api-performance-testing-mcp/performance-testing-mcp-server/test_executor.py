"""
Test Executor Module
Handles end-to-end test execution and analysis using ECS/Fargate
"""

import json
import logging
import os
import re
import time
from typing import Dict, Any, List
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

def execute_test(session_id: str, execution_environment: Dict, monitoring_config: Dict,
                s3_client, ecs_client, bedrock_client) -> Dict[str, Any]:
    """
    Execute performance test end-to-end
    
    Args:
        session_id: Session ID linking to test plans
        execution_environment: ECS/Fargate configuration
        monitoring_config: Monitoring and metrics configuration
        s3_client: AWS S3 client
        ecs_client: AWS ECS client
        bedrock_client: AWS Bedrock client
    
    Returns:
        Test execution results and analysis
    """
    try:
        # Validate and sanitize inputs
        session_id = _sanitize_session_id(session_id)
        execution_environment = _validate_execution_environment(execution_environment)
        
        logger.info(f"Starting test execution for session {session_id}")
        
        # Load test plans
        test_plans = _load_test_plans(session_id, s3_client)
        
        # Validate test plans
        validation_result = _validate_test_plans(test_plans)
        if not validation_result['valid']:
            return {
                'session_id': session_id,
                'status': 'validation_failed',
                'error': validation_result['error']
            }
        
        # Start test execution
        execution_result = _start_test_execution(
            session_id, test_plans, execution_environment, ecs_client
        )
        
        # Return immediately after starting tests (async execution)
        final_result = {
            'session_id': session_id,
            'status': 'started',
            'execution': execution_result,
            'message': 'Performance tests started successfully. Results will be available in S3 after completion.',
            'monitoring_commands': {
                'check_tasks': f'aws ecs list-tasks --cluster {execution_environment.get("cluster_name", "performance-testing-cluster")}',
                'view_logs': 'aws logs tail /ecs/java-jmeter-runner --follow',
                'check_results': f'aws s3 ls s3://performance-testing-{session_id}/ --recursive'
            },
            'results_location': f's3://{os.environ.get("S3_BUCKET_NAME")}/perf-pipeline/{session_id}/results/',
            'timestamp': time.time()
        }
        
        # Store initial execution status
        _store_execution_results(session_id, final_result, s3_client)
        
        logger.info(f"Test execution completed for session {session_id}")
        return final_result
        
    except Exception as e:
        logger.error(f"Error in test execution: {str(e)}")
        return {
            'session_id': session_id,
            'status': 'error',
            'error': str(e),
            'timestamp': time.time()
        }

def _load_test_plans(session_id: str, s3_client) -> Dict[str, str]:
    """Load test plans from S3"""
    try:
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        prefix = _sanitize_s3_path(f"perf-pipeline/{session_id}/plans/")
        
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        test_plans = {}
        
        for obj in response.get('Contents', []):
            key = obj['Key']
            plan_name = key.replace(prefix, '')
            
            plan_response = s3_client.get_object(Bucket=bucket_name, Key=key)
            content = plan_response['Body'].read().decode('utf-8')
            test_plans[plan_name] = content
        
        logger.info(f"Loaded {len(test_plans)} test plans")
        return test_plans
        
    except Exception as e:
        logger.warning(f"Failed to load test plans, will be handled upstream: {str(e)}")
        raise

def _validate_test_plans(test_plans: Dict[str, str]) -> Dict[str, Any]:
    """Validate test plans before execution"""
    try:
        if not test_plans:
            return {'valid': False, 'error': 'No test plans found'}
        
        validation_results = []
        
        for plan_name, plan_content in test_plans.items():
            plan_validation = _validate_single_plan(plan_name, plan_content)
            validation_results.append(plan_validation)
        
        failed_validations = [v for v in validation_results if not v['valid']]
        
        if failed_validations:
            return {
                'valid': False,
                'error': f"Validation failed for {len(failed_validations)} plans",
                'details': failed_validations
            }
        
        return {
            'valid': True,
            'validated_plans': len(test_plans),
            'details': validation_results
        }
        
    except Exception as e:
        return {'valid': False, 'error': f"Validation error: {str(e)}"}

def _validate_single_plan(plan_name: str, plan_content: str) -> Dict[str, Any]:
    """Validate a single test plan"""
    try:
        validation_issues = []
        
        # Basic content checks
        if len(plan_content.strip()) < 100:
            validation_issues.append("Plan content too short")
        
        # Java DSL specific checks
        if plan_name.endswith('.java'):
            # Check for JMeter imports (either traditional API or DSL)
            if 'org.apache.jmeter' not in plan_content:
                validation_issues.append("Missing required JMeter imports")
            
            # Check for main method (required for execution)
            if 'public static void main' not in plan_content:
                validation_issues.append("Missing main method for execution")
        
        # JMX specific checks
        elif plan_name.endswith('.jmx'):
            required_elements = ['<jmeterTestPlan', '<TestPlan', '<ThreadGroup']
            for element in required_elements:
                if element not in plan_content:
                    validation_issues.append(f"Missing required JMX element: {element}")
        
        return {
            'plan_name': plan_name,
            'valid': len(validation_issues) == 0,
            'issues': validation_issues
        }
        
    except Exception as e:
        return {
            'plan_name': plan_name,
            'valid': False,
            'issues': [f"Validation error: {str(e)}"]
        }

def _start_test_execution(session_id: str, test_plans: Dict, execution_environment: Dict, ecs_client) -> Dict[str, Any]:
    """Start test execution on ECS/Fargate"""
    try:
        cluster_name = execution_environment.get('cluster_name', 'performance-testing-cluster')
        task_definition = execution_environment.get('task_definition', 'jmeter-runner-corrected')
        
        # Create task definition if it doesn't exist
        _ensure_task_definition_exists(task_definition, execution_environment, ecs_client)
        
        # Start ECS tasks for each test plan
        running_tasks = []
        target_url = execution_environment.get('target_url')
        
        for plan_name, plan_content in test_plans.items():
            task_result = _start_single_test_task(
                session_id, plan_name, cluster_name, task_definition, ecs_client, target_url
            )
            running_tasks.append(task_result)
        
        return {
            'cluster_name': cluster_name,
            'task_definition': task_definition,
            'running_tasks': running_tasks,
            'total_tasks': len(running_tasks),
            'start_time': time.time()
        }
        
    except Exception as e:
        logger.error(f"Error starting test execution: {str(e)}")
        return {
            'error': str(e),
            'status': 'failed_to_start'
        }

def _ensure_task_definition_exists(task_definition_name: str, execution_environment: Dict, ecs_client):
    """Ensure ECS task definition exists"""
    try:
        # Check if task definition exists
        ecs_client.describe_task_definition(taskDefinition=task_definition_name)
        logger.info(f"Task definition {task_definition_name} already exists")
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ClientException':
            # Task definition doesn't exist, create it
            logger.info(f"Creating task definition {task_definition_name}")
            _create_jmeter_task_definition(task_definition_name, execution_environment, ecs_client)
        else:
            raise

def _create_jmeter_task_definition(task_definition_name: str, execution_environment: Dict, ecs_client):
    """Create JMeter task definition"""
    
    cpu = execution_environment.get('cpu', '4096')  # 4 vCPUs for high load
    memory = execution_environment.get('memory', '8192')  # 8GB RAM for 10K threads
    
    task_definition = {
        'family': task_definition_name,
        'networkMode': 'awsvpc',
        'requiresCompatibilities': ['FARGATE'],
        'cpu': cpu,
        'memory': memory,
        'executionRoleArn': os.environ.get('ECS_EXECUTION_ROLE_ARN'),
        'taskRoleArn': os.environ.get('ECS_TASK_ROLE_ARN'),
        'containerDefinitions': [
            {
                'name': 'jmeter-runner',
                'image': f'{os.environ.get("AWS_ACCOUNT_ID")}.dkr.ecr.us-east-1.amazonaws.com/jmeter-runner:latest',
                'essential': True,
                'logConfiguration': {
                    'logDriver': 'awslogs',
                    'options': {
                        'awslogs-group': '/ecs/performance-testing',
                        'awslogs-region': os.environ.get('DEPLOYMENT_REGION', 'us-west-2'),
                        'awslogs-stream-prefix': 'jmeter'
                    }
                },
                'environment': [
                    {'name': 'S3_BUCKET', 'value': os.environ.get('S3_BUCKET_NAME')},
                    {'name': 'SESSION_ID', 'value': '${SESSION_ID}'},
                    {'name': 'TARGET_HOST', 'value': '${TARGET_HOST}'},
                    {'name': 'TARGET_PORT', 'value': '${TARGET_PORT}'},
                    {'name': 'JAVA_OPTS', 'value': '-Xms2g -Xmx6g -XX:+UseG1GC -XX:MaxGCPauseMillis=100'},
                    {'name': 'JVM_ARGS', 'value': '-Xms2g -Xmx6g'}
                ],
                'command': [
                    '/entrypoint.sh'  # Use the existing JMeter runner entrypoint
                ]
            }
        ]
    }
    
    ecs_client.register_task_definition(**task_definition)
    logger.info(f"Created task definition {task_definition_name}")

def _start_single_test_task(session_id: str, plan_name: str, cluster_name: str, task_definition: str, ecs_client, target_url: str = None) -> Dict[str, Any]:
    """Start a single test execution task"""
    try:
        # Default to internal ALB for fake API service if no target URL provided
        if not target_url:
            target_host = "internal-performance-testing-internal-alb-1984904225.us-east-1.elb.amazonaws.com"
            target_port = "80"
        else:
            # Parse target URL
            if target_url.startswith('http://'):
                target_url = target_url[7:]
            elif target_url.startswith('https://'):
                target_url = target_url[8:]
            
            if ':' in target_url:
                target_host, target_port = target_url.split(':', 1)
            else:
                target_host = target_url
                target_port = "80"
        
        response = ecs_client.run_task(
            cluster=cluster_name,
            taskDefinition=task_definition,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': os.environ.get('ECS_SUBNETS').split(','),
                    'securityGroups': os.environ.get('ECS_SECURITY_GROUPS').split(','),
                    'assignPublicIp': 'DISABLED'  # Use private subnets
                }
            },
            overrides={
                'containerOverrides': [
                    {
                        'name': 'jmeter-runner',
                        'environment': [
                            {'name': 'SESSION_ID', 'value': session_id},
                            {'name': 'PLAN_NAME', 'value': plan_name},
                            {'name': 'TARGET_HOST', 'value': target_host},
                            {'name': 'TARGET_PORT', 'value': target_port}
                        ]
                    }
                ]
            },
            tags=[
                {'key': 'SessionId', 'value': session_id},
                {'key': 'PlanName', 'value': plan_name},
                {'key': 'Purpose', 'value': 'PerformanceTesting'}
            ]
        )
        
        task_arn = response['tasks'][0]['taskArn']
        
        return {
            'plan_name': plan_name,
            'task_arn': task_arn,
            'status': 'started',
            'start_time': time.time()
        }
        
    except Exception as e:
        logger.error(f"Error starting task for {plan_name}: {str(e)}")
        return {
            'plan_name': plan_name,
            'status': 'failed_to_start',
            'error': str(e)
        }

def _monitor_execution(session_id: str, execution_result: Dict, monitoring_config: Dict, ecs_client) -> Dict[str, Any]:
    """Monitor test execution progress"""
    try:
        running_tasks = execution_result.get('running_tasks', [])
        cluster_name = execution_result.get('cluster_name')
        
        if not running_tasks:
            return {'status': 'no_tasks_to_monitor'}
        
        # Monitor tasks until completion
        max_wait_time = monitoring_config.get('duration', '30m')
        max_wait_seconds = _time_to_seconds(max_wait_time)
        
        start_time = time.time()
        completed_tasks = []
        
        while time.time() - start_time < max_wait_seconds:
            task_arns = [task['task_arn'] for task in running_tasks if task.get('task_arn')]
            
            if not task_arns:
                break
            
            # Check task status
            response = ecs_client.describe_tasks(
                cluster=cluster_name,
                tasks=task_arns
            )
            
            still_running = []
            
            for task in response['tasks']:
                task_arn = task['taskArn']
                last_status = task['lastStatus']
                
                if last_status in ['STOPPED', 'DEPROVISIONING']:
                    # Task completed
                    task_info = next((t for t in running_tasks if t.get('task_arn') == task_arn), {})
                    completed_tasks.append({
                        **task_info,
                        'final_status': last_status,
                        'stop_reason': task.get('stoppedReason', 'Unknown'),
                        'completion_time': time.time()
                    })
                else:
                    still_running.append(task_arn)
            
            running_tasks = [t for t in running_tasks if t.get('task_arn') in still_running]
            
            if not running_tasks:
                break
            
            # Intentional sleep: Poll ECS task status every 30 seconds to avoid API throttling
            # This is necessary for monitoring long-running performance test tasks
            polling_interval = int(os.environ.get('TASK_POLLING_INTERVAL_SECONDS', '30'))
            time.sleep(polling_interval)
        
        # Fetch logs for failed tasks
        logs_client = boto3.client('logs', region_name=os.environ.get('DEPLOYMENT_REGION', 'us-west-2'))
        task_logs = _fetch_task_logs(completed_tasks, logs_client)
        
        return {
            'session_id': session_id,
            'monitoring_duration': time.time() - start_time,
            'completed_tasks': completed_tasks,
            'still_running': len(running_tasks),
            'total_tasks': len(completed_tasks) + len(running_tasks),
            'task_logs': task_logs
        }
        
    except Exception as e:
        logger.error(f"Error monitoring execution: {str(e)}")
        return {
            'status': 'monitoring_error',
            'error': str(e)
        }

def _collect_test_results(session_id: str, s3_client) -> Dict[str, Any]:
    """Collect test results from S3"""
    try:
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        prefix = _sanitize_s3_path(f"perf-pipeline/{session_id}/results/")
        
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        results = {}
        
        for obj in response.get('Contents', []):
            key = obj['Key']
            result_name = key.replace(prefix, '')
            
            if result_name.endswith('.jtl'):
                # JMeter results file
                result_response = s3_client.get_object(Bucket=bucket_name, Key=key)
                content = result_response['Body'].read().decode('utf-8')
                results[result_name] = _parse_jtl_results(content)
        
        return {
            'session_id': session_id,
            'results_files': list(results.keys()),
            'parsed_results': results,
            'collection_time': time.time()
        }
        
    except Exception as e:
        logger.error(f"Error collecting results: {str(e)}")
        return {
            'status': 'collection_error',
            'error': str(e)
        }

def _parse_jtl_results(jtl_content: str) -> Dict[str, Any]:
    """Parse JMeter JTL results file"""
    try:
        lines = jtl_content.strip().split('\n')
        if len(lines) < 2:
            return {'error': 'Empty or invalid JTL file'}
        
        # Parse header
        header = lines[0].split(',')
        
        # Parse data lines
        results = []
        for line in lines[1:]:
            if line.strip():
                values = line.split(',')
                if len(values) == len(header):
                    result = dict(zip(header, values))
                    results.append(result)
        
        # Calculate summary statistics
        if results:
            response_times = [float(r.get('elapsed', 0)) for r in results if r.get('elapsed', '').isdigit()]
            success_count = len([r for r in results if r.get('success', 'false').lower() == 'true'])
            
            summary = {
                'total_samples': len(results),
                'success_count': success_count,
                'error_count': len(results) - success_count,
                'error_rate': (len(results) - success_count) / len(results) * 100 if results else 0,
                'avg_response_time': sum(response_times) / len(response_times) if response_times else 0,
                'min_response_time': min(response_times) if response_times else 0,
                'max_response_time': max(response_times) if response_times else 0
            }
            
            return {
                'summary': summary,
                'raw_results': results[:100]  # Limit raw results to first 100
            }
        
        return {'error': 'No valid results found'}
        
    except Exception as e:
        return {'error': f'Error parsing JTL: {str(e)}'}

def _analyze_results_with_ai(results: Dict, bedrock_client) -> Dict[str, Any]:
    """Analyze test results using AI"""
    try:
        system_prompt = """You are an expert performance testing analyst. 
        Analyze the provided JMeter test results and provide:
        
        1. Performance Summary: Overall system performance assessment
        2. Issues Identified: Any performance bottlenecks or issues
        3. Recommendations: Specific recommendations for improvement
        4. NFR Compliance: Assessment against non-functional requirements
        
        Return your analysis as a JSON object."""
        
        user_prompt = f"""Analyze these performance test results:

{json.dumps(results, indent=2)}

Provide comprehensive analysis and recommendations."""
        
        prompt_config = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_prompt}]
                }
            ]
        }
        
        body = json.dumps(prompt_config)
        model_id = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
        
        response = bedrock_client.invoke_model(
            body=body,
            modelId=model_id,
            accept="application/json",
            contentType="application/json"
        )
        
        response_body = json.loads(response.get("body").read())
        content_list = response_body.get("content", [])
        if content_list and isinstance(content_list, list) and len(content_list) > 0:
            result_text = content_list[0].get("text", "")
        else:
            raise Exception("Invalid response format from Claude")
        
        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            return {
                'analysis_text': result_text,
                'analysis_type': 'text_format'
            }
            
    except Exception as e:
        logger.error(f"Error in AI analysis: {str(e)}")
        return {
            'error': str(e),
            'fallback_analysis': _create_basic_analysis(results)
        }

def _create_basic_analysis(results: Dict) -> Dict[str, Any]:
    """Create basic analysis when AI fails"""
    try:
        parsed_results = results.get('parsed_results', {})
        
        if not parsed_results:
            return {'status': 'no_results_to_analyze'}
        
        # Aggregate statistics across all result files
        total_samples = 0
        total_errors = 0
        avg_response_times = []
        
        for result_file, result_data in parsed_results.items():
            summary = result_data.get('summary', {})
            total_samples += summary.get('total_samples', 0)
            total_errors += summary.get('error_count', 0)
            if summary.get('avg_response_time', 0) > 0:
                avg_response_times.append(summary.get('avg_response_time', 0))
        
        overall_error_rate = (total_errors / total_samples * 100) if total_samples > 0 else 0
        overall_avg_response_time = sum(avg_response_times) / len(avg_response_times) if avg_response_times else 0
        
        return {
            'performance_summary': {
                'total_samples': total_samples,
                'overall_error_rate': round(overall_error_rate, 2),
                'average_response_time': round(overall_avg_response_time, 2)
            },
            'recommendations': [
                'Review error logs for high error rate' if overall_error_rate > 5 else 'Error rate within acceptable limits',
                'Optimize response time' if overall_avg_response_time > 1000 else 'Response time performance acceptable',
                'Consider load balancing if throughput is insufficient'
            ],
            'analysis_type': 'basic_fallback'
        }
        
    except Exception as e:
        return {'error': f'Basic analysis failed: {str(e)}'}

def _store_execution_results(session_id: str, final_result: Dict, s3_client):
    """Store final execution results in S3"""
    try:
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        s3_key = _sanitize_s3_path(f"perf-pipeline/{session_id}/execution_results.json")
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(final_result, indent=2, default=str),
            ContentType='application/json'
        )
        
        logger.info(f"Execution results stored at s3://{bucket_name}/{s3_key}")
        
    except Exception as e:
        logger.error(f"Error storing execution results: {str(e)}")

def _sanitize_session_id(session_id: str) -> str:
    """Sanitize session ID to prevent path traversal and injection"""
    if not session_id:
        raise ValueError("Session ID is required")
    
    # Allow only alphanumeric, hyphens, and underscores
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        raise ValueError("Session ID contains invalid characters")
    
    # Limit length
    if len(session_id) > 64:
        raise ValueError("Session ID too long")
    
    return session_id

def _validate_execution_environment(execution_environment: Dict) -> Dict:
    """Validate execution environment parameters"""
    if not isinstance(execution_environment, dict):
        execution_environment = {}
    
    # Validate cluster name
    cluster_name = execution_environment.get('cluster_name', 'performance-testing-cluster')
    if not re.match(r'^[a-zA-Z0-9_-]+$', cluster_name):
        raise ValueError("Invalid cluster name")
    
    # Validate task definition
    task_definition = execution_environment.get('task_definition', 'jmeter-runner-corrected')
    if not re.match(r'^[a-zA-Z0-9_-]+$', task_definition):
        raise ValueError("Invalid task definition name")
    
    # Validate target URL if provided
    target_url = execution_environment.get('target_url', '')
    if target_url:
        # Allow internal IPs, service discovery names, and internal ALBs (secure)
        if not (re.match(r'^10\.\d+\.\d+\.\d+:\d+$', target_url) or 
                re.match(r'^[a-zA-Z0-9.-]+\.performance-testing\.local:\d+$', target_url) or
                re.match(r'^internal-[a-zA-Z0-9.-]+\.elb\.amazonaws\.com:\d+$', target_url)):
            raise ValueError("Invalid target URL - only internal IPs, service discovery, and internal ALBs allowed")
    
    return execution_environment

def _sanitize_s3_path(path: str) -> str:
    """Sanitize S3 path to prevent path traversal"""
    if not path:
        raise ValueError("S3 path is required")
    
    # Remove any path traversal attempts
    path = path.replace('..', '').replace('//', '/')
    
    # Ensure it starts with perf-pipeline
    if not path.startswith('perf-pipeline/'):
        raise ValueError("S3 path must be within perf-pipeline directory")
    
    return path

def _time_to_seconds(time_str: str) -> int:
    """Convert time string to seconds"""
    if not time_str:
        return 1800  # Default 30 minutes
    
    time_str = time_str.lower().strip()
    
    if time_str.endswith('s'):
        return int(time_str[:-1])
    elif time_str.endswith('m'):
        return int(time_str[:-1]) * 60
    elif time_str.endswith('h'):
        return int(time_str[:-1]) * 3600
    else:
        try:
            return int(time_str)
        except ValueError:
            return 1800

def _fetch_task_logs(completed_tasks: List[Dict], logs_client) -> Dict[str, Any]:
    """Fetch CloudWatch logs for completed tasks to identify errors"""
    try:
        task_logs = {
            'logs_fetched': 0,
            'error_logs': [],
            'summary': {}
        }
        
        log_group_name = "/ecs/java-jmeter-runner"
        
        for task in completed_tasks:
            task_arn = task.get('task_arn', '')
            plan_name = task.get('plan_name', 'unknown')
            
            # Extract task ID from ARN
            task_id = task_arn.split('/')[-1] if task_arn else ''
            
            if not task_id:
                continue
            
            # Construct log stream name
            log_stream_name = f"ecs/jmeter-runner/{task_id}"
            
            try:
                # Get log events
                response = logs_client.get_log_events(
                    logGroupName=log_group_name,
                    logStreamName=log_stream_name,
                    startFromHead=True
                )
                
                events = response.get('events', [])
                task_logs['logs_fetched'] += 1
                
                # Look for error messages
                error_messages = []
                compilation_errors = []
                
                for event in events:
                    message = event.get('message', '')
                    timestamp = event.get('timestamp', 0)
                    
                    # Check for common error patterns
                    if any(error_pattern in message.lower() for error_pattern in [
                        'error:', 'exception', 'failed', 'could not find or load main class',
                        'classnotfoundexception', 'compilation error'
                    ]):
                        error_messages.append({
                            'timestamp': timestamp,
                            'message': message,
                            'plan_name': plan_name
                        })
                    
                    # Specific compilation errors
                    if 'could not find or load main class' in message.lower():
                        compilation_errors.append({
                            'type': 'ClassNotFoundException',
                            'message': message,
                            'plan_name': plan_name,
                            'timestamp': timestamp
                        })
                
                if error_messages:
                    task_logs['error_logs'].extend(error_messages)
                
                if compilation_errors:
                    if 'compilation_errors' not in task_logs:
                        task_logs['compilation_errors'] = []
                    task_logs['compilation_errors'].extend(compilation_errors)
                
                # Summary for this task
                task_logs['summary'][plan_name] = {
                    'total_log_events': len(events),
                    'error_count': len(error_messages),
                    'has_compilation_errors': len(compilation_errors) > 0,
                    'task_status': task.get('final_status', 'unknown')
                }
                
            except Exception as log_error:
                logger.warning(f"Could not fetch logs for task {task_id}: {str(log_error)}")
                task_logs['summary'][plan_name] = {
                    'log_fetch_error': str(log_error),
                    'task_status': task.get('final_status', 'unknown')
                }
        
        return task_logs
        
    except Exception as e:
        logger.error(f"Error fetching task logs: {str(e)}")
        return {
            'logs_fetched': 0,
            'error_logs': [],
            'fetch_error': str(e)
        }