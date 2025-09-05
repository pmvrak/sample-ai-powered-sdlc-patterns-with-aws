#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stacks.performance_testing_stack import PerformanceTestingStack

app = cdk.App()

# Get environment configuration
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION', 'us-west-2')
)

# Main performance testing stack
performance_stack = PerformanceTestingStack(
    app, 
    "PerformanceTestingStack",
    env=env,
    description="Performance testing infrastructure with fake API and JMeter runner"
)

# Add tags to all resources
cdk.Tags.of(app).add("Project", "PerformanceTesting")
cdk.Tags.of(app).add("Environment", "Development") 
cdk.Tags.of(app).add("ManagedBy", "CDK")

app.synth()