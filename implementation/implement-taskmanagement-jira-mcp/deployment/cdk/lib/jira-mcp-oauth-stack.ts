import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import * as path from 'path';

export interface JiraMcpOAuthStackProps extends cdk.StackProps {
  environment: string;
  jiraUrl: string;
  jiraUsername: string;
  jiraApiToken: string;
}

export class JiraMcpOAuthStack extends cdk.Stack {
  public readonly oauthApiUrl: string;
  public readonly dynamoTable: dynamodb.Table;

  constructor(scope: Construct, id: string, props: JiraMcpOAuthStackProps) {
    super(scope, id, props);

    // DynamoDB table for OAuth clients and tokens
    this.dynamoTable = new dynamodb.Table(this, 'OAuthClientsTable', {
      tableName: `jira-mcp-oauth-clients-${props.environment}`,
      partitionKey: { name: 'client_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'expires_at',
      removalPolicy: cdk.RemovalPolicy.DESTROY, // For dev environments
    });

    // CloudWatch Log Group for OAuth Lambda
    const oauthLogGroup = new logs.LogGroup(this, 'OAuthLambdaLogGroup', {
      logGroupName: `/aws/lambda/jira-mcp-oauth-server-${props.environment}`,
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // IAM role for OAuth Lambda
    const oauthLambdaRole = new iam.Role(this, 'OAuthLambdaRole', {
      roleName: `jira-mcp-oauth-lambda-role-${props.environment}`,
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
      inlinePolicies: {
        DynamoDBPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'dynamodb:GetItem',
                'dynamodb:PutItem',
                'dynamodb:UpdateItem',
                'dynamodb:DeleteItem',
                'dynamodb:Query',
                'dynamodb:Scan',
              ],
              resources: [this.dynamoTable.tableArn],
            }),
          ],
        }),
      },
    });

    // OAuth Lambda function
    const oauthLambda = new lambda.Function(this, 'OAuthServerFunction', {
      functionName: `jira-mcp-oauth-server-${props.environment}`,
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'oauth_handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../oauth-server-deployment.zip')),
      role: oauthLambdaRole,
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        DYNAMODB_TABLE: this.dynamoTable.tableName,
        ENVIRONMENT: props.environment,
        MCP_SERVER_URL: '', // Will be set after MCP server creation
      },
    });

    // API Gateway for OAuth server
    const oauthApi = new apigateway.RestApi(this, 'OAuthApi', {
      restApiName: `jira-mcp-oauth-api-${props.environment}`,
      description: 'OAuth Authorization Server for JIRA MCP Server',
      deployOptions: {
        stageName: props.environment,
        throttlingRateLimit: 100,
        throttlingBurstLimit: 200,
      },
      defaultCorsPreflightOptions: {
        allowCredentials: false,
        allowHeaders: ['Authorization', 'Content-Type', 'X-Amz-Date'],
        allowMethods: ['GET', 'POST', 'OPTIONS'],
        allowOrigins: ['https://console.aws.amazon.com', 'https://q.amazonaws.com'],
        maxAge: cdk.Duration.minutes(5),
      },
    });

    // Lambda integration
    const oauthLambdaIntegration = new apigateway.LambdaIntegration(oauthLambda, {
      requestTemplates: { 
        "application/json": '{ "statusCode": "200" }' 
      },
      proxy: true,
    });

    // OAuth routes
    const wellKnownResource = oauthApi.root.addResource('.well-known');
    const authServerResource = wellKnownResource.addResource('oauth-authorization-server');
    authServerResource.addMethod('GET', oauthLambdaIntegration);

    const registerResource = oauthApi.root.addResource('register');
    registerResource.addMethod('POST', oauthLambdaIntegration);

    const authorizeResource = oauthApi.root.addResource('authorize');
    authorizeResource.addMethod('GET', oauthLambdaIntegration);

    const tokenResource = oauthApi.root.addResource('token');
    tokenResource.addMethod('POST', oauthLambdaIntegration);

    const introspectResource = oauthApi.root.addResource('introspect');
    introspectResource.addMethod('POST', oauthLambdaIntegration);

    // Update Lambda environment with OAuth issuer URL
    this.oauthApiUrl = oauthApi.url;
    // Note: OAUTH_ISSUER will be set via environment variable or discovered at runtime

    // Outputs
    new cdk.CfnOutput(this, 'OAuthApiEndpoint', {
      value: this.oauthApiUrl,
      description: 'OAuth API Gateway endpoint',
    });

    new cdk.CfnOutput(this, 'OAuthMetadataUrl', {
      value: `${this.oauthApiUrl}.well-known/oauth-authorization-server`,
      description: 'OAuth authorization server metadata URL',
    });

    new cdk.CfnOutput(this, 'DynamoTableName', {
      value: this.dynamoTable.tableName,
      description: 'DynamoDB table for OAuth clients',
    });
  }
}
