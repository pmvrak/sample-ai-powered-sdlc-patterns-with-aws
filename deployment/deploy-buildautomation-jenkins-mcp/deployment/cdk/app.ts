#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { JenkinsMcpServerStack } from './lib/jenkins-mcp-server-stack';
import { JenkinsMcpOAuthStack } from './lib/jenkins-mcp-oauth-stack';

const app = new cdk.App();

// Get configuration from environment variables or context
const environment = app.node.tryGetContext('environment') || process.env.ENVIRONMENT || 'dev';
const awsRegion = app.node.tryGetContext('aws-region') || process.env.AWS_REGION || 'us-east-1';
const jenkinsUrl = app.node.tryGetContext('jenkins-url') || process.env.JENKINS_URL;
const jenkinsUsername = app.node.tryGetContext('jenkins-username') || process.env.JENKINS_USERNAME;
const jenkinsApiToken = app.node.tryGetContext('jenkins-api-token') || process.env.JENKINS_API_TOKEN;

if (!jenkinsUrl || !jenkinsUsername || !jenkinsApiToken) {
  throw new Error('Missing required Jenkins configuration. Please set JENKINS_URL, JENKINS_USERNAME, and JENKINS_API_TOKEN environment variables.');
}

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: awsRegion,
};

const stackProps = {
  env,
  environment,
  jenkinsUrl,
  jenkinsUsername,
  jenkinsApiToken,
};

// Create OAuth server stack first
const oauthStack = new JenkinsMcpOAuthStack(app, `JenkinsMcpOAuthStack-${environment}`, stackProps);

// Create MCP server stack with dependency on OAuth stack
const mcpStack = new JenkinsMcpServerStack(app, `JenkinsMcpServerStack-${environment}`, {
  ...stackProps,
  oauthApiUrl: oauthStack.oauthApiUrl,
});

// Add dependency
mcpStack.addDependency(oauthStack);

// Add tags to all stacks
cdk.Tags.of(app).add('Project', 'jenkins-mcp-server');
cdk.Tags.of(app).add('Environment', environment);
cdk.Tags.of(app).add('ManagedBy', 'CDK');
