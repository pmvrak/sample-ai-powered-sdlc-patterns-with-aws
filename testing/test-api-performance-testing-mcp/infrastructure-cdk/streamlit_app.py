#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stacks.performance_testing_stack import PerformanceTestingStack
from stacks.streamlit_stack import StreamlitStack

app = cdk.App()

# Get environment configuration
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION', 'us-west-2')
)

# Get parameters from environment variables (set by deploy script)
mcp_function_url = os.getenv('MCP_FUNCTION_URL')
artifact_bucket = os.getenv('ARTIFACT_BUCKET')
vpc_id = os.getenv('VPC_ID')

print(f"🔧 CDK App - MCP_FUNCTION_URL: {mcp_function_url}")
print(f"🔧 CDK App - ARTIFACT_BUCKET: {artifact_bucket}")
print(f"🔧 CDK App - VPC_ID: {vpc_id}")

# Streamlit application stack (references existing performance stack resources)
streamlit_stack = StreamlitStack(
    app,
    "StreamlitStack", 
    mcp_function_url=mcp_function_url,
    artifact_bucket=artifact_bucket,
    vpc_id=vpc_id,
    env=env,
    description="Streamlit MCP demo application with secure ALB"
)

# Add tags to all resources
cdk.Tags.of(app).add("Project", "PerformanceTesting")
cdk.Tags.of(app).add("Environment", "Development") 
cdk.Tags.of(app).add("ManagedBy", "CDK")

app.synth()