from aws_cdk import (
    Duration,
    Stack,
    CfnOutput,
    RemovalPolicy,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_elasticloadbalancingv2 as elbv2,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    aws_kms as kms,
    Tags,
)
from constructs import Construct
from cdk_nag import NagSuppressions
import hashlib


class SimpleIncidentManagementECSStack(Stack):
    """
    Simple ECS Stack for Incident Management System
    """

    def __init__(self, scope: Construct, id: str, environment: str = "dev", **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        self.env_name = environment
        
        # Create unique suffix for resource naming
        hash_base_string = (self.account + self.region + self.env_name).encode("utf8")
        self.resource_suffix = str(hashlib.sha256(hash_base_string).hexdigest())[:8]
        
        # Create infrastructure components in proper order
        self._create_kms_key()
        self._create_secrets()
        self._create_ecs_service()  # ECS service (including ALB)
        self._create_outputs()
        
        # Tag all resources
        Tags.of(self).add("Project", "IncidentManagement")
        Tags.of(self).add("Environment", self.env_name)
        Tags.of(self).add("ManagedBy", "CDK")
        Tags.of(self).add("DeploymentType", "ECS")

    def _create_kms_key(self):
        """Create KMS key for encryption"""
        
        self.kms_key = kms.Key(
            self, f"IncidentManagementKey-{self.env_name}",
            description=f"KMS key for incident management ECS {self.env_name}",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY  # Always destroy for dev-only deployment
        )



    def _create_secrets(self):
        """Create or import secrets with rotation enabled for sensitive configuration"""
        
        # Create/Import application configuration secrets with rotation
        try:
            self.app_secrets = secretsmanager.Secret.from_secret_name_v2(
                self, f"AppSecrets-{self.env_name}",
                secret_name=f"incident-management/app-config-{self.env_name}"
            )
        except:
            # Create new secret if it doesn't exist
            self.app_secrets = secretsmanager.Secret(
                self, f"AppSecrets-{self.env_name}",
                secret_name=f"incident-management/app-config-{self.env_name}",
                description=f"Application secrets for incident management {self.env_name}",
                encryption_key=self.kms_key,
                automatic_rotation=secretsmanager.RotationSchedule(
                    self, f"AppSecretsRotation-{self.env_name}",
                    secret=self.app_secrets,
                    rotation_lambda=None,  # Manual rotation for JWT secrets
                    automatically_after=Duration.days(90)  # Rotate every 90 days
                ) if self.env_name == "prod" else None,  # Only enable rotation in prod
                removal_policy=RemovalPolicy.DESTROY if self.env_name == "dev" else RemovalPolicy.RETAIN
            )
        
        # Import existing Slack configuration secrets
        self.slack_secrets = secretsmanager.Secret.from_secret_name_v2(
            self, f"SlackSecrets-{self.env_name}",
            secret_name=f"incident-management/slack-config-{self.env_name}"
        )
        
        # Import existing PagerDuty configuration secrets
        self.pagerduty_secrets = secretsmanager.Secret.from_secret_name_v2(
            self, f"PagerDutySecrets-{self.env_name}",
            secret_name=f"incident-management/pagerduty-config-{self.env_name}"
        )
        
        # Import existing Splunk configuration secrets (for MCP server)
        self.splunk_secrets = secretsmanager.Secret.from_secret_name_v2(
            self, f"SplunkSecrets-{self.env_name}",
            secret_name=f"incident-management/splunk-config-{self.env_name}"
        )

    def _create_ecs_service(self):
        """Create ECS service using patterns for simplicity"""
        
        # Create ECS cluster without Container Insights for dev-only deployment
        cluster = ecs.Cluster(
            self, f"IncidentManagementCluster-{self.env_name}",
            cluster_name=f"incident-management-{self.env_name}",
            container_insights=False  # Disabled for dev-only deployment to reduce costs
        )
        
        # Create the ECS service with ALB using patterns
        self.fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, f"IncidentManagementService-{self.env_name}",
            cluster=cluster,
            service_name=f"incident-management-{self.env_name}",
            cpu=512,  # Dev-only deployment uses smaller resources
            memory_limit_mib=1024,  # Dev-only deployment uses smaller resources
            desired_count=1,  # Single instance for dev-only deployment
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    directory="../../",
                    file="Dockerfile",
                    exclude=[
                        "incident_management/infrastructure/cdk.out",
                        "incident_management/infrastructure/node_modules",
                        "**/__pycache__",
                        "**/*.pyc",
                        "**/.git",
                        "**/.gitignore",
                        "**/test",
                        "**/tests",
                        "**/docs",
                        "**/*.md",
                        "**/.env*",
                        "**/venv",
                        "**/.venv",
                        "**/logs",
                        "**/.pytest_cache",
                        "**/node_modules",
                        "**/cdk.out"
                    ]
                ),
                container_port=8002,
                environment={
                    "ENVIRONMENT": self.env_name,
                    "AWS_REGION": self.region,
                    "API_HOST": "0.0.0.0",
                    "API_PORT": "8002",
                    "LOG_LEVEL": "DEBUG",  # Debug logging for dev-only deployment
                    # Splunk MCP Server configuration - only need secret for direct Splunk connection
                    "SECRET_ARN": f"incident-management/splunk-config-{self.env_name}"
                },
                secrets={
                    "JWT_SECRET": ecs.Secret.from_secrets_manager(
                        self.app_secrets, "jwt_secret"
                    ),
                    "SLACK_WEBHOOK_URL": ecs.Secret.from_secrets_manager(
                        self.slack_secrets, "webhook_url"
                    ),
                    "SLACK_BOT_TOKEN": ecs.Secret.from_secrets_manager(
                        self.slack_secrets, "bot_token"
                    ),
                    "SLACK_SIGNING_SECRET": ecs.Secret.from_secrets_manager(
                        self.slack_secrets, "signing_secret"
                    ),
                    "PAGERDUTY_USER_API_KEY": ecs.Secret.from_secrets_manager(
                        self.pagerduty_secrets, "user_api_key"
                    ),
                    "PAGERDUTY_APP_HOST": ecs.Secret.from_secrets_manager(
                        self.pagerduty_secrets, "app_host"
                    ),
                    "PAGERDUTY_AUTO_CREATE_INCIDENTS": ecs.Secret.from_secrets_manager(
                        self.pagerduty_secrets, "auto_create_incidents"
                    ),
                    "SPLUNK_HOST": ecs.Secret.from_secrets_manager(
                        self.splunk_secrets, "SplunkHost"
                    ),
                    "SPLUNK_TOKEN": ecs.Secret.from_secrets_manager(
                        self.splunk_secrets, "SplunkToken"
                    )
                },
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="incident-management",
                    log_group=logs.LogGroup(
                        self, f"IncidentManagementLogGroup-{self.env_name}",
                        log_group_name=f"/ecs/incident-management-{self.env_name}",
                        retention=logs.RetentionDays.ONE_WEEK,  # One week retention for dev-only deployment
                        removal_policy=RemovalPolicy.DESTROY  # Always destroy for dev-only deployment
                    )
                )
            ),
            public_load_balancer=True,
            listener_port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            health_check_grace_period=Duration.minutes(5)
        )
        
        # Configure auto scaling
        scalable_target = self.fargate_service.service.auto_scale_task_count(
            min_capacity=1,
            max_capacity=3  # Limited scaling for dev-only deployment
        )
        
        # Scale based on CPU utilization
        scalable_target.scale_on_cpu_utilization(
            f"CPUScaling-{self.env_name}",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2)
        )
        
        # Scale based on memory utilization
        scalable_target.scale_on_memory_utilization(
            f"MemoryScaling-{self.env_name}",
            target_utilization_percent=80,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2)
        )
        
        # Add additional IAM permissions for Splunk MCP server
        self._add_additional_iam_permissions()
        
        # Add CDK Nag suppressions for this stack
        self._add_nag_suppressions()
        
        # Add CDK Nag suppressions for this stack
        self._add_nag_suppressions()





    def _add_additional_iam_permissions(self):
        """Add additional IAM permissions for MCP servers"""
        
        # Get the task role created by the ECS pattern
        task_role = self.fargate_service.task_definition.task_role
        
        # Add permissions for Splunk MCP server to access Splunk secrets
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret"
                ],
                resources=[
                    # Legacy secret for backward compatibility
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:splunk-bedrock-secret*",
                    # New incident management Splunk secret
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:incident-management/splunk-config-{self.env_name}*"
                ]
            )
        )
        
        # Add permissions for Bedrock (used by Splunk MCP server for embeddings and AI Investigation)
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel"
                ],
                resources=[
                    # Titan embedding model for Splunk MCP server
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0",
                    f"arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
                    # Claude 3.7 Sonnet inference profile for AI Investigation (multiple regions)
                    f"arn:aws:bedrock:*:{self.account}:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                    # Claude 3.7 Sonnet foundation model (fallback)
                    f"arn:aws:bedrock:*::foundation-model/anthropic.claude-3-7-sonnet-20250219-v1:0",
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-7-sonnet-20250219-v1:0"
                ]
            )
        )

    def _add_nag_suppressions(self):
        """Add CDK Nag suppressions for specific resources"""
        
        # Suppress ECS task definition issues
        NagSuppressions.add_resource_suppressions(
            self.fargate_service.task_definition,
            [
                {
                    "id": "AwsSolutions-ECS2",
                    "reason": "Environment variables contain configuration data, secrets are properly handled via AWS Secrets Manager"
                },
                {
                    "id": "AwsSolutions-ECS4",
                    "reason": "Container insights not required for development environment"
                },
                {
                    "id": "AwsSolutions-ECS7",
                    "reason": "Container runs as non-root user (UID 1001) with dropped capabilities and security hardening applied"
                }
            ]
        )
        
        # Suppress ALB security group issues
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/IncidentManagementService-{self.env_name}/LB/SecurityGroup",
            [
                {
                    "id": "AwsSolutions-EC23",
                    "reason": "ALB security group allows HTTP inbound traffic from internet - required for web application access"
                }
            ]
        )
        
        # Suppress ALB access logging issues
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/IncidentManagementService-{self.env_name}/LB",
            [
                {
                    "id": "AwsSolutions-ELB2",
                    "reason": "ALB access logging disabled for demo environment - not required for demonstration purposes and reduces complexity"
                }
            ]
        )
        
        # Suppress ECS service security group issues
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/IncidentManagementService-{self.env_name}/Service/SecurityGroup",
            [
                {
                    "id": "AwsSolutions-EC23",
                    "reason": "ECS service security group allows inbound traffic from ALB - required for application functionality"
                }
            ]
        )
        
        # Suppress IAM role issues
        task_role = self.fargate_service.task_definition.task_role
        NagSuppressions.add_resource_suppressions(
            task_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard permissions required for Bedrock model access across multiple regions and for Secrets Manager secret versions"
                }
            ]
        )
        
        # Suppress execution role issues
        execution_role = self.fargate_service.task_definition.execution_role
        NagSuppressions.add_resource_suppressions(
            execution_role,
            [
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "AWS managed policy AmazonECSTaskExecutionRolePolicy is required for ECS task execution"
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard permissions required for CloudWatch logs and ECR access"
                }
            ]
        )
        

        
        # Suppress KMS key issues if any
        NagSuppressions.add_resource_suppressions(
            self.kms_key,
            [
                {
                    "id": "AwsSolutions-KMS5",
                    "reason": "KMS key rotation is enabled, default key policy is acceptable for this use case"
                }
            ]
        )
        

        
        # Suppressions for dev-only deployment
        # Suppress ECS Container Insights for development environment
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/IncidentManagementCluster-{self.env_name}",
            [
                {
                    "id": "AwsSolutions-ECS4",
                    "reason": "Container Insights disabled for development environment to reduce costs"
                }
            ]
        )
        
        # Suppress VPC Flow Logs for development environment
        vpc = self.fargate_service.cluster.vpc
        NagSuppressions.add_resource_suppressions(
            vpc,
            [
                {
                    "id": "AwsSolutions-VPC7",
                    "reason": "VPC Flow Logs disabled for development environment to reduce costs and log volume"
                }
            ]
        )


    def _create_outputs(self):
        """Create CloudFormation outputs"""
        
        CfnOutput(
            self, f"LoadBalancerURL-{self.env_name}",
            value=f"http://{self.fargate_service.load_balancer.load_balancer_dns_name}",
            description="URL of the incident management application",
            export_name=f"IncidentManagement-URL-{self.env_name}"
        )
        
        CfnOutput(
            self, f"ECSClusterName-{self.env_name}",
            value=self.fargate_service.cluster.cluster_name,
            description="Name of the ECS cluster",
            export_name=f"IncidentManagement-ECS-Cluster-{self.env_name}"
        )
        
        CfnOutput(
            self, f"ECSServiceName-{self.env_name}",
            value=self.fargate_service.service.service_name,
            description="Name of the ECS service",
            export_name=f"IncidentManagement-ECS-Service-{self.env_name}"
        )
        
