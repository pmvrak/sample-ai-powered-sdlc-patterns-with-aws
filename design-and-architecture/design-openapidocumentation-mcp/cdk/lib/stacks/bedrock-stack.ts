import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import { Construct } from 'constructs';
import { CONFIG } from '../config';
import { NagSuppressions } from 'cdk-nag';

interface BedrockStackProps extends cdk.StackProps {
  collectionArn: string;
  bucketArn: string;
  bedrockRoleArn: string;
}

export class BedrockStack extends cdk.Stack {
  public readonly agentId: string;
  public readonly knowledgeBaseId: string;

  constructor(scope: Construct, id: string, props: BedrockStackProps) {
    super(scope, id, props);

    // Agent Role
    const agentRole = new iam.CfnRole(this, 'AgentRole', {
      roleName: 'AmazonBedrockExecutionRoleForAgents_cdk',
      assumeRolePolicyDocument: {
        Statement: [{
          Effect: 'Allow',
          Principal: {
            Service: 'bedrock.amazonaws.com'
          },
          Action: 'sts:AssumeRole'
        }]
      },
      managedPolicyArns: ['arn:aws:iam::aws:policy/AmazonBedrockFullAccess']
    });

    // Knowledge Base
    const knowledgeBase = new bedrock.CfnKnowledgeBase(this, 'KnowledgeBase', {
      name: `${CONFIG.collectionName}-kb`,
      description: 'Answers on basis of data in knowledge base',
      roleArn: props.bedrockRoleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: process.env.BEDROCK_EMBEDDING_MODEL_ARN || `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`
        }
      },
      storageConfiguration: {
        type: 'OPENSEARCH_SERVERLESS',
        opensearchServerlessConfiguration: {
          collectionArn: props.collectionArn,
          vectorIndexName: CONFIG.indexName,
          fieldMapping: {
            vectorField: 'vector',
            textField: 'text',
            metadataField: 'metadata'
          }
        }
      }
    });

    // Data Source
    new bedrock.CfnDataSource(this, 'DataSource', {
      knowledgeBaseId: knowledgeBase.ref,
      name: `${CONFIG.collectionName}-datasource`,
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: {
          bucketArn: props.bucketArn
        }
      }
    });



    const agent = new bedrock.CfnAgent(this, 'Agent', {
      agentName: 'openapi-architect-agent',
      agentResourceRoleArn: agentRole.attrArn,
      autoPrepare: true,
      foundationModel: process.env.BEDROCK_FOUNDATION_MODEL || 'eu.anthropic.claude-3-7-sonnet-20250219-v1:0',
      instruction: `You are an AWS Solutions Architect specializing in API design and OpenAPI specification generation. Your task is to generate complete, well-structured OpenAPI 3.1 specifications based on the business requirements, domain analysis, and API details provided by the user. 

Key responsibilities:
1. Generate OpenAPI 3.1 specifications from user-provided business context and requirements
2. Create comprehensive API endpoints, schemas, and documentation
3. Follow REST API best practices and Well-Architected principles
4. Include appropriate HTTP methods, status codes, request/response schemas
5. Add security definitions, examples, and validation rules
6. Structure the output as valid OpenAPI 3.1 YAML or JSON

Always generate new specifications based on the user's input. Focus on creating concise, essential API definitions that match the provided business requirements. Keep responses under 20KB to avoid service limits. Prioritize core functionality over comprehensive details.`,
      description: 'AWS Solutions Architect for OpenAPI Generation',
      idleSessionTtlInSeconds: 900,
      knowledgeBases: [{
        knowledgeBaseId: knowledgeBase.ref,
        description: 'Knowledge base contains the latest OpenAPI specifications and instructions.',
        knowledgeBaseState: 'ENABLED'
      }]
    });

    // Set public properties for other stacks to reference
    this.agentId = agent.ref;
    this.knowledgeBaseId = knowledgeBase.ref;

    // Outputs
    new cdk.CfnOutput(this, 'KnowledgeBaseId', {
      value: knowledgeBase.ref
    });

    new cdk.CfnOutput(this, 'AgentId', {
      value: agent.ref
    });

    // CDK NAG suppressions for AWS managed policy usage
    NagSuppressions.addResourceSuppressions(agentRole, [
      {
        id: 'AwsSolutions-IAM4',
        reason: 'AmazonBedrockFullAccess managed policy is the AWS-recommended approach for Bedrock agents. This policy is maintained by AWS and includes the necessary permissions that evolve with the Bedrock service. Creating a custom policy would require constant maintenance to keep up with service updates.',
        appliesTo: ['Policy::arn:aws:iam::aws:policy/AmazonBedrockFullAccess']
      }
    ]);
  }
}
