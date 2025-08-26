#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stack import AmazonQMcpStack

app = cdk.App()

# Load configuration from deployment_config.env
config = {}
try:
    with open('../deployment_config.env', 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.strip().split('=', 1)
                if key.startswith('export '):
                    key = key[7:]  # Remove 'export ' prefix
                config[key] = value
except FileNotFoundError:
    print("Warning: deployment_config.env not found, using defaults")

# Create the stack
AmazonQMcpStack(
    app, 
    config.get('STACK_NAME', 'mcp-existing-cognito-v9'),
    env=cdk.Environment(
        account=config.get('ACCOUNT_ID', cdk.Aws.ACCOUNT_ID),
        region=config.get('REGION', 'us-east-1')
    ),
    config=config
)

app.synth()