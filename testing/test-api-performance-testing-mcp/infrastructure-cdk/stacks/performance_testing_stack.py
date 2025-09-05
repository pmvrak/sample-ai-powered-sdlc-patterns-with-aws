from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_s3 as s3,
    aws_iam as iam,
    aws_logs as logs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ecr as ecr,
    aws_lambda as lambda_,
    aws_servicediscovery as servicediscovery,
    aws_ecr_assets as ecr_assets,
    RemovalPolicy,
    Duration,
    CfnOutput,
    Aspects,
)
from constructs import Construct
from cdk_nag import NagSuppressions


class PerformanceTestingStack(Stack):
    """
    CDK Stack for Performance Testing Infrastructure
    
    Step 4: Deploy basic infrastructure to AWS
    - VPC with public/private subnets
    - ECS Fargate cluster
    - S3 bucket for test artifacts
    - ECR repositories for containers
    - Load balancers for fake API (external and internal)
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Step 4.1: Create VPC and networking
        self._create_networking()
        
        # Step 4.2: Create ECS cluster
        self._create_ecs_cluster()
        
        # Step 4.3: Create S3 bucket for test artifacts
        self._create_storage()
        
        # Step 4.4: Create ECR repositories
        self._create_container_repositories()
        
        # Step 4.5: Create load balancers (external and internal)
        self._create_load_balancers()
        
        # Step 4.6: Create ECS task definitions and IAM roles
        self._create_ecs_task_definitions()
        
        # Step 4.7: Create MCP Server Lambda function
        self._create_mcp_server_lambda()
        
        # Step 4.8: Create outputs for easy access
        self._create_outputs()

    def _create_networking(self):
        """Create VPC with public and private subnets"""
        self.vpc = ec2.Vpc(
            self, "PerformanceTestingVPC",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="PublicSubnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="PrivateSubnet", 
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                )
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True,
            # Enable VPC Flow Logs
            flow_logs={
                "FlowLogsCloudWatch": ec2.FlowLogOptions(
                    destination=ec2.FlowLogDestination.to_cloud_watch_logs(
                        logs.LogGroup(
                            self, "VPCFlowLogsGroup",
                            log_group_name="/aws/vpc/flowlogs",
                            retention=logs.RetentionDays.ONE_WEEK,
                            removal_policy=RemovalPolicy.DESTROY
                        )
                    ),
                    traffic_type=ec2.FlowLogTrafficType.ALL
                )
            }
        )

    def _create_ecs_cluster(self):
        """Create ECS Fargate cluster"""
        self.cluster = ecs.Cluster(
            self, "PerformanceTestingCluster",
            vpc=self.vpc,
            cluster_name="performance-testing-cluster",
            container_insights=True
        )
        
        # Create service discovery namespace
        self.namespace = servicediscovery.PrivateDnsNamespace(
            self, "ServiceDiscoveryNamespace",
            name="performance-testing.local",
            vpc=self.vpc,
            description="Service discovery for performance testing"
        )

    def _create_storage(self):
        """Create S3 bucket for test artifacts"""
        # Create access logs bucket first
        self.access_logs_bucket = s3.Bucket(
            self, "AccessLogsBucket",
            bucket_name=f"performance-testing-access-logs-{self.account}-{self.region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )
        
        # Create main artifacts bucket with access logging
        self.artifacts_bucket = s3.Bucket(
            self, "TestArtifactsBucket",
            bucket_name=f"performance-testing-{self.account}-{self.region}",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            server_access_logs_bucket=self.access_logs_bucket,
            server_access_logs_prefix="s3-access-logs/"
        )
        
        # Add CDK Nag suppressions for S3 HTTPS enforcement
        NagSuppressions.add_resource_suppressions(
            self.artifacts_bucket,
            [
                {
                    "id": "AwsSolutions-S10",
                    "reason": "S3 bucket accessed by Streamlit demo application which runs on HTTP for development/testing purposes"
                }
            ]
        )
        
        NagSuppressions.add_resource_suppressions(
            self.access_logs_bucket,
            [
                {
                    "id": "AwsSolutions-S10",
                    "reason": "Access logs bucket - AWS service access uses HTTPS by default, HTTP enforcement not required for log storage"
                }
            ]
        )
        
        # Add suppressions for bucket policies (CDK auto-generated)
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            "/PerformanceTestingStack/TestArtifactsBucket/Policy",
            [
                {
                    "id": "AwsSolutions-S10",
                    "reason": "S3 bucket accessed by Streamlit demo application which runs on HTTP for development/testing purposes"
                }
            ]
        )
        
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            "/PerformanceTestingStack/AccessLogsBucket/Policy",
            [
                {
                    "id": "AwsSolutions-S10",
                    "reason": "Access logs bucket - AWS service access uses HTTPS by default, HTTP enforcement not required for log storage"
                }
            ]
        )

    def _create_container_repositories(self):
        """Create ECR repositories for containers"""
        self.fake_api_repository = ecr.Repository(
            self, "FakeApiRepository",
            repository_name="fake-api-service",
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # JMeter repository is now created automatically by CDK when using from_asset
        # No need to create it manually

    def _create_load_balancers(self):
        """Create Internal Load Balancer for performance testing"""
        

        
        # Security group for ECS tasks (fake API)
        self.ecs_security_group = ec2.SecurityGroup(
            self, "ECSSecurityGroup",
            vpc=self.vpc,
            description="Security group for ECS tasks",
            allow_all_outbound=True
        )
        
        # Security group for Internal ALB
        self.internal_alb_security_group = ec2.SecurityGroup(
            self, "InternalALBSecurityGroup",
            vpc=self.vpc,
            description="Security group for Internal Application Load Balancer",
            allow_all_outbound=False
        )
        
        # Allow HTTP traffic from JMeter to Internal ALB
        self.internal_alb_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4("10.0.0.0/16"),
            connection=ec2.Port.tcp(80),
            description="HTTP traffic from JMeter runners within VPC"
        )
        
        # Allow Internal ALB to forward traffic to ECS tasks (using VPC CIDR to avoid circular dependency)
        self.internal_alb_security_group.add_egress_rule(
            peer=ec2.Peer.ipv4("10.0.0.0/16"),
            connection=ec2.Port.tcp(8080),
            description="HTTP traffic to ECS tasks"
        )
        
        # Add CDK Nag suppression for Internal ALB Security Group
        NagSuppressions.add_resource_suppressions(
            self.internal_alb_security_group,
            [
                {
                    "id": "AwsSolutions-EC23",
                    "reason": "Internal ALB security group restricts access to VPC CIDR (10.0.0.0/16) only - this is appropriate for internal load balancer within VPC"
                }
            ]
        )
        
        # Security group for JMeter runners
        self.jmeter_security_group = ec2.SecurityGroup(
            self, "JMeterSecurityGroup",
            vpc=self.vpc,
            description="Security group for JMeter runners",
            allow_all_outbound=False
        )
        
        # Allow HTTPS for AWS API calls and ECR
        self.jmeter_security_group.add_egress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="HTTPS for AWS API calls and ECR"
        )
        
        # Allow HTTP to fake API service via internal ALB
        self.jmeter_security_group.add_egress_rule(
            peer=ec2.Peer.ipv4("10.0.0.0/16"),
            connection=ec2.Port.tcp(80),
            description="HTTP to internal ALB"
        )
        
        # Allow DNS resolution
        self.jmeter_security_group.add_egress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(53),
            description="DNS resolution"
        )
        
        self.jmeter_security_group.add_egress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.udp(53),
            description="DNS resolution"
        )
        
        # Allow ECS tasks to receive traffic from Internal ALB
        self.ecs_security_group.add_ingress_rule(
            peer=ec2.Peer.security_group_id(self.internal_alb_security_group.security_group_id),
            connection=ec2.Port.tcp(8080),
            description="HTTP traffic from Internal ALB"
        )
        
        # Allow ECS tasks to communicate with each other within VPC
        self.ecs_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4("10.0.0.0/16"),
            connection=ec2.Port.tcp(8080),
            description="HTTP traffic from VPC (ECS tasks)"
        )
        

        
        # Create Internal ALB for JMeter runners (VPC-only)
        self.internal_load_balancer = elbv2.ApplicationLoadBalancer(
            self, "InternalApplicationLoadBalancer",
            vpc=self.vpc,
            internet_facing=False,  # Internal ALB only
            security_group=self.internal_alb_security_group,
            load_balancer_name="performance-testing-internal-alb",
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )
        
        # Enable ALB access logging
        self.internal_load_balancer.log_access_logs(
            bucket=self.access_logs_bucket,
            prefix="alb-access-logs"
        )
        

        
        # Create target group for internal ALB
        self.internal_target_group = elbv2.ApplicationTargetGroup(
            self, "InternalFakeApiTargetGroup",
            vpc=self.vpc,
            port=8080,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path="/health",
                protocol=elbv2.Protocol.HTTP,
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3
            ),
            target_group_name="internal-fake-api-tg"
        )
        
        # Create internal listener
        self.internal_listener = self.internal_load_balancer.add_listener(
            "InternalALBListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[self.internal_target_group]
        )

    def _create_ecs_task_definitions(self):
        """Create ECS task definitions and IAM roles"""
        
        # Create IAM roles for ECS tasks with custom policies (CDK Nag compliant)
        self.ecs_task_execution_role = iam.Role(
            self, "ECSTaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            inline_policies={
                "ECSTaskExecutionPolicy": iam.PolicyDocument(
                    statements=[
                        # ECR permissions for pulling images
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ecr:GetAuthorizationToken",
                                "ecr:BatchCheckLayerAvailability",
                                "ecr:GetDownloadUrlForLayer",
                                "ecr:BatchGetImage"
                            ],
                            resources=[
                                self.fake_api_repository.repository_arn,
                                f"arn:aws:ecr:{self.region}:{self.account}:repository/*"
                            ]
                        ),
                        # CloudWatch Logs permissions (allow all /ecs/* log groups)
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/ecs/*"
                            ]
                        )
                    ]
                )
            }
        )
        
        self.ecs_task_role = iam.Role(
            self, "ECSTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            inline_policies={
                "S3Access": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:GetObject",
                                "s3:PutObject",
                                "s3:DeleteObject",
                                "s3:ListBucket"
                            ],
                            resources=[
                                self.artifacts_bucket.bucket_arn,
                                f"{self.artifacts_bucket.bucket_arn}/*"
                            ]
                        )
                    ]
                )
            }
        )
        
        # Create CloudWatch log groups
        self.fake_api_log_group = logs.LogGroup(
            self, "FakeApiLogGroup",
            log_group_name="/ecs/fake-api-service",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        self.jmeter_log_group = logs.LogGroup(
            self, "JMeterLogGroup", 
            log_group_name="/ecs/jmeter-runner",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Create JMeter task definition (for on-demand execution)
        self.jmeter_task_definition = ecs.FargateTaskDefinition(
            self, "JMeterTaskDefinition",
            memory_limit_mib=4096,
            cpu=2048,
            execution_role=self.ecs_task_execution_role,
            task_role=self.ecs_task_role
        )
        
        # Add JMeter container (environment variables are non-sensitive configuration)
        self.jmeter_container = self.jmeter_task_definition.add_container(
            "jmeter-runner",
            # Build JMeter image from source during CDK deployment
            image=ecs.ContainerImage.from_asset(
                "../jmeter-runner",
                platform=ecr_assets.Platform.LINUX_AMD64
            ),
            environment={
                "TARGET_HOST": "fake-api-service.performance-testing.local",
                "TARGET_PORT": "8080",
                "S3_BUCKET": self.artifacts_bucket.bucket_name
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="jmeter",
                log_group=self.jmeter_log_group
            )
        )
        
        # Add CDK Nag suppressions
        NagSuppressions.add_resource_suppressions(
            self.jmeter_task_definition,
            [
                {
                    "id": "AwsSolutions-ECS2",
                    "reason": "Environment variables contain non-sensitive configuration only (hostnames, ports, bucket names)"
                }
            ]
        )
        
        # Add suppressions for IAM wildcard permissions (required for functionality)
        NagSuppressions.add_resource_suppressions(
            self.ecs_task_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard permissions required for S3 object access - ECS tasks need to read/write test artifacts with dynamic names",
                    "appliesTo": ["Resource::<TestArtifactsBucket9A9B9F14.Arn>/*"]
                }
            ]
        )
        
        NagSuppressions.add_resource_suppressions(
            self.ecs_task_execution_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard permissions required for CloudWatch Logs and ECR access - ECS tasks need to create log groups/streams with dynamic names and access ECR repositories",
                    "appliesTo": [
                        f"Resource::arn:aws:logs:{self.region}:{self.account}:log-group:/ecs/*",
                        f"Resource::arn:aws:ecr:{self.region}:{self.account}:repository/*",
                        "Resource::*"
                    ]
                }
            ]
        )
        
        # Add suppression for CDK-generated DefaultPolicy
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            "/PerformanceTestingStack/ECSTaskExecutionRole/DefaultPolicy",
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "CDK-generated policy for ECR access - wildcard required for ECR authorization token",
                    "appliesTo": ["Resource::*"]
                }
            ]
        )

    def _create_mcp_server_lambda(self):
        """Create MCP Server Lambda function"""
        
        # Create IAM role for Lambda function
        self.mcp_lambda_role = iam.Role(
            self, "MCPServerLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                "MCPServerPolicy": iam.PolicyDocument(
                    statements=[
                        # Basic Lambda execution
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream", 
                                "logs:PutLogEvents"
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/performance-testing-mcp-server:*"
                            ]
                        ),
                        # Bedrock access for AI (all regions for model availability)
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock:InvokeModel",
                                "bedrock:InvokeModelWithResponseStream"
                            ],
                            resources=[
                                "arn:aws:bedrock:*::foundation-model/*",
                                f"arn:aws:bedrock:*:{self.account}:inference-profile/*",
                                f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0"
                            ]
                        ),
                        # S3 access for test artifacts
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:GetObject",
                                "s3:PutObject", 
                                "s3:DeleteObject",
                                "s3:ListBucket"
                            ],
                            resources=[
                                self.artifacts_bucket.bucket_arn,
                                f"{self.artifacts_bucket.bucket_arn}/*"
                            ]
                        ),
                        # ECS access for JMeter execution (resource-specific actions)
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ecs:RunTask",
                                "ecs:DescribeTasks",
                                "ecs:ListTasks",
                                "ecs:StopTask",
                                "ecs:TagResource"
                            ],
                            resources=[
                                f"arn:aws:ecs:{self.region}:{self.account}:cluster/{self.cluster.cluster_name}",
                                f"arn:aws:ecs:{self.region}:{self.account}:task-definition/{self.jmeter_task_definition.family}:*",
                                f"arn:aws:ecs:{self.region}:{self.account}:task/*"
                            ]
                        ),
                        # ECS DescribeTaskDefinition requires wildcard resource
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ecs:DescribeTaskDefinition"
                            ],
                            resources=["*"]
                        ),
                        # IAM pass role for ECS tasks
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["iam:PassRole"],
                            resources=[
                                self.ecs_task_execution_role.role_arn,
                                self.ecs_task_role.role_arn
                            ]
                        )
                    ]
                )
            }
        )
        
        # Create Lambda function from source
        self.mcp_server_function = lambda_.Function(
            self, "MCPServerFunction",
            function_name="performance-testing-mcp-server",
            runtime=lambda_.Runtime.FROM_IMAGE,
            code=lambda_.Code.from_asset_image(
                "../performance-testing-mcp-server",
                platform=ecr_assets.Platform.LINUX_AMD64
            ),
            handler=lambda_.Handler.FROM_IMAGE,
            role=self.mcp_lambda_role,
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment={
                "S3_BUCKET_NAME": self.artifacts_bucket.bucket_name,
                "ECS_CLUSTER_NAME": self.cluster.cluster_name,
                "JMETER_TASK_DEFINITION": self.jmeter_task_definition.family,
                "BEDROCK_REGION": self.region,
                "BEDROCK_MODEL_ID": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                "ECS_SUBNETS": ",".join([subnet.subnet_id for subnet in self.vpc.private_subnets]),
                "ECS_SECURITY_GROUPS": self.jmeter_security_group.security_group_id,
                "DEPLOYMENT_REGION": self.region,
                "AWS_ACCOUNT_ID": self.account,
                "ECS_EXECUTION_ROLE_ARN": self.ecs_task_execution_role.role_arn,
                "ECS_TASK_ROLE_ARN": self.ecs_task_role.role_arn,
                "INTERNAL_ALB_DNS": self.internal_load_balancer.load_balancer_dns_name
            }
        )
        
        # Create function URL for HTTP access
        self.mcp_function_url = self.mcp_server_function.add_function_url(
            auth_type=lambda_.FunctionUrlAuthType.AWS_IAM,
            cors=lambda_.FunctionUrlCorsOptions(
                allow_credentials=True,
                allowed_headers=["*"],
                allowed_methods=[lambda_.HttpMethod.ALL],
                allowed_origins=["*"]
            )
        )
        
        # Add CDK Nag suppressions for Lambda
        NagSuppressions.add_resource_suppressions(
            self.mcp_lambda_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard permissions required for Lambda functionality - S3 objects, ECS tasks, Bedrock models have dynamic names, and DescribeTaskDefinition requires wildcard resource",
                    "appliesTo": [
                        "Resource::<TestArtifactsBucket9A9B9F14.Arn>/*",
                        "Resource::arn:aws:bedrock:*::foundation-model/*",
                        f"Resource::arn:aws:ecs:{self.region}:{self.account}:task/*",
                        f"Resource::arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/performance-testing-mcp-server:*",
                        f"Resource::arn:aws:ecs:{self.region}:{self.account}:task-definition/PerformanceTestingStackJMeterTaskDefinitionF58D664C:*",
                        f"Resource::arn:aws:bedrock:*:{self.account}:inference-profile/*",
                        "Resource::*"
                    ]
                }
            ]
        )

    def _create_outputs(self):
        """Create CloudFormation outputs"""
        CfnOutput(
            self, "VPCId",
            value=self.vpc.vpc_id,
            description="VPC ID"
        )
        
        CfnOutput(
            self, "ECSClusterName", 
            value=self.cluster.cluster_name,
            description="ECS Cluster Name"
        )
        
        CfnOutput(
            self, "S3BucketName",
            value=self.artifacts_bucket.bucket_name,
            description="S3 Bucket for test artifacts",
            export_name=f"{self.stack_name}-S3BucketName"
        )
        

        
        CfnOutput(
            self, "InternalALBDNSName",
            value=self.internal_load_balancer.load_balancer_dns_name,
            description="Internal Application Load Balancer DNS Name (VPC-only)"
        )
        
        CfnOutput(
            self, "FakeApiRepositoryURI",
            value=self.fake_api_repository.repository_uri,
            description="Fake API ECR Repository URI"
        )
        
        # JMeter repository URI is auto-generated by CDK from_asset
        # Available via CDK metadata if needed
        
        CfnOutput(
            self, "MCPServerFunctionName",
            value=self.mcp_server_function.function_name,
            description="MCP Server Lambda Function Name"
        )
        
        CfnOutput(
            self, "MCPServerFunctionURL",
            value=self.mcp_function_url.url,
            description="MCP Server Function URL for HTTP access"
        )
        
        CfnOutput(
            self, "ServiceDiscoveryNamespaceOutput",
            value=self.namespace.namespace_name,
            description="Service Discovery Namespace for internal communication"
        )
        
        CfnOutput(
            self, "PrivateSubnets",
            value=",".join([subnet.subnet_id for subnet in self.vpc.private_subnets]),
            description="Private subnet IDs for ECS tasks"
        )
        
        CfnOutput(
            self, "JMeterSecurityGroupId",
            value=self.jmeter_security_group.security_group_id,
            description="Security group for JMeter tasks"
        )