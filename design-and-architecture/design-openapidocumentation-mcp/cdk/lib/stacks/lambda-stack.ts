import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';

export interface LambdaStackProps extends cdk.StackProps {
  bedrockAgentId?: string;
  bedrockAgentAliasId?: string;
  knowledgeBaseId?: string;
}

export class LambdaStack extends cdk.Stack {
  public readonly domainAnalyzerFunction: lambda.Function;
  public readonly docGeneratorFunction: lambda.Function;

  constructor(scope: Construct, id: string, props: LambdaStackProps) {
    super(scope, id, props);

    // Create IAM role for domain analyzer Lambda function with least-privilege permissions
    const domainAnalyzerRole = new iam.Role(this, 'DomainAnalyzerLambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      description: 'IAM role for domain analyzer Lambda function with least-privilege Bedrock and S3 access'
    });

    // Add CloudWatch Logs permissions (minimum required for Lambda execution)
    domainAnalyzerRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents'
      ],
      resources: [
        `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/lambda/*`
      ]
    }));

    // Add Bedrock agent permissions if agent is configured
    if (props.bedrockAgentId && props.bedrockAgentAliasId) {
      domainAnalyzerRole.addToPolicy(new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'bedrock:InvokeAgent',
          'bedrock:GetAgent',
          'bedrock:GetAgentAlias'
        ],
        resources: [
          `arn:aws:bedrock:${this.region}:${this.account}:agent/${props.bedrockAgentId}`,
          `arn:aws:bedrock:${this.region}:${this.account}:agent-alias/${props.bedrockAgentId}/${props.bedrockAgentAliasId}`
        ]
      }));
    }

    // Add separate policy for model invocation with specific model
    domainAnalyzerRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'bedrock:InvokeModel'
      ],
      resources: [
        `*`
      ]
    }));

    // S3 permissions removed - Lambda functions now return responses directly

    // Suppress cdk-nag warnings for IAM role policies
    NagSuppressions.addResourceSuppressions(domainAnalyzerRole, [
      {
        id: 'AwsSolutions-IAM5',
        reason: 'Wildcard permissions are necessary for CloudWatch Logs (Lambda runtime requirement) and Bedrock model access (cross-region inference profiles)',
        appliesTo: [
          `Resource::arn:aws:logs:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:log-group:/aws/lambda/*`,
          `Resource::arn:aws:bedrock:*:${cdk.Aws.ACCOUNT_ID}:inference-profile/eu.anthropic.claude-3-7-sonnet-20250219-v1:0`
        ]
      }
    ], true);

    // Create domain analyzer Lambda function
    this.domainAnalyzerFunction = new lambda.Function(this, 'DomainAnalyzerFunction', {
      runtime: lambda.Runtime.NODEJS_22_X,
      handler: 'domain-analyzer.handler',
      code: lambda.Code.fromAsset('../domain-analyzer-lambda'),
      role: domainAnalyzerRole,
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      environment: {
        BEDROCK_REGION: process.env.BEDROCK_REGION || this.region,
        MODEL_ID: process.env.MODEL_ID || 'anthropic.claude-3-7-sonnet-20250219-v1:0',
        ...(props.bedrockAgentId && { BEDROCK_AGENT_ID: props.bedrockAgentId }),
        ...(props.bedrockAgentAliasId && { BEDROCK_AGENT_ALIAS_ID: props.bedrockAgentAliasId }),
        AUTH_REQUIRED: 'false' // Disable authentication for internal calls
      },
      description: 'Lambda function for domain model analysis using Bedrock Claude 3.7 Sonnet'
    });



    // Export Lambda function ARN for application use
    new cdk.CfnOutput(this, 'DomainAnalyzerFunctionArn', {
      value: this.domainAnalyzerFunction.functionArn,
      description: 'ARN of the domain analyzer Lambda function',
      exportName: `${this.stackName}-DomainAnalyzerFunctionArn`
    });

    new cdk.CfnOutput(this, 'DomainAnalyzerFunctionName', {
      value: this.domainAnalyzerFunction.functionName,
      description: 'Name of the domain analyzer Lambda function',
      exportName: `${this.stackName}-DomainAnalyzerFunctionName`
    });

    // Create IAM role for doc generator Lambda function with least-privilege permissions
    const docGeneratorRole = new iam.Role(this, 'DocGeneratorLambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      description: 'IAM role for doc generator Lambda function with minimal Bedrock access'
    });

    // Add CloudWatch Logs permissions (minimum required for Lambda execution)
    docGeneratorRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents'
      ],
      resources: [
        `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/lambda/*`
      ]
    }));

    // Add minimal Bedrock permissions for model invocation only
    docGeneratorRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'bedrock:InvokeModel'
      ],
      resources: [
        `*`
      ]
    }));

    // S3 permissions removed - Lambda functions now return responses directly

    // Create doc generator Lambda function
    this.docGeneratorFunction = new lambda.Function(this, 'DocGeneratorFunction', {
      runtime: lambda.Runtime.NODEJS_22_X,
      handler: 'doc-gen.handler',
      code: lambda.Code.fromAsset('../doc-gen-lambda'),
      role: docGeneratorRole,
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      environment: {
        BEDROCK_REGION: process.env.BEDROCK_REGION || this.region,
        MODEL_ID: process.env.MODEL_ID || 'anthropic.claude-3-7-sonnet-20250219-v1:0',
        AUTH_REQUIRED: 'false' // Disable authentication for internal calls
      },
      description: 'Lambda function for API documentation generation using Bedrock Claude 3.7 Sonnet'
    });



    // Suppress cdk-nag warnings for doc generator IAM role policies
    NagSuppressions.addResourceSuppressions(docGeneratorRole, [
      {
        id: 'AwsSolutions-IAM5',
        reason: 'Wildcard permissions are necessary for CloudWatch Logs (Lambda runtime requirement) and Bedrock model access (cross-region inference profiles)',
        appliesTo: [
          `Resource::arn:aws:logs:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:log-group:/aws/lambda/*`,
          `Resource::arn:aws:bedrock:*:${cdk.Aws.ACCOUNT_ID}:inference-profile/eu.anthropic.claude-3-7-sonnet-20250219-v1:0`
        ]
      }
    ], true);

    // Export doc generator Lambda function ARN for application use
    new cdk.CfnOutput(this, 'DocGeneratorFunctionArn', {
      value: this.docGeneratorFunction.functionArn,
      description: 'ARN of the doc generator Lambda function',
      exportName: `${this.stackName}-DocGeneratorFunctionArn`
    });

    new cdk.CfnOutput(this, 'DocGeneratorFunctionName', {
      value: this.docGeneratorFunction.functionName,
      description: 'Name of the doc generator Lambda function',
      exportName: `${this.stackName}-DocGeneratorFunctionName`
    });

    // Backend functionality is now handled by the MCP server ECS service
  }
}