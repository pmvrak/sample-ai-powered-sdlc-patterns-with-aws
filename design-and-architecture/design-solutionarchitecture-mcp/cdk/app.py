#!/usr/bin/env python3

import os
import boto3

import aws_cdk as cdk
import cdk_nag

from stack.stack import AWSAgentStack

# Automatically detect AWS account ID and region
def get_aws_account_id():
    """Get the current AWS account ID dynamically"""
    try:
        sts_client = boto3.client('sts')
        return sts_client.get_caller_identity()['Account']
    except Exception as e:
        print(f"Warning: Could not auto-detect AWS account ID: {e}")
        print("Please ensure AWS credentials are configured (aws configure)")
        return None

def get_aws_region():
    """Get the AWS region from environment or AWS config"""
    # Try environment variable first
    region = os.getenv('CDK_DEFAULT_REGION')
    if region:
        return region
    
    # Try AWS config
    try:
        session = boto3.Session()
        return session.region_name
    except:
        # Default to us-east-1 for Bedrock compatibility
        return 'us-east-1'

# Get account and region dynamically
account_id = get_aws_account_id()
region = get_aws_region()

if not account_id:
    print("❌ Error: Could not determine AWS account ID")
    print("Please run: aws configure")
    exit(1)

print(f"🚀 Deploying to Account: {account_id}, Region: {region}")

app = cdk.App()
AWSAgentStack(app, "MCPArchitectureServer",
    env=cdk.Environment(account=account_id, region=region),
)

cdk.Aspects.of(app).add(cdk_nag.AwsSolutionsChecks(verbose=True))

app.synth()
