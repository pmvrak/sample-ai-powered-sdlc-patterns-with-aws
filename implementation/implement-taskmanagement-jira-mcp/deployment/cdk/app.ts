#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { JiraMcpServerStack } from './lib/jira-mcp-server-stack';
import { JiraMcpOAuthStack } from './lib/jira-mcp-oauth-stack';

const app = new cdk.App();

// Get configuration from environment variables or context
const environment = app.node.tryGetContext('environment') || process.env.ENVIRONMENT || 'dev';
const awsRegion = app.node.tryGetContext('aws-region') || process.env.AWS_REGION || 'us-east-1';
const jiraUrl = app.node.tryGetContext('jira-url') || process.env.JIRA_URL;
const jiraUsername = app.node.tryGetContext('jira-username') || process.env.JIRA_USERNAME;
const jiraApiToken = app.node.tryGetContext('jira-api-token') || process.env.JIRA_API_TOKEN;

if (!jiraUrl || !jiraUsername || !jiraApiToken) {
  throw new Error('Missing required JIRA configuration. Please set JIRA_URL, JIRA_USERNAME, and JIRA_API_TOKEN environment variables.');
}

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: awsRegion,
};

const stackProps = {
  env,
  environment,
  jiraUrl,
  jiraUsername,
  jiraApiToken,
};

// Create OAuth server stack first
const oauthStack = new JiraMcpOAuthStack(app, `JiraMcpOAuthStack-${environment}`, stackProps);

// Create MCP server stack with dependency on OAuth stack
const mcpStack = new JiraMcpServerStack(app, `JiraMcpServerStack-${environment}`, {
  ...stackProps,
  oauthApiUrl: oauthStack.oauthApiUrl,
});

// Add dependency
mcpStack.addDependency(oauthStack);

// Add tags to all stacks
cdk.Tags.of(app).add('Project', 'jira-mcp-server');
cdk.Tags.of(app).add('Environment', environment);
cdk.Tags.of(app).add('ManagedBy', 'CDK');
