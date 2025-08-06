import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';

import * as certificatemanager from 'aws-cdk-lib/aws-certificatemanager';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';

export interface McpServerStackProps extends cdk.StackProps {
  vpcId?: string;
  domainName?: string;
  certificateArn?: string;
  allowedIps?: string[];
  domainAnalyzerFunction?: lambda.Function;
  docGeneratorFunction?: lambda.Function;

}

export class McpServerStack extends cdk.Stack {
  public readonly serviceUrl: string;
  public readonly loadBalancer: elbv2.ApplicationLoadBalancer;

  constructor(scope: Construct, id: string, props?: McpServerStackProps) {
    super(scope, id, props);

    // Create S3 bucket for ALB access logs (simplified)
    const albLogsBucket = new s3.Bucket(this, 'McpServerAlbLogsBucket', {
      bucketName: `mcp-server-alb-logs-${cdk.Aws.ACCOUNT_ID}-${cdk.Aws.REGION}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Create or use existing VPC (no NAT Gateway - using VPC Endpoints instead)
    const vpc = props?.vpcId
      ? ec2.Vpc.fromLookup(this, 'ExistingVpc', { vpcId: props.vpcId })
      : new ec2.Vpc(this, 'McpServerVpc', {
        maxAzs: 2,
        natGateways: 0, // No NAT Gateway - using VPC Endpoints
        subnetConfiguration: [
          {
            cidrMask: 24,
            name: 'Private',
            subnetType: ec2.SubnetType.PRIVATE_ISOLATED, // Changed to isolated
          },
          {
            cidrMask: 24,
            name: 'Public',
            subnetType: ec2.SubnetType.PUBLIC,
          },
        ],
      });

    // Suppress VPC Flow Logs warning - not needed for this simple MCP server use case
    if (!props?.vpcId) {
      NagSuppressions.addResourceSuppressions(
        vpc,
        [
          {
            id: 'AwsSolutions-VPC7',
            reason: 'VPC Flow Logs not required for simple MCP server deployment. Can be enabled later if detailed network monitoring is needed.',
          },
        ]
      );
    }

    // Create VPC Endpoints to replace NAT Gateway functionality
    // S3 Gateway Endpoint (FREE - for ALB logs and general S3 access)
    new ec2.GatewayVpcEndpoint(this, 'S3Endpoint', {
      vpc,
      service: ec2.GatewayVpcEndpointAwsService.S3,
      subnets: [
        {
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
      ],
    });

    // ECR API Endpoint (for Docker registry API calls)
    const ecrApiEndpoint = new ec2.InterfaceVpcEndpoint(this, 'EcrApiEndpoint', {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.ECR,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      privateDnsEnabled: true,
    });

    // ECR Docker Endpoint (for Docker image pulls)
    const ecrDkrEndpoint = new ec2.InterfaceVpcEndpoint(this, 'EcrDkrEndpoint', {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      privateDnsEnabled: true,
    });

    // CloudWatch Logs Endpoint (for application logging)
    const logsEndpoint = new ec2.InterfaceVpcEndpoint(this, 'LogsEndpoint', {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      privateDnsEnabled: true,
    });

    // Bedrock Runtime Endpoint (for AI model access)
    const bedrockEndpoint = new ec2.InterfaceVpcEndpoint(this, 'BedrockEndpoint', {
      vpc,
      service: new ec2.InterfaceVpcEndpointService(`com.amazonaws.${cdk.Aws.REGION}.bedrock-runtime`),
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      privateDnsEnabled: true,
    });



    // SSM Endpoint (for parameter store secrets)
    const ssmEndpoint = new ec2.InterfaceVpcEndpoint(this, 'SsmEndpoint', {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.SSM,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      privateDnsEnabled: true,
    });

    // Lambda Endpoint (for Lambda function invocation)
    const lambdaEndpoint = new ec2.InterfaceVpcEndpoint(this, 'LambdaEndpoint', {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.LAMBDA,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      privateDnsEnabled: true,
    });

    // Create ECR repository for the MCP server image with unique name
    const ecrRepository = new ecr.Repository(this, 'McpServerRepository', {
      repositoryName: `mcp-server-${cdk.Aws.ACCOUNT_ID}`,
      imageScanOnPush: true,
      lifecycleRules: [
        {
          maxImageCount: 10,
          tagStatus: ecr.TagStatus.UNTAGGED,
        },
      ],
    });

    // Create ECS cluster with Container Insights
    const cluster = new ecs.Cluster(this, 'McpServerCluster', {
      vpc,
      clusterName: 'mcp-server-cluster',
      enableFargateCapacityProviders: true,
    });

    // Enable Container Insights manually since the property is deprecated
    const cfnCluster = cluster.node.defaultChild as ecs.CfnCluster;
    cfnCluster.clusterSettings = [
      {
        name: 'containerInsights',
        value: 'enabled',
      },
    ];

    // Create CloudWatch log group
    const logGroup = new logs.LogGroup(this, 'McpServerLogGroup', {
      logGroupName: '/ecs/mcp-server',
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Create custom managed policy for task execution role
    const taskExecutionPolicy = new iam.ManagedPolicy(this, 'McpServerTaskExecutionPolicy', {
      statements: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'ecr:GetAuthorizationToken',
            'ecr:BatchCheckLayerAvailability',
            'ecr:GetDownloadUrlForLayer',
            'ecr:BatchGetImage',
          ],
          resources: [ecrRepository.repositoryArn],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'logs:CreateLogStream',
            'logs:PutLogEvents',
          ],
          resources: [logGroup.logGroupArn],
        }),
      ],
    });

    // Create task execution role
    const taskExecutionRole = new iam.Role(this, 'McpServerTaskExecutionRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      managedPolicies: [taskExecutionPolicy],
    });


    // Create task role with necessary permissions
    const taskRole = new iam.Role(this, 'McpServerTaskRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      inlinePolicies: {
        McpServerPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'bedrock:InvokeModel',
                'bedrock:InvokeModelWithResponseStream',
              ],
              resources: [
                `arn:aws:bedrock:${cdk.Aws.REGION}::foundation-model/*`,
                `arn:aws:bedrock:*::foundation-model/*`,
                `arn:aws:bedrock:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:inference-profile/*`,
              ],
            }),

            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'lambda:InvokeFunction',
              ],
              resources: [
                ...(props?.domainAnalyzerFunction ? [props.domainAnalyzerFunction.functionArn] : []),
                ...(props?.docGeneratorFunction ? [props.docGeneratorFunction.functionArn] : []),
              ],
            }),
            // S3 permissions removed - Lambda functions now return responses directly
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'logs:CreateLogStream',
                'logs:PutLogEvents',
              ],
              resources: [logGroup.logGroupArn],
            }),
          ],
        }),
      },
    });

    // Create Fargate task definition with explicit x86_64 architecture
    const taskDefinition = new ecs.FargateTaskDefinition(this, 'McpServerTaskDefinition', {
      memoryLimitMiB: 1024,
      cpu: 512,
      executionRole: taskExecutionRole,
      taskRole: taskRole,
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.X86_64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
    });

    // Add container to task definition (using secrets instead of environment variables)
    const container = taskDefinition.addContainer('McpServerContainer', {
      image: ecs.ContainerImage.fromEcrRepository(ecrRepository, 'latest'),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'mcp-server',
        logGroup: logGroup,
      }),
      // Use environment variables for configuration - updated for US inference profile
      environment: {
        NODE_ENV: process.env.NODE_ENV || 'production',
        PORT: process.env.PORT || '3000',
        MCP_PORT: process.env.MCP_PORT || '3001',
        AWS_REGION: cdk.Aws.REGION,
        BEDROCK_REGION: process.env.BEDROCK_REGION || 'us-east-1',
        MODEL_ID: process.env.MODEL_ID || 'us.anthropic.claude-3-7-sonnet-20250219-v1:0',
        // BUCKET_NAME removed - Lambda functions now return responses directly
        DOMAIN_ANALYZER_LAMBDA_ARN: props?.domainAnalyzerFunction?.functionArn || '',
        DOC_GENERATOR_LAMBDA_ARN: props?.docGeneratorFunction?.functionArn || '',

        MCP_SERVER_NAME: process.env.MCP_SERVER_NAME || 'openapi-documentation-mcp-prod',
        MCP_SERVER_VERSION: process.env.MCP_SERVER_VERSION || '1.0.1',
        LOG_LEVEL: process.env.LOG_LEVEL || 'info',
        HEALTH_CHECK_ENABLED: process.env.HEALTH_CHECK_ENABLED || 'true',
        ENABLE_REQUEST_LOGGING: process.env.ENABLE_REQUEST_LOGGING || 'true',
      },
      healthCheck: {
        command: ['CMD-SHELL', 'node -e "require(\'http\').get(\'http://localhost:3000/health\', (res) => { process.exit(res.statusCode === 200 ? 0 : 1) })" || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
    });

    container.addPortMappings({
      containerPort: 3001,
      protocol: ecs.Protocol.TCP,
    });

    // Add port mapping for health endpoint
    container.addPortMappings({
      containerPort: 3000,
      protocol: ecs.Protocol.TCP,
    });

    // Create security group for ECS service
    const ecsSecurityGroup = new ec2.SecurityGroup(this, 'McpServerEcsSecurityGroup', {
      vpc,
      description: 'Security group for MCP Server ECS service',
      allowAllOutbound: true,
    });

    // Create security group for load balancer
    const albSecurityGroup = new ec2.SecurityGroup(this, 'McpServerAlbSecurityGroup', {
      vpc,
      description: 'Security group for MCP Server ALB',
      allowAllOutbound: true,
    });

    // Allow inbound traffic from ALB to ECS on both ports
    ecsSecurityGroup.addIngressRule(
      albSecurityGroup,
      ec2.Port.tcp(3001),
      'Allow ALB to reach MCP server port'
    );

    ecsSecurityGroup.addIngressRule(
      albSecurityGroup,
      ec2.Port.tcp(3000),
      'Allow ALB to reach health check port'
    );

    // Allow inbound HTTP traffic to ALB from specific IPs only
    const allowedIps = props?.allowedIps || [];

    if (allowedIps.length === 0) {
      // If no IPs specified, warn and require explicit IP configuration
      console.warn('WARNING: No allowed IPs specified. ALB access will be restricted.');
      console.warn('Use --allowed-ips parameter or set allowedIps in stack props to allow access.');
      // Don't add any ingress rules - ALB will be inaccessible until IPs are specified
    } else {
      // Add rules for each allowed IP
      allowedIps.forEach((ip) => {
        albSecurityGroup.addIngressRule(
          ec2.Peer.ipv4(ip),
          ec2.Port.tcp(80),
          `Allow HTTP traffic from ${ip}`
        );

        // Also allow HTTPS in case we add certificates later
        albSecurityGroup.addIngressRule(
          ec2.Peer.ipv4(ip),
          ec2.Port.tcp(443),
          `Allow HTTPS traffic from ${ip}`
        );
      });

      console.log(`ALB access restricted to IPs: ${allowedIps.join(', ')}`);
    }

    // Create the ALB first so we can get its DNS name
    this.loadBalancer = new elbv2.ApplicationLoadBalancer(this, 'McpServerLoadBalancer', {
      vpc,
      internetFacing: true, // Public ALB for web app access
      securityGroup: albSecurityGroup,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PUBLIC,
      },
    });

    // Set ALB idle timeout to 20 minutes (1200 seconds) for long-running operations
    const cfnLoadBalancer = this.loadBalancer.node.defaultChild as elbv2.CfnLoadBalancer;
    cfnLoadBalancer.addPropertyOverride('LoadBalancerAttributes', [
      {
        Key: 'idle_timeout.timeout_seconds',
        Value: '1200'
      }
    ]);

    // Enable ALB access logs
    this.loadBalancer.logAccessLogs(albLogsBucket, 'mcp-server-alb');

    // Create Fargate service with lower desired count initially
    const service = new ecs.FargateService(this, 'McpServerService', {
      cluster,
      taskDefinition,
      desiredCount: 0, // Start with 0, scale up after image is pushed
      assignPublicIp: false,
      securityGroups: [ecsSecurityGroup],
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      enableExecuteCommand: true,
      minHealthyPercent: 0, // Allow scaling from 0
      maxHealthyPercent: 200,
    });

    // Create target group
    const targetGroup = new elbv2.ApplicationTargetGroup(this, 'McpServerTargetGroup', {
      vpc,
      port: 3001,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      healthCheck: {
        enabled: true,
        path: '/health',
        protocol: elbv2.Protocol.HTTP,
        port: '3000', // Health endpoint is on port 3000
        healthyHttpCodes: '200',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
      },
    });

    // Add ECS service to target group
    service.attachToApplicationTargetGroup(targetGroup);

    // MCP Server handles its own authentication - no Cognito needed

    // Simple HTTP/HTTPS setup without Cognito authentication
    // MCP server handles its own authentication
    if (props?.certificateArn || props?.domainName) {
      let certificate;
      if (props?.certificateArn) {
        certificate = certificatemanager.Certificate.fromCertificateArn(
          this,
          'McpServerCertificate',
          props.certificateArn
        );
      } else if (props?.domainName) {
        certificate = new certificatemanager.Certificate(this, 'McpServerCertificate', {
          domainName: props.domainName,
          validation: certificatemanager.CertificateValidation.fromDns(),
        });
      }

      // Create HTTP listener that redirects all traffic to HTTPS
      this.loadBalancer.addListener('McpServerHttpListener', {
        port: 80,
        protocol: elbv2.ApplicationProtocol.HTTP,
        defaultAction: elbv2.ListenerAction.redirect({
          protocol: 'HTTPS',
          port: '443',
          permanent: true,
        }),
      });

      // Create HTTPS listener
      this.loadBalancer.addListener('McpServerHttpsListener', {
        port: 443,
        protocol: elbv2.ApplicationProtocol.HTTPS,
        certificates: [certificate!],
        defaultAction: elbv2.ListenerAction.forward([targetGroup]),
      });

      // Set service URL to use HTTPS
      this.serviceUrl = `https://${this.loadBalancer.loadBalancerDnsName}`;
    } else {
      // Use HTTP only
      this.loadBalancer.addListener('McpServerHttpOnlyListener', {
        port: 80,
        protocol: elbv2.ApplicationProtocol.HTTP,
        defaultAction: elbv2.ListenerAction.forward([targetGroup]),
      });

      // Set service URL to use HTTP
      this.serviceUrl = `http://${this.loadBalancer.loadBalancerDnsName}`;
    }

    // Outputs
    new cdk.CfnOutput(this, 'McpServerUrl', {
      value: this.serviceUrl,
      description: 'MCP Server URL',
    });

    new cdk.CfnOutput(this, 'EcrRepositoryUri', {
      value: ecrRepository.repositoryUri,
      description: 'ECR Repository URI for MCP Server',
    });

    new cdk.CfnOutput(this, 'ClusterName', {
      value: cluster.clusterName,
      description: 'ECS Cluster Name',
    });

    new cdk.CfnOutput(this, 'ServiceName', {
      value: service.serviceName,
      description: 'ECS Service Name',
    });

    // Add CDK-nag suppressions for acceptable security trade-offs
    NagSuppressions.addResourceSuppressions(
      albLogsBucket,
      [
        {
          id: 'AwsSolutions-S1',
          reason: 'ALB access logs bucket does not need server access logging for this use case',
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      taskExecutionRole,
      [
        {
          id: 'AwsSolutions-IAM4',
          reason: 'Task execution role uses custom managed policy instead of AWS managed policy',
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      taskExecutionPolicy,
      [
        {
          id: 'AwsSolutions-IAM5',
          reason: 'ECR GetAuthorizationToken requires wildcard permission as it does not support resource-level permissions',
          appliesTo: ['Resource::*'],
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      taskExecutionRole.node.findChild('DefaultPolicy'),
      [
        {
          id: 'AwsSolutions-IAM5',
          reason: 'Task execution role default policy requires wildcard permissions for ECR and CloudWatch operations',
          appliesTo: ['Resource::*'],
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      taskRole,
      [
        {
          id: 'AwsSolutions-IAM5',
          reason: 'Bedrock foundation models require wildcard permissions as model ARNs are not predictable',
          appliesTo: [
            'Resource::arn:aws:bedrock:<AWS::Region>::foundation-model/*',
            'Resource::arn:aws:bedrock-agent:<AWS::Region>:<AWS::AccountId>:agent/*',
          ],
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      taskRole.node.findChild('DefaultPolicy'),
      [
        {
          id: 'AwsSolutions-IAM5',
          reason: 'CloudWatch Logs permissions are scoped to specific log group',
          appliesTo: ['Resource::*'],
        },
      ]
    );

    NagSuppressions.addResourceSuppressions(
      albSecurityGroup,
      [
        {
          id: 'CdkNagValidationFailure',
          reason: 'VPC CIDR block reference is acceptable for private ALB security group',
        },
        {
          id: 'AwsSolutions-EC23',
          reason: 'ALB security group allows internet access which is required for public-facing load balancer',
        },
      ]
    );

    // Suppress VPC Endpoint security group warnings
    [ecrApiEndpoint, ecrDkrEndpoint, logsEndpoint, bedrockEndpoint, ssmEndpoint, lambdaEndpoint].forEach((endpoint) => {
      NagSuppressions.addResourceSuppressions(
        endpoint,
        [
          {
            id: 'CdkNagValidationFailure',
            reason: 'VPC endpoint security groups with VPC CIDR references are acceptable for private connectivity',
          },
        ]
      );

      // Add suppressions for the security groups
      const securityGroup = endpoint.node.findChild('SecurityGroup');
      if (securityGroup) {
        NagSuppressions.addResourceSuppressions(
          securityGroup,
          [
            {
              id: 'AwsSolutions-EC23',
              reason: 'VPC endpoint security groups use VPC CIDR references which is acceptable for private connectivity',
            },
            {
              id: 'CdkNagValidationFailure',
              reason: 'VPC endpoint security groups with VPC CIDR references are acceptable for private connectivity',
            },
          ]
        );
      }
    });

    // CDK Nag suppressions removed - no S3 permissions needed

    NagSuppressions.addResourceSuppressions(taskDefinition, [
      {
        id: 'AwsSolutions-ECS2',
        reason: 'Environment variables are acceptable for this use case as they contain non-sensitive configuration',
      },
    ]);

    // Cognito removed - MCP server handles its own authentication

    // Suppress Lambda IAM role warnings if they exist
    try {
      const customResourceProvider = this.node.findChild('AWS679f53fac002430cb0da5b7982bd2287');
      if (customResourceProvider) {
        const serviceRole = customResourceProvider.node.findChild('ServiceRole');
        if (serviceRole) {
          NagSuppressions.addResourceSuppressions(serviceRole, [
            {
              id: 'AwsSolutions-IAM4',
              reason: 'AWS Lambda custom resource provider uses AWS managed policy by design',
              appliesTo: ['Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'],
            },
          ]);
        }
      }
    } catch (error) {
      // Ignore if the resource doesn't exist
      console.log('Custom resource provider not found, skipping suppressions');
    }
  }
}