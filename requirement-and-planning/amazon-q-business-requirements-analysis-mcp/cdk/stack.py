import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as integrations,
    aws_iam as iam,
    aws_sso as sso,
    aws_ecr as ecr,
    CustomResource,
    Duration,
    RemovalPolicy
)
from constructs import Construct
import json


class AmazonQMcpStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.config = config
        
        # Create IAM roles first
        self.create_iam_roles()
        
        # Create IDC setup
        self.create_idc_setup()
        
        # Create Lambda functions
        self.create_lambda_functions()
        
        # Create API Gateway
        self.create_api_gateway()
        
        # Output important values
        self.create_outputs()

    def create_iam_roles(self):
        """Create IAM roles for the stack"""
        
        # Q Business Chat Role - use CfnRole for exact CloudFormation control
        self.qbiz_chat_role_cfn = iam.CfnRole(
            self, "QBizChatRole",
            role_name=f"{self.stack_name}-qbiz-chat-role-v8",
            assume_role_policy_document={
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "AllowAccountRoot",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": f"arn:aws:iam::{self.account}:root"
                        },
                        "Action": [
                            "sts:AssumeRole",
                            "sts:SetContext"
                        ]
                    }
                ]
            },
            policies=[
                {
                    "policyName": "QBizChatPolicy",
                    "policyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "qbusiness:Chat",
                                    "qbusiness:ChatSync",
                                    "qbusiness:ListMessages",
                                    "qbusiness:ListConversations",
                                    "qbusiness:DeleteConversation",
                                    "qbusiness:PutFeedback",
                                    "qbusiness:GetWebExperience",
                                    "qbusiness:GetApplication",
                                    "qbusiness:ListPlugins",
                                    "qbusiness:GetChatControlsConfiguration"
                                ],
                                "Resource": [
                                    f"arn:aws:qbusiness:{self.region}:{self.account}:application/*"
                                ]
                            }
                        ]
                    }
                }
            ]
        )
        
        # Create a wrapper for the CfnRole to use in other constructs
        self.qbiz_chat_role = iam.Role.from_role_arn(
            self, "QBizChatRoleRef",
            role_arn=self.qbiz_chat_role_cfn.attr_arn
        )
        
        # MCP Lambda Role - exactly matching CloudFormation template
        self.mcp_lambda_role = iam.Role(
            self, "MCPLambdaRole",
            role_name=f"{self.stack_name}-mcp-lambda-role-v8",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ],
            inline_policies={
                "AssumeQBizChatRole": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["sts:AssumeRole", "sts:SetContext"],
                            resources=[f"arn:aws:iam::{self.account}:role/{self.stack_name}-qbiz-chat-role-v8"]
                        )
                    ]
                ),
                "IntegratedAuthPermissions": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["sso-oauth:CreateTokenWithIAM"],
                            resources=["*"]
                        )
                    ]
                )
            }
        )
        
        # IDC Lambda Execution Role
        self.idc_lambda_role = iam.Role(
            self, "IDCLambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ],
            inline_policies={
                "SSOAdminPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "sso:CreateInstance",
                                "sso:DescribeInstance", 
                                "sso:ListInstances",
                                "iam:CreateServiceLinkedRole",
                                "identitystore:CreateGroup",
                                "identitystore:CreateGroupMembership",
                                "identitystore:CreateUser",
                                "identitystore:ListGroups",
                                "identitystore:ListUsers",
                                "sso:PutApplicationAssignmentConfiguration",
                                "sso:PutApplicationAuthenticationMethod",
                                "sso:DeleteApplicationAuthenticationMethod",
                                "sso:PutApplicationAccessScope",
                                "sso:DeleteApplicationAccessScope",
                                "sso:CreateTrustedTokenIssuer",
                                "sso:DeleteTrustedTokenIssuer",
                                "sso:PutApplicationGrant",
                                "sso:DeleteApplicationGrant"
                            ],
                            resources=["*"]
                        )
                    ]
                )
            }
        )
        


    def create_idc_setup(self):
        """Create Identity Center setup"""
        
        # IDC Application
        self.idc_app = sso.CfnApplication(
            self, "IDCApiApp",
            application_provider_arn="arn:aws:sso::aws:applicationProvider/custom",
            instance_arn=f"arn:aws:sso:::instance/{self.config.get('IDC_INSTANCE_ID')}",
            name=f"{self.stack_name}-icode-cognito-mcp-auth-v8"
        )
        
        # IDC Configuration Lambda
        with open('idc_config_lambda.py', 'r') as f:
            idc_config_code = f.read()
        
        self.idc_config_lambda = _lambda.Function(
            self, "IDCConfigLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline(idc_config_code),
            role=self.idc_lambda_role,
            timeout=Duration.minutes(5),
            description="Configure IDC Application"
        )
        
        # Custom resources for IDC configuration
        self.create_idc_custom_resources()

    def create_idc_custom_resources(self):
        """Create custom resources for IDC configuration"""
        
        # Access Scopes
        CustomResource(
            self, "IDCAppScopes",
            service_token=self.idc_config_lambda.function_arn,
            properties={
                "ResourceType": "access-scope",
                "IDCApplicationArn": self.idc_app.attr_application_arn,
                "AccessScopes": [
                    "qbusiness:conversations:access",
                    "qbusiness:messages:access"
                ]
            }
        )
        
        # Assignment Configuration
        CustomResource(
            self, "IDCAppAssignmentConfig", 
            service_token=self.idc_config_lambda.function_arn,
            properties={
                "ResourceType": "assignment-config",
                "IDCApplicationArn": self.idc_app.attr_application_arn,
                "AssignmentRequired": "no"
            }
        )
        
        # Trusted Token Issuer
        self.tti_resource = CustomResource(
            self, "IDCTrustedTokenIssuer",
            service_token=self.idc_config_lambda.function_arn,
            properties={
                "ResourceType": "trusted-token-issuer",
                "Name": f"{self.stack_name}-icode-cognito-tti-v8",
                "InstanceArn": f"arn:aws:sso:::instance/{self.config.get('IDC_INSTANCE_ID')}",
                "TTIConfiguration": {
                    "OidcJwtConfiguration": {
                        "IssuerUrl": f"https://cognito-idp.{self.region}.amazonaws.com/{self.config.get('EXISTING_COGNITO_USER_POOL_ID')}",
                        "ClaimAttributePath": "email",
                        "IdentityStoreAttributePath": "emails.value",
                        "JwksRetrievalOption": "OPEN_ID_DISCOVERY"
                    }
                }
            }
        )
        
        # Application Grant
        CustomResource(
            self, "IDCAppGrant",
            service_token=self.idc_config_lambda.function_arn,
            properties={
                "ResourceType": "application-grant",
                "IDCApplicationArn": self.idc_app.attr_application_arn,
                "GrantType": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "Grant": {
                    "JwtBearer": {
                        "AuthorizedTokenIssuers": [
                            {
                                "TrustedTokenIssuerArn": self.tti_resource.get_att_string("TrustedTokenIssuerArn"),
                                "AuthorizedAudiences": [self.config.get('EXISTING_COGNITO_CLIENT_ID')]
                            }
                        ]
                    }
                }
            }
        )
        
        # Authentication Method
        CustomResource(
            self, "IDCAppAuthMethod",
            service_token=self.idc_config_lambda.function_arn,
            properties={
                "ResourceType": "app-auth-method",
                "IDCApplicationArn": self.idc_app.attr_application_arn,
                "AuthenticationMethod": {
                    "Iam": {
                        "ActorPolicy": {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Action": "sso-oauth:CreateTokenWithIAM",
                                    "Principal": {"AWS": self.qbiz_chat_role.role_arn},
                                    "Resource": self.idc_app.attr_application_arn
                                }
                            ]
                        }
                    }
                }
            }
        )

    def create_lambda_functions(self):
        """Create Lambda functions"""
        
        # MCP Lambda Function
        self.mcp_lambda = _lambda.Function(
            self, "MCPLambda",
            function_name=f"{self.stack_name}-mcp-lambda-v8",
            runtime=_lambda.Runtime.FROM_IMAGE,
            handler=_lambda.Handler.FROM_IMAGE,
            code=_lambda.Code.from_ecr_image(
                repository=ecr.Repository.from_repository_name(
                    self, "ECRRepo", 
                    self.config.get('REPOSITORY_NAME', 'amazon-q-mcp-server')
                ),
                tag_or_digest=self.config.get('IMAGE_TAG', 'latest')
            ),
            role=self.mcp_lambda_role,
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "Q_BUSINESS_APPLICATION_ID": self.config.get('Q_BUSINESS_APP_ID'),
                "QBIZ_ROLE_ARN": self.qbiz_chat_role.role_arn,
                "IDC_APP_CLIENT_ID": self.idc_app.attr_application_arn,
                "ALLOWED_CORS_ORIGINS": self.config.get('ALLOWED_CORS_ORIGINS', 'https://luvvfzwt.chat.qbusiness.us-east-1.on.aws'),
                "MCP_PROTOCOL_VERSION": "2024-11-05",
                "MCP_SERVER_NAME": "amazon-q-mcp-server",
                "MCP_SERVER_VERSION": "2.0.0",
                "MCP_DEFAULT_USERNAME": "mateo_jackson@example.com",
                # Security: IAM auth enabled by default
                "ENABLE_IAM_AUTH": "true",
                "LOG_LEVEL": "INFO",
                # Security: Optional IP restrictions (uncomment and configure if needed)
                # "ALLOWED_SOURCE_IPS": "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
            }
        )
        


    def create_api_gateway(self):
        """Create API Gateway"""
        
        # HTTP API with IAM authorization and security hardening
        self.api = apigw.HttpApi(
            self, "MCPApiGateway",
            api_name=f"{self.stack_name}-mcp-api-v8",
            description="MCP API with IAM authentication handled in Lambda",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_credentials=True,
                allow_headers=["Content-Type", "Authorization", "X-Amz-Date", "X-Amz-Security-Token", "X-Amz-User-Agent"],
                allow_methods=[apigw.CorsHttpMethod.POST, apigw.CorsHttpMethod.GET, apigw.CorsHttpMethod.OPTIONS],
                # Security: Explicit origins only, no wildcards
                allow_origins=self.config.get('ALLOWED_CORS_ORIGINS', 'https://luvvfzwt.chat.qbusiness.us-east-1.on.aws').split(','),
                max_age=Duration.hours(1)  # Reduced from 1 day for better security
            ),
            # Security: Disable default endpoint (forces custom domain usage if needed)
            disable_execute_api_endpoint=False  # Set to True if using custom domain
        )
        
        # Lambda Integration (no authorizer needed - IAM auth is handled in the lambda)
        integration = integrations.HttpLambdaIntegration(
            "MCPLambdaIntegration",
            self.mcp_lambda
        )
        
        # Routes - using IAM authorization at the API Gateway level
        self.api.add_routes(
            path="/{proxy+}",
            methods=[apigw.HttpMethod.ANY],
            integration=integration
        )

    def create_outputs(self):
        """Create stack outputs"""
        
        cdk.CfnOutput(
            self, "ApiEndpoint",
            value=self.api.url,
            description="MCP API Gateway endpoint URL"
        )
        
        cdk.CfnOutput(
            self, "MCPLambdaArn",
            value=self.mcp_lambda.function_arn,
            description="MCP Lambda function ARN"
        )
        
        cdk.CfnOutput(
            self, "QBizRoleArn", 
            value=self.qbiz_chat_role.role_arn,
            description="Q Business chat role ARN"
        )
        
        cdk.CfnOutput(
            self, "IDCApplicationArn",
            value=self.idc_app.attr_application_arn,
            description="Identity Center application ARN"
        )