import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import * as path from 'path';

export interface JiraMcpServerStackProps extends cdk.StackProps {
  environment: string;
  jiraUrl: string;
  jiraUsername: string;
  jiraApiToken: string;
  oauthApiUrl: string;
}

export class JiraMcpServerStack extends cdk.Stack {
  public readonly mcpApiUrl: string;

  constructor(scope: Construct, id: string, props: JiraMcpServerStackProps) {
    super(scope, id, props);

    // CloudWatch Log Group for MCP Lambda
    const mcpLogGroup = new logs.LogGroup(this, 'McpLambdaLogGroup', {
      logGroupName: `/aws/lambda/jira-mcp-server-${props.environment}`,
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // IAM role for MCP Lambda
    const mcpLambdaRole = new iam.Role(this, 'McpLambdaRole', {
      roleName: `jira-mcp-lambda-role-${props.environment}`,
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
    });

    // MCP Lambda function
    const mcpLambda = new lambda.Function(this, 'McpServerFunction', {
      functionName: `jira-mcp-server-${props.environment}`,
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'lambda_handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../lambda-deployment.zip')),
      role: mcpLambdaRole,
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        JIRA_URL: props.jiraUrl,
        JIRA_USERNAME: props.jiraUsername,
        JIRA_API_TOKEN: props.jiraApiToken,
        OAUTH_ISSUER: props.oauthApiUrl,
      },
    });

    // API Gateway for MCP server
    const mcpApi = new apigateway.RestApi(this, 'McpApi', {
      restApiName: `jira-mcp-api-${props.environment}`,
      description: 'JIRA MCP Server API for Amazon Q Developer',
      deployOptions: {
        stageName: props.environment,
        throttlingRateLimit: 100,
        throttlingBurstLimit: 200,
      },
      defaultCorsPreflightOptions: {
        allowCredentials: false,
        allowHeaders: ['Authorization', 'Content-Type', 'X-Amz-Date', 'X-Api-Key'],
        allowMethods: ['GET', 'POST', 'OPTIONS'],
        allowOrigins: ['https://console.aws.amazon.com', 'https://q.amazonaws.com'],
        maxAge: cdk.Duration.minutes(5),
      },
    });

    // Lambda integration
    const mcpLambdaIntegration = new apigateway.LambdaIntegration(mcpLambda, {
      requestTemplates: { 
        "application/json": '{ "statusCode": "200" }' 
      },
      proxy: true,
    });

    // MCP routes - using proxy integration for all paths
    mcpApi.root.addMethod('ANY', mcpLambdaIntegration);
    
    // Proxy resource for catch-all
    const proxyResource = mcpApi.root.addResource('{proxy+}');
    proxyResource.addMethod('ANY', mcpLambdaIntegration);

    // Store the URL for outputs
    this.mcpApiUrl = mcpApi.url;
    // Note: MCP_SERVER_URL will be set via environment variable or discovered at runtime

    // Outputs
    new cdk.CfnOutput(this, 'McpApiEndpoint', {
      value: this.mcpApiUrl,
      description: 'MCP API Gateway endpoint',
    });

    new cdk.CfnOutput(this, 'McpServerUrl', {
      value: this.mcpApiUrl,
      description: 'MCP Server URL',
    });

    new cdk.CfnOutput(this, 'ProtectedResourceMetadataUrl', {
      value: `${this.mcpApiUrl}.well-known/oauth-protected-resource`,
      description: 'Protected resource metadata URL',
    });

    new cdk.CfnOutput(this, 'HealthCheckUrl', {
      value: `${this.mcpApiUrl}health`,
      description: 'Health check endpoint',
    });
  }
}
