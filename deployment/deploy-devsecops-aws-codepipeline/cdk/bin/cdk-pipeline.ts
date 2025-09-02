#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { CdkPipelineStack } from '../lib/stacks/cdk-pipeline-stack';
import { ApplicationStack } from '../lib/stacks/application-stack';

const app = new cdk.App();

// Define common environment
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

// Create the application stack
new ApplicationStack(app, 'MyApplicationStack', {
  env
});

// Create the pipeline stack
new CdkPipelineStack(app, 'CdkPipelineStack', {
  env
  // You can add additional props here if needed
});

// Add tags to all stacks
cdk.Tags.of(app).add('Environment', 'Production');
cdk.Tags.of(app).add('Project', 'iCode');

app.synth();
