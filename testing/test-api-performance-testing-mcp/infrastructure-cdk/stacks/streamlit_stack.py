from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_logs as logs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ecr as ecr,
    aws_ecr_assets as ecr_assets,
    RemovalPolicy,
    Duration,
    CfnOutput,
)
from constructs import Construct
from cdk_nag import NagSuppressions


class StreamlitStack(Stack):
    """
    CDK Stack for Streamlit MCP Demo Application
    
    Separate stack for the Streamlit application with:
    - ECS Fargate service
    - Internet-facing ALB with IP restrictions
    - ECR repository
    - Proper security groups
    """

    def __init__(self, scope: Construct, construct_id: str, 
                 mcp_function_url: str = None,
                 artifact_bucket: str = None,
                 vpc_id: str = None,
                 cluster_name: str = None,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Store parameters
        self.mcp_function_url = mcp_function_url
        self.artifact_bucket = artifact_bucket
        
        # Import existing VPC from PerformanceTestingStack
        self.vpc = ec2.Vpc.from_lookup(
            self, "ImportedVPC",
            vpc_id=vpc_id
        ) if vpc_id else ec2.Vpc.from_lookup(
            self, "ImportedVPC", 
            is_default=True
        )
        
        # Create separate ECS cluster for Streamlit (but use shared VPC)
        self.cluster = ecs.Cluster(
            self, "StreamlitCluster",
            vpc=self.vpc,
            cluster_name="streamlit-cluster",
            container_insights=True
        )
        
        # Create Streamlit-specific resources
        self._create_streamlit_repository()
        self._create_streamlit_iam_roles()
        self._create_streamlit_security_groups()
        self._create_streamlit_load_balancer()
        self._create_streamlit_service()
        self._create_outputs()

    def _create_streamlit_repository(self):
        """Create ECR repository for Streamlit"""
        self.streamlit_repository = ecr.Repository(
            self, "StreamlitRepository",
            repository_name="streamlit-mcp-demo",
            removal_policy=RemovalPolicy.DESTROY
        )

    def _create_streamlit_iam_roles(self):
        """Create IAM roles for Streamlit ECS tasks"""
        
        # Create ECS task execution role with custom policy (CDK Nag compliant)
        self.ecs_task_execution_role = iam.Role(
            self, "StreamlitECSTaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            inline_policies={
                "StreamlitTaskExecutionPolicy": iam.PolicyDocument(
                    statements=[
                        # ECR permissions for pulling Streamlit image
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ecr:GetAuthorizationToken",
                                "ecr:BatchCheckLayerAvailability", 
                                "ecr:GetDownloadUrlForLayer",
                                "ecr:BatchGetImage"
                            ],
                            resources=[
                                f"arn:aws:ecr:{self.region}:{self.account}:repository/streamlit-mcp-demo"
                            ]
                        ),
                        # CloudWatch Logs permissions
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/ecs/streamlit-mcp-demo:*"
                            ]
                        )
                    ]
                )
            }
        )
        
        # Add CDK Nag suppressions for ECS task execution role
        NagSuppressions.add_resource_suppressions(
            self.ecs_task_execution_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "CloudWatch Logs wildcard (*) is required for ECS task execution role to create and write to log streams with dynamic names. This is a standard AWS pattern for ECS logging.",
                    "appliesTo": [f"Resource::arn:aws:logs:{self.region}:{self.account}:log-group:/ecs/streamlit-mcp-demo:*"]
                }
            ]
        )
        
        # Grant ECR access for Streamlit repository
        self.streamlit_repository.grant_pull(self.ecs_task_execution_role)
        
        # Add CDK Nag suppression for ECR repository grant (CDK-generated policy)
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            "/StreamlitStack/StreamlitECSTaskExecutionRole/DefaultPolicy",
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "ECR repository grant_pull() method generates wildcard permissions for ECR authorization token and repository access. This is AWS CDK standard behavior for ECR access patterns.",
                    "appliesTo": ["Resource::*"]
                }
            ]
        )
        
        # Create CloudWatch log group for Streamlit (needed for task execution role)
        self.streamlit_log_group = logs.LogGroup(
            self, "StreamlitLogGroup",
            log_group_name="/ecs/streamlit-mcp-demo",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Grant CloudWatch logs access
        self.streamlit_log_group.grant_write(self.ecs_task_execution_role)
        
        # Create ECS task role with S3 and Lambda permissions
        self.ecs_task_role = iam.Role(
            self, "StreamlitECSTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            inline_policies={
                "StreamlitAccessPolicy": iam.PolicyDocument(
                    statements=[
                        # S3 permissions for accessing performance testing artifacts
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:ListBucket",
                                "s3:GetObject"
                            ],
                            resources=[
                                f"arn:aws:s3:::performance-testing-{self.account}-{self.region}",
                                f"arn:aws:s3:::performance-testing-{self.account}-{self.region}/*"
                            ]
                        ),
                        # Lambda permissions for invoking MCP function
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "lambda:InvokeFunction",
                                "lambda:InvokeFunctionUrl"
                            ],
                            resources=[
                                f"arn:aws:lambda:{self.region}:{self.account}:function:*"
                            ]
                        )
                    ]
                )
            }
        )
        
        # Add CDK Nag suppressions for ECS task role
        NagSuppressions.add_resource_suppressions(
            self.ecs_task_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "S3 bucket wildcard (/*) is required to access all objects within the performance testing artifacts bucket. This follows AWS best practice for S3 object access patterns.",
                    "appliesTo": [f"Resource::arn:aws:s3:::performance-testing-{self.account}-{self.region}/*"]
                },
                {
                    "id": "AwsSolutions-IAM5", 
                    "reason": "Lambda function wildcard (*) is required because the Streamlit app needs to invoke dynamically created MCP Lambda functions. Function names are not known at deployment time and follow the pattern of MCP server implementations.",
                    "appliesTo": [f"Resource::arn:aws:lambda:{self.region}:{self.account}:function:*"]
                }
            ]
        )

    def _create_streamlit_security_groups(self):
        """Create security groups for Streamlit ALB and ECS tasks"""
        
        # Create security group for Streamlit ALB (IP-restricted)
        self.streamlit_alb_security_group = ec2.SecurityGroup(
            self, "StreamlitALBSecurityGroup",
            vpc=self.vpc,
            description="Security group for Streamlit ALB (IP-restricted)",
            allow_all_outbound=True,
            disable_inline_rules=True  # Prevent CDK from adding automatic rules
        )
        
        # Add ingress rule restricted to your IP address
        streamlit_alb_ingress = ec2.CfnSecurityGroupIngress(
            self, "StreamlitALBIngressRule",
            group_id=self.streamlit_alb_security_group.security_group_id,
            ip_protocol="tcp",
            from_port=80,
            to_port=80,
            cidr_ip="<youripaddress>",  # Restricted to your current IP
            description="HTTP access for Streamlit ALB - restricted to specific IP"
        )
        
        # Add CDK Nag suppression for IP-restricted security group
        NagSuppressions.add_resource_suppressions(
            self.streamlit_alb_security_group,
            [
                {
                    "id": "AwsSolutions-EC23",
                    "reason": "Security group is configured with IP-restricted ingress for enhanced security. Access is limited to a single trusted IP address."
                }
            ]
        )
        
        # Create security group for Streamlit ECS tasks
        self.streamlit_ecs_security_group = ec2.SecurityGroup(
            self, "StreamlitECSSecurityGroup",
            vpc=self.vpc,
            description="Security group for Streamlit ECS tasks",
            allow_all_outbound=True  # Needs internet access to call Lambda Function URL
        )
        
        # Allow ALB to reach ECS tasks
        self.streamlit_ecs_security_group.add_ingress_rule(
            peer=ec2.Peer.security_group_id(self.streamlit_alb_security_group.security_group_id),
            connection=ec2.Port.tcp(8501),
            description="HTTP traffic from Streamlit ALB"
        )

    def _create_streamlit_load_balancer(self):
        """Create Internet-facing ALB for Streamlit - handled in _create_streamlit_service"""
        pass

    def _create_streamlit_service(self):
        """Create Streamlit ECS service"""
        
        # Create task definition
        self.streamlit_task_definition = ecs.FargateTaskDefinition(
            self, "StreamlitTaskDefinition",
            memory_limit_mib=2048,
            cpu=1024,
            execution_role=self.ecs_task_execution_role,
            task_role=self.ecs_task_role
        )
        
        # Add container with Docker image built from source
        self.streamlit_container = self.streamlit_task_definition.add_container(
            "StreamlitContainer",
            image=ecs.ContainerImage.from_asset(
                "../streamlit-mcp-demo",
                platform=ecr_assets.Platform.LINUX_AMD64
            ),
            port_mappings=[
                ecs.PortMapping(container_port=8501, protocol=ecs.Protocol.TCP)
            ],
            environment={
                "AWS_DEFAULT_REGION": self.region,
                "AWS_REGION": self.region,
                "MCP_FUNCTION_URL": self.mcp_function_url or "https://example.lambda-url.us-west-2.on.aws/",
                "ARTIFACT_BUCKET": self.artifact_bucket or "performance-testing-bucket-name",
                "DEMO_MODE": "false"
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="streamlit",
                log_group=self.streamlit_log_group
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8501/_stcore/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60)
            )
        )
        
        # Add CDK Nag suppression for environment variables (non-sensitive config)
        NagSuppressions.add_resource_suppressions(
            self.streamlit_task_definition,
            [
                {
                    "id": "AwsSolutions-ECS2",
                    "reason": "Environment variables contain non-sensitive configuration only (AWS region, function URLs, bucket names)"
                }
            ]
        )
        
        # Create ECS service using high-level construct
        self.streamlit_service = ecs.FargateService(
            self, "StreamlitService",
            cluster=self.cluster,
            task_definition=self.streamlit_task_definition,
            desired_count=1,
            service_name="streamlit-mcp-demo",
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[self.streamlit_ecs_security_group]
        )
        
        # Create high-level target group and attach to service
        self.streamlit_target_group_hl = elbv2.ApplicationTargetGroup(
            self, "StreamlitTargetGroupHL",
            vpc=self.vpc,
            port=8501,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            target_group_name="streamlit-mcp-tg",  # Explicit name for stability
            health_check=elbv2.HealthCheck(
                path="/",
                protocol=elbv2.Protocol.HTTP,
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3
            ),
            targets=[self.streamlit_service]
        )
        
        # Create high-level ALB and listener with retention policy
        self.streamlit_alb_hl = elbv2.ApplicationLoadBalancer(
            self, "StreamlitALBHL",
            vpc=self.vpc,
            internet_facing=True,
            security_group=self.streamlit_alb_security_group,
            load_balancer_name="streamlit-mcp-demo-alb",
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            deletion_protection=True  # Prevent accidental deletion
        )
        
        # Add listener to ALB
        self.streamlit_listener_hl = self.streamlit_alb_hl.add_listener(
            "StreamlitListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[self.streamlit_target_group_hl]
        )

    def _create_outputs(self):
        """Create CloudFormation outputs"""
        CfnOutput(
            self, "StreamlitVPCId",
            value=self.vpc.vpc_id,
            description="Streamlit VPC ID (shared with PerformanceTestingStack)"
        )
        
        CfnOutput(
            self, "StreamlitClusterName",
            value=self.cluster.cluster_name,
            description="Streamlit ECS Cluster Name (separate cluster, shared VPC)"
        )
        
        CfnOutput(
            self, "StreamlitRepositoryURI",
            value=self.streamlit_repository.repository_uri,
            description="Streamlit ECR Repository URI"
        )
        
        CfnOutput(
            self, "StreamlitALBDNSName",
            value=self.streamlit_alb_hl.load_balancer_dns_name,
            description="Streamlit Application Load Balancer DNS Name"
        )
        
        CfnOutput(
            self, "StreamlitURL",
            value=f"http://{self.streamlit_alb_hl.load_balancer_dns_name}",
            description="Streamlit Application URL"
        )
        
        CfnOutput(
            self, "ArchitectureNote",
            value="Streamlit makes HTTP calls to Lambda Function URL - no VPC dependency needed",
            description="Architecture Design Note"
        )