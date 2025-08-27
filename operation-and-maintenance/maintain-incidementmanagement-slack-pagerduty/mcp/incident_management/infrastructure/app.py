#!/usr/bin/env python3
"""
CDK App for Incident Management System Infrastructure

This app creates the complete infrastructure for the intelligent incident management system
across multiple environments (dev, staging, prod) with proper resource isolation and
blue-green deployment capabilities.
"""

import os
import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks, NagSuppressions
from simple_ecs_stack import SimpleIncidentManagementECSStack


def get_environment_config():
    """Get configuration for dev-only deployment"""
    env_name = "dev"  # Always dev for this simplified deployment
    account_id = os.getenv("CDK_DEFAULT_ACCOUNT", os.getenv("AWS_ACCOUNT_ID"))
    region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")
    
    if not account_id:
        raise ValueError("AWS_ACCOUNT_ID or CDK_DEFAULT_ACCOUNT must be set")
    
    return {
        "environment": env_name,
        "account": account_id,
        "region": region
    }


def main():
    """Main CDK app entry point"""
    app = cdk.App()
    
    # Get environment configuration
    config = get_environment_config()
    env = cdk.Environment(
        account=config["account"],
        region=config["region"]
    )
    
    environment = config["environment"]  # Always "dev"
    
    # Create ECS-based deployment (dev-only)
    incident_stack = SimpleIncidentManagementECSStack(
        app, 
        f"SimpleIncidentManagementECSStack-{environment}",
        environment=environment,
        env=env,
        description=f"Incident Management System (ECS) - Development Environment",
        tags={
            "Project": "IncidentManagement",
            "Environment": environment,
            "Owner": "DevOps",
            "CostCenter": "Engineering",
            "DeploymentType": "ECS"
        }
    )
    
    # Output key information
    cdk.CfnOutput(
        incident_stack,
        "StackInfo",
        value=f"Incident Management System deployed in development environment",
        description="Deployment information"
    )
    
    # Output API endpoint for ECS deployment
    cdk.CfnOutput(
        incident_stack,
        "ApplicationURL",
        value=f"http://{incident_stack.fargate_service.load_balancer.load_balancer_dns_name}",
        description="Application Load Balancer URL for ECS deployment"
    )
    
    cdk.CfnOutput(
        incident_stack,
        "DashboardURL",
        value=f"https://{config['region']}.console.aws.amazon.com/cloudwatch/home?region={config['region']}#dashboards:name=IncidentManagement-{environment}",
        description="CloudWatch Dashboard URL"
    )
    
    # Add CDK Nag checks
    cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))
    
    # Add global suppressions for common acceptable patterns
    _add_global_nag_suppressions(incident_stack)
    
    app.synth()


def _add_global_nag_suppressions(stack):
    """Add global CDK Nag suppressions for acceptable patterns"""
    
    # Suppress common ECS/ALB patterns that are acceptable for this use case
    NagSuppressions.add_stack_suppressions(
        stack,
        [

            {
                "id": "AwsSolutions-EC23",
                "reason": "Security group allows inbound HTTP traffic for ALB - acceptable for web application"
            },
            {
                "id": "AwsSolutions-ECS2",
                "reason": "Environment variables contain non-sensitive configuration data"
            },
            {
                "id": "AwsSolutions-IAM4",
                "reason": "AWS managed policies are acceptable for ECS task execution role"
            },
            {
                "id": "AwsSolutions-IAM5",
                "reason": "Wildcard permissions needed for Bedrock model access across regions"
            },
            {
                "id": "AwsSolutions-L1",
                "reason": "Using latest runtime versions as specified in CDK context"
            },
            {
                "id": "AwsSolutions-COG4",
                "reason": "No Cognito user pool required - using internal authentication"
            },
            {
                "id": "AwsSolutions-APIG1",
                "reason": "No API Gateway logging required for internal tool"
            },
            {
                "id": "AwsSolutions-APIG2",
                "reason": "Request validation handled at application level"
            },
            {
                "id": "AwsSolutions-APIG3",
                "reason": "WAF not required for internal development tool"
            },
            {
                "id": "AwsSolutions-APIG4",
                "reason": "API Gateway authorization handled at application level"
            },
            {
                "id": "AwsSolutions-APIG6",
                "reason": "CloudWatch logging not required for internal tool"
            },
            {
                "id": "AwsSolutions-CFR1",
                "reason": "CloudFront not required for internal ECS application"
            },
            {
                "id": "AwsSolutions-CFR2",
                "reason": "CloudFront not required for internal ECS application"
            },
            {
                "id": "AwsSolutions-CFR3",
                "reason": "CloudFront not required for internal ECS application"
            },
            {
                "id": "AwsSolutions-CFR4",
                "reason": "CloudFront not required for internal ECS application"
            }
        ]
    )


if __name__ == "__main__":
    main()