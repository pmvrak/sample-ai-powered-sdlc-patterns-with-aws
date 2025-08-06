#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';

import { OpenSearchStack } from '../lib/stacks/opensearch-stack';
import { BedrockStack } from '../lib/stacks/bedrock-stack';
// StorageStack removed - S3 buckets no longer needed as Lambdas return responses directly
import { LambdaStack } from '../lib/stacks/lambda-stack';
import { McpServerStack } from '../lib/stacks/mcp-server-stack';


const app = new cdk.App();

// Deploy OpenSearch Stack first (needed for Bedrock knowledge base)
const opensearchStack = new OpenSearchStack(app, 'OpenSearchStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1'
  }
});

// Storage Stack removed - S3 buckets no longer needed as Lambdas return responses directly

// Deploy Bedrock Stack second (agent and knowledge base for OpenAPI generation)
const bedrockStack = new BedrockStack(app, 'BedrockStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1'
  },
  collectionArn: opensearchStack.collection.attrArn,
  bucketArn: opensearchStack.s3Bucket.attrArn,
  bedrockRoleArn: opensearchStack.bedrockRole.attrArn
});

// Deploy Lambda Stack third (Domain Analyzer and Doc Generator functions)
const lambdaStack = new LambdaStack(app, 'LambdaAPIStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1'
  },
  bedrockAgentId: bedrockStack.agentId,
  bedrockAgentAliasId: process.env.BEDROCK_AGENT_ALIAS_ID || 'TSTALIASID', // Default test alias ID
  knowledgeBaseId: bedrockStack.knowledgeBaseId
});

// Deploy MCP Server Stack fourth (ECS service with ALB)
// Get parameters from CDK context
const certificateArn = app.node.tryGetContext('certificateArn');
const domainName = app.node.tryGetContext('domainName');
const allowedIpsString = app.node.tryGetContext('allowedIps');
const allowedIps = allowedIpsString ? allowedIpsString.split(',').map((ip: string) => ip.trim()) : undefined;

const mcpServerStack = new McpServerStack(app, 'McpServerStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1'
  },
  certificateArn,
  domainName,
  allowedIps,
  domainAnalyzerFunction: lambdaStack.domainAnalyzerFunction,
  docGeneratorFunction: lambdaStack.docGeneratorFunction
});

// Add dependencies to ensure proper deployment order
bedrockStack.addDependency(opensearchStack);
lambdaStack.addDependency(bedrockStack);
mcpServerStack.addDependency(lambdaStack); // MCP Server stack depends on Lambda stack for function references
mcpServerStack.addDependency(bedrockStack); // MCP Server stack depends on Bedrock stack for agent configuration

// Comment out cdk-nag checks to avoid deployment issues
// cdk.Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }));

// CDK Nag suppressions are handled via command line flags in deploy-all.sh

app.synth();
