import os
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    Size,
    aws_lambda as _lambda,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    aws_s3 as s3,
    aws_bedrock as bedrock,
    aws_cloudtrail as cloudtrail,
)
from constructs import Construct
from aws_cdk.aws_iam import PolicyStatement, AnyPrincipal, Effect, ServicePrincipal
from cdk_nag import NagSuppressions


class AWSAgentStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        region = self.region
        account = self.account

        # 1) Create logging bucket for S3 access logs
        logging_bucket = s3.Bucket(
            self, "MCPServerAccessLogsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True
        )
        
        # Main assets bucket with server access logging enabled
        assets_bucket = s3.Bucket(
            self, "MCPServerAssetsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            server_access_logs_bucket=logging_bucket,
            server_access_logs_prefix="assets-bucket-logs/"
        )
        
        # S3 bucket is private to your account only

        # Deploy MCP Server as a containerized Lambda function
        # This implements the Model Context Protocol specification with all functionality integrated
        mcp_server_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "mcp-server")
        
        mcp_image_asset = ecr_assets.DockerImageAsset(
            self, "MCPServerImageAsset",
            directory=mcp_server_dir,
            platform=ecr_assets.Platform.LINUX_AMD64,
            build_args={
                "BUILDPLATFORM": "linux/amd64",
                "TARGETPLATFORM": "linux/amd64"
            },
            build_secrets={}
        )
        
        # Create MCP Server Lambda function with comprehensive role
        mcp_lambda_role = iam.Role(
            self, "MCPArchitectureServerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                "CloudWatchLogsPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            resources=[
                                f"arn:aws:logs:{region}:{account}:log-group:/aws/lambda/*"
                            ]
                        )
                    ]
                )
            }
        )
        
        # Grant permissions to invoke Bedrock models and cross-region inference profiles
        mcp_lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock-runtime:InvokeModel"
                ],
                resources=[
                    # Foundation models for Haiku and Titan (fallback)
                    f"arn:aws:bedrock:{region}::foundation-model/*",
                    "arn:aws:bedrock:us-west-2::foundation-model/*",
                    "arn:aws:bedrock:us-east-1::foundation-model/*",
                    "arn:aws:bedrock:us-east-2::foundation-model/*",
                    # Cross-region inference profile for Claude 3.7 Sonnet
                    f"arn:aws:bedrock:{region}:{account}:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0"
                ]
            )
        )
        
        # Add suppressions for the MCP server role
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/MCPArchitectureServerRole/Resource",
            suppressions=[
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Lambda needs access to create its own log groups/streams with dynamic names",
                    "appliesTo": [f"Resource::arn:aws:logs:{region}:{account}:log-group:/aws/lambda/*"]
                }
            ]
        )
        
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/MCPArchitectureServerRole/DefaultPolicy/Resource",
            suppressions=[
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Bedrock requires access to foundation models and specific inference profiles",
                    "appliesTo": [
                        f"Resource::arn:aws:bedrock:{region}::foundation-model/*",
                        "Resource::arn:aws:bedrock:us-west-2::foundation-model/*",
                        "Resource::arn:aws:bedrock:us-east-1::foundation-model/*",
                        "Resource::arn:aws:bedrock:us-east-2::foundation-model/*"
                    ]
                }
            ]
        )
        
        # Create the MCP Server Lambda with increased memory and timeout for handling all functionality
        mcp_lambda = _lambda.DockerImageFunction(
            self, "MCPArchitectureServerFunction",
            code=_lambda.DockerImageCode.from_image_asset(mcp_server_dir),
            memory_size=10240,  # Increased memory to handle diagram generation
            timeout=Duration.seconds(600),  # Increased timeout for complex operations
            ephemeral_storage_size=Size.mebibytes(10240),  # Added ephemeral storage for diagram generation
            environment={
                "BEDROCK_REGION": region,
                "AWS_ACCOUNT_ID": account,
                "S3_BUCKET_NAME": assets_bucket.bucket_name,
                "VECTORSTORE_PATH": "/var/task/local_index",
                "BEDROCK_MODEL_ID": "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
            },
            role=mcp_lambda_role
        )
        
        # Grant permissions to access S3 directly
        assets_bucket.grant_read_write(mcp_lambda)
        
        # Add suppressions for S3 permissions
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/MCPArchitectureServerRole/DefaultPolicy/Resource",
            suppressions=[
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "S3 operations require wildcard permissions for object operations",
                    "appliesTo": [
                        "Action::s3:Abort*",
                        "Action::s3:DeleteObject*",
                        "Action::s3:GetBucket*",
                        "Action::s3:GetObject*",
                        "Action::s3:List*",
                        f"Resource::<MCPServerAssetsBucketA7A0E7C6.Arn>/*"
                    ]
                }
            ]
        )
        
        # Create Lambda Function URL with strict IAM authentication - NO PUBLIC ACCESS
        mcp_function_url = mcp_lambda.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.AWS_IAM,  # Requires AWS IAM authentication
            cors=_lambda.FunctionUrlCorsOptions(
                allowed_origins=["https://console.aws.amazon.com"],  # Restrict CORS origins
                allowed_methods=[_lambda.HttpMethod.POST, _lambda.HttpMethod.GET],  # Only needed methods
                allowed_headers=["Content-Type", "Authorization", "X-Amz-Date", "X-Amz-Security-Token"],
                max_age=Duration.hours(1)
            )
        )
        
        # Add resource-based policy to Lambda function - Only allow your account
        mcp_lambda.add_permission(
            "AllowOwnerAccountOnly",
            principal=iam.AccountPrincipal(self.account),
            action="lambda:InvokeFunctionUrl"
        )
        
        # SECURITY: The Lambda Function URL with AWS_IAM auth type already provides security
        # Combined with the resource-based permissions above, this creates a secure setup
        # Only the specified accounts with valid IAM credentials can access the function
        
        # COMPLIANCE: Add CloudTrail for security monitoring (required by security policy)
        cloudtrail_bucket = s3.Bucket(
            self, "MCPServerCloudTrailBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            server_access_logs_bucket=logging_bucket,
            server_access_logs_prefix="cloudtrail-access-logs/"
        )
        
        # Create CloudTrail for audit compliance
        trail = cloudtrail.Trail(
            self, "MCPServerAuditTrail",
            bucket=cloudtrail_bucket,
            include_global_service_events=True,
            is_multi_region_trail=True,
            enable_file_validation=True,
            send_to_cloud_watch_logs=True
        )

        # Outputs
        CfnOutput(self, "AssetsBucket", value=assets_bucket.bucket_name)
        
        # MCP Server outputs - SECURE ACCESS ONLY
        CfnOutput(
            self, "MCPServerURL", 
            value=mcp_function_url.url,
            description="🔒 SECURE MCP Server URL - Requires AWS IAM authentication, NO public access"
        )
        CfnOutput(
            self, "MCPServerLambdaArn", 
            value=mcp_lambda.function_arn,
            description="MCP Server Lambda Function ARN"
        )
        
        # Security information
        CfnOutput(
            self, "SecurityInfo",
            value=f"SECURE ACCESS: Only account {self.account} allowed. IAM authentication required.",
            description="🛡️ Security: No public access, IAM authentication mandatory"
        )
        
        CfnOutput(
            self, "AuthenticationMethod",
            value="AWS Signature Version 4 (SigV4) required - use awscurl or curl --aws-sigv4",
            description="🔐 Authentication: AWS SigV4 with service=lambda"
        )
        
        CfnOutput(
            self, "TestCommand",
            value=f"awscurl --service lambda --region {region} {mcp_function_url.url}",
            description="🧪 Test command using awscurl with proper SigV4 authentication"
        )