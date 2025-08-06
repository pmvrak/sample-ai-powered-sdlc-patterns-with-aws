"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.McpServerStack = void 0;
const cdk = require("aws-cdk-lib");
const ec2 = require("aws-cdk-lib/aws-ec2");
const ecs = require("aws-cdk-lib/aws-ecs");
const elbv2 = require("aws-cdk-lib/aws-elasticloadbalancingv2");
const iam = require("aws-cdk-lib/aws-iam");
const logs = require("aws-cdk-lib/aws-logs");
const ecr = require("aws-cdk-lib/aws-ecr");
const s3 = require("aws-cdk-lib/aws-s3");
const certificatemanager = require("aws-cdk-lib/aws-certificatemanager");
const cdk_nag_1 = require("cdk-nag");
class McpServerStack extends cdk.Stack {
    constructor(scope, id, props) {
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
            cdk_nag_1.NagSuppressions.addResourceSuppressions(vpc, [
                {
                    id: 'AwsSolutions-VPC7',
                    reason: 'VPC Flow Logs not required for simple MCP server deployment. Can be enabled later if detailed network monitoring is needed.',
                },
            ]);
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
        const cfnCluster = cluster.node.defaultChild;
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
        ecsSecurityGroup.addIngressRule(albSecurityGroup, ec2.Port.tcp(3001), 'Allow ALB to reach MCP server port');
        ecsSecurityGroup.addIngressRule(albSecurityGroup, ec2.Port.tcp(3000), 'Allow ALB to reach health check port');
        // Allow inbound HTTP traffic to ALB from specific IPs only
        const allowedIps = props?.allowedIps || [];
        if (allowedIps.length === 0) {
            // If no IPs specified, warn and require explicit IP configuration
            console.warn('WARNING: No allowed IPs specified. ALB access will be restricted.');
            console.warn('Use --allowed-ips parameter or set allowedIps in stack props to allow access.');
            // Don't add any ingress rules - ALB will be inaccessible until IPs are specified
        }
        else {
            // Add rules for each allowed IP
            allowedIps.forEach((ip) => {
                albSecurityGroup.addIngressRule(ec2.Peer.ipv4(ip), ec2.Port.tcp(80), `Allow HTTP traffic from ${ip}`);
                // Also allow HTTPS in case we add certificates later
                albSecurityGroup.addIngressRule(ec2.Peer.ipv4(ip), ec2.Port.tcp(443), `Allow HTTPS traffic from ${ip}`);
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
        const cfnLoadBalancer = this.loadBalancer.node.defaultChild;
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
                certificate = certificatemanager.Certificate.fromCertificateArn(this, 'McpServerCertificate', props.certificateArn);
            }
            else if (props?.domainName) {
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
                certificates: [certificate],
                defaultAction: elbv2.ListenerAction.forward([targetGroup]),
            });
            // Set service URL to use HTTPS
            this.serviceUrl = `https://${this.loadBalancer.loadBalancerDnsName}`;
        }
        else {
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
        cdk_nag_1.NagSuppressions.addResourceSuppressions(albLogsBucket, [
            {
                id: 'AwsSolutions-S1',
                reason: 'ALB access logs bucket does not need server access logging for this use case',
            },
        ]);
        cdk_nag_1.NagSuppressions.addResourceSuppressions(taskExecutionRole, [
            {
                id: 'AwsSolutions-IAM4',
                reason: 'Task execution role uses custom managed policy instead of AWS managed policy',
            },
        ]);
        cdk_nag_1.NagSuppressions.addResourceSuppressions(taskExecutionPolicy, [
            {
                id: 'AwsSolutions-IAM5',
                reason: 'ECR GetAuthorizationToken requires wildcard permission as it does not support resource-level permissions',
                appliesTo: ['Resource::*'],
            },
        ]);
        cdk_nag_1.NagSuppressions.addResourceSuppressions(taskExecutionRole.node.findChild('DefaultPolicy'), [
            {
                id: 'AwsSolutions-IAM5',
                reason: 'Task execution role default policy requires wildcard permissions for ECR and CloudWatch operations',
                appliesTo: ['Resource::*'],
            },
        ]);
        cdk_nag_1.NagSuppressions.addResourceSuppressions(taskRole, [
            {
                id: 'AwsSolutions-IAM5',
                reason: 'Bedrock foundation models require wildcard permissions as model ARNs are not predictable',
                appliesTo: [
                    'Resource::arn:aws:bedrock:<AWS::Region>::foundation-model/*',
                    'Resource::arn:aws:bedrock-agent:<AWS::Region>:<AWS::AccountId>:agent/*',
                ],
            },
        ]);
        cdk_nag_1.NagSuppressions.addResourceSuppressions(taskRole.node.findChild('DefaultPolicy'), [
            {
                id: 'AwsSolutions-IAM5',
                reason: 'CloudWatch Logs permissions are scoped to specific log group',
                appliesTo: ['Resource::*'],
            },
        ]);
        cdk_nag_1.NagSuppressions.addResourceSuppressions(albSecurityGroup, [
            {
                id: 'CdkNagValidationFailure',
                reason: 'VPC CIDR block reference is acceptable for private ALB security group',
            },
            {
                id: 'AwsSolutions-EC23',
                reason: 'ALB security group allows internet access which is required for public-facing load balancer',
            },
        ]);
        // Suppress VPC Endpoint security group warnings
        [ecrApiEndpoint, ecrDkrEndpoint, logsEndpoint, bedrockEndpoint, ssmEndpoint, lambdaEndpoint].forEach((endpoint) => {
            cdk_nag_1.NagSuppressions.addResourceSuppressions(endpoint, [
                {
                    id: 'CdkNagValidationFailure',
                    reason: 'VPC endpoint security groups with VPC CIDR references are acceptable for private connectivity',
                },
            ]);
            // Add suppressions for the security groups
            const securityGroup = endpoint.node.findChild('SecurityGroup');
            if (securityGroup) {
                cdk_nag_1.NagSuppressions.addResourceSuppressions(securityGroup, [
                    {
                        id: 'AwsSolutions-EC23',
                        reason: 'VPC endpoint security groups use VPC CIDR references which is acceptable for private connectivity',
                    },
                    {
                        id: 'CdkNagValidationFailure',
                        reason: 'VPC endpoint security groups with VPC CIDR references are acceptable for private connectivity',
                    },
                ]);
            }
        });
        // CDK Nag suppressions removed - no S3 permissions needed
        cdk_nag_1.NagSuppressions.addResourceSuppressions(taskDefinition, [
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
                    cdk_nag_1.NagSuppressions.addResourceSuppressions(serviceRole, [
                        {
                            id: 'AwsSolutions-IAM4',
                            reason: 'AWS Lambda custom resource provider uses AWS managed policy by design',
                            appliesTo: ['Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'],
                        },
                    ]);
                }
            }
        }
        catch (error) {
            // Ignore if the resource doesn't exist
            console.log('Custom resource provider not found, skipping suppressions');
        }
    }
}
exports.McpServerStack = McpServerStack;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoibWNwLXNlcnZlci1zdGFjay5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbIm1jcC1zZXJ2ZXItc3RhY2sudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6Ijs7O0FBQUEsbUNBQW1DO0FBQ25DLDJDQUEyQztBQUMzQywyQ0FBMkM7QUFDM0MsZ0VBQWdFO0FBQ2hFLDJDQUEyQztBQUMzQyw2Q0FBNkM7QUFDN0MsMkNBQTJDO0FBRTNDLHlDQUF5QztBQUV6Qyx5RUFBeUU7QUFFekUscUNBQTBDO0FBWTFDLE1BQWEsY0FBZSxTQUFRLEdBQUcsQ0FBQyxLQUFLO0lBSTNDLFlBQVksS0FBZ0IsRUFBRSxFQUFVLEVBQUUsS0FBMkI7UUFDbkUsS0FBSyxDQUFDLEtBQUssRUFBRSxFQUFFLEVBQUUsS0FBSyxDQUFDLENBQUM7UUFFeEIsb0RBQW9EO1FBQ3BELE1BQU0sYUFBYSxHQUFHLElBQUksRUFBRSxDQUFDLE1BQU0sQ0FBQyxJQUFJLEVBQUUsd0JBQXdCLEVBQUU7WUFDbEUsVUFBVSxFQUFFLHVCQUF1QixHQUFHLENBQUMsR0FBRyxDQUFDLFVBQVUsSUFBSSxHQUFHLENBQUMsR0FBRyxDQUFDLE1BQU0sRUFBRTtZQUN6RSxpQkFBaUIsRUFBRSxFQUFFLENBQUMsaUJBQWlCLENBQUMsU0FBUztZQUNqRCxVQUFVLEVBQUUsRUFBRSxDQUFDLGdCQUFnQixDQUFDLFVBQVU7WUFDMUMsVUFBVSxFQUFFLElBQUk7WUFDaEIsYUFBYSxFQUFFLEdBQUcsQ0FBQyxhQUFhLENBQUMsT0FBTztZQUN4QyxpQkFBaUIsRUFBRSxJQUFJO1NBQ3hCLENBQUMsQ0FBQztRQUVILDRFQUE0RTtRQUM1RSxNQUFNLEdBQUcsR0FBRyxLQUFLLEVBQUUsS0FBSztZQUN0QixDQUFDLENBQUMsR0FBRyxDQUFDLEdBQUcsQ0FBQyxVQUFVLENBQUMsSUFBSSxFQUFFLGFBQWEsRUFBRSxFQUFFLEtBQUssRUFBRSxLQUFLLENBQUMsS0FBSyxFQUFFLENBQUM7WUFDakUsQ0FBQyxDQUFDLElBQUks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d0JBQ0UsRUFBRSxFQUFFLHlCQUF5Qjt3QkFDN0IsTUFBTSxFQUFFLCtGQUErRjtxQkFDeEc7aUJBQ0YsQ0FDRixDQUFDO1lBQ0osQ0FBQztRQUNILENBQUMsQ0FBQyxDQUFDO1FBRUgsMERBQTBEO1FBRTFELHlCQUFlLENBQUMsdUJBQXVCLENBQUMsY0FBYyxFQUFFO1lBQ3REO2dCQUNFLEVBQUUsRUFBRSxtQkFBbUI7Z0JBQ3ZCLE1BQU0sRUFBRSxvR0FBb0c7YUFDN0c7U0FDRixDQUFDLENBQUM7UUFFSCw4REFBOEQ7UUFFOUQsa0RBQWtEO1FBQ2xELElBQUksQ0FBQztZQUNILE1BQU0sc0JBQXNCLEdBQUcsSUFBSSxDQUFDLElBQUksQ0FBQyxTQUFTLENBQUMscUNBQXFDLENBQUMsQ0FBQztZQUMxRixJQUFJLHNCQUFzQixFQUFFLENBQUM7Z0JBQzNCLE1BQU0sV0FBVyxHQUFHLHNCQUFzQixDQUFDLElBQUksQ0FBQyxTQUFTLENBQUMsYUFBYSxDQUFDLENBQUM7Z0JBQ3pFLElBQUksV0FBVyxFQUFFLENBQUM7b0JBQ2hCLHlCQUFlLENBQUMsdUJBQXVCLENBQUMsV0FBVyxFQUFFO3dCQUNuRDs0QkFDRSxFQUFFLEVBQUUsbUJBQW1COzRCQUN2QixNQUFNLEVBQUUsdUVBQXVFOzRCQUMvRSxTQUFTLEVBQUUsQ0FBQyx1RkFBdUYsQ0FBQzt5QkFDckc7cUJBQ0YsQ0FBQyxDQUFDO2dCQUNMLENBQUM7WUFDSCxDQUFDO1FBQ0gsQ0FBQztRQUFDLE9BQU8sS0FBSyxFQUFFLENBQUM7WUFDZix1Q0FBdUM7WUFDdkMsT0FBTyxDQUFDLEdBQUcsQ0FBQywyREFBMkQsQ0FBQyxDQUFDO1FBQzNFLENBQUM7SUFDSCxDQUFDO0NBQ0Y7QUE3bUJELHdDQTZtQkMiLCJzb3VyY2VzQ29udGVudCI6WyJpbXBvcnQgKiBhcyBjZGsgZnJvbSAnYXdzLWNkay1saWInO1xuaW1wb3J0ICogYXMgZWMyIGZyb20gJ2F3cy1jZGstbGliL2F3cy1lYzInO1xuaW1wb3J0ICogYXMgZWNzIGZyb20gJ2F3cy1jZGstbGliL2F3cy1lY3MnO1xuaW1wb3J0ICogYXMgZWxidjIgZnJvbSAnYXdzLWNkay1saWIvYXdzLWVsYXN0aWNsb2FkYmFsYW5jaW5ndjInO1xuaW1wb3J0ICogYXMgaWFtIGZyb20gJ2F3cy1jZGstbGliL2F3cy1pYW0nO1xuaW1wb3J0ICogYXMgbG9ncyBmcm9tICdhd3MtY2RrLWxpYi9hd3MtbG9ncyc7XG5pbXBvcnQgKiBhcyBlY3IgZnJvbSAnYXdzLWNkay1saWIvYXdzLWVjcic7XG5pbXBvcnQgKiBhcyBsYW1iZGEgZnJvbSAnYXdzLWNkay1saWIvYXdzLWxhbWJkYSc7XG5pbXBvcnQgKiBhcyBzMyBmcm9tICdhd3MtY2RrLWxpYi9hd3MtczMnO1xuXG5pbXBvcnQgKiBhcyBjZXJ0aWZpY2F0ZW1hbmFnZXIgZnJvbSAnYXdzLWNkay1saWIvYXdzLWNlcnRpZmljYXRlbWFuYWdlcic7XG5pbXBvcnQgeyBDb25zdHJ1Y3QgfSBmcm9tICdjb25zdHJ1Y3RzJztcbmltcG9ydCB7IE5hZ1N1cHByZXNzaW9ucyB9IGZyb20gJ2Nkay1uYWcnO1xuXG5leHBvcnQgaW50ZXJmYWNlIE1jcFNlcnZlclN0YWNrUHJvcHMgZXh0ZW5kcyBjZGsuU3RhY2tQcm9wcyB7XG4gIHZwY0lkPzogc3RyaW5nO1xuICBkb21haW5OYW1lPzogc3RyaW5nO1xuICBjZXJ0aWZpY2F0ZUFybj86IHN0cmluZztcbiAgYWxsb3dlZElwcz86IHN0cmluZ1tdO1xuICBkb21haW5BbmFseXplckZ1bmN0aW9uPzogbGFtYmRhLkZ1bmN0aW9uO1xuICBkb2NHZW5lcmF0b3JGdW5jdGlvbj86IGxhbWJkYS5GdW5jdGlvbjtcblxufVxuXG5leHBvcnQgY2xhc3MgTWNwU2VydmVyU3RhY2sgZXh0ZW5kcyBjZGsuU3RhY2sge1xuICBwdWJsaWMgcmVhZG9ubHkgc2VydmljZVVybDogc3RyaW5nO1xuICBwdWJsaWMgcmVhZG9ubHkgbG9hZEJhbGFuY2VyOiBlbGJ2Mi5BcHBsaWNhdGlvbkxvYWRCYWxhbmNlcjtcblxuICBjb25zdHJ1Y3RvcihzY29wZTogQ29uc3RydWN0LCBpZDogc3RyaW5nLCBwcm9wcz86IE1jcFNlcnZlclN0YWNrUHJvcHMpIHtcbiAgICBzdXBlcihzY29wZSwgaWQsIHByb3BzKTtcblxuICAgIC8vIENyZWF0ZSBTMyBidWNrZXQgZm9yIEFMQiBhY2Nlc3MgbG9ncyAoc2ltcGxpZmllZClcbiAgICBjb25zdCBhbGJMb2dzQnVja2V0ID0gbmV3IHMzLkJ1Y2tldCh0aGlzLCAnTWNwU2VydmVyQWxiTG9nc0J1Y2tldCcsIHtcbiAgICAgIGJ1Y2tldE5hbWU6IGBtY3Atc2VydmVyLWFsYi1sb2dzLSR7Y2RrLkF3cy5BQ0NPVU5UX0lEfS0ke2Nkay5Bd3MuUkVHSU9OfWAsXG4gICAgICBibG9ja1B1YmxpY0FjY2VzczogczMuQmxvY2tQdWJsaWNBY2Nlc3MuQkxPQ0tfQUxMLFxuICAgICAgZW5jcnlwdGlvbjogczMuQnVja2V0RW5jcnlwdGlvbi5TM19NQU5BR0VELFxuICAgICAgZW5mb3JjZVNTTDogdHJ1ZSxcbiAgICAgIHJlbW92YWxQb2xpY3k6IGNkay5SZW1vdmFsUG9saWN5LkRFU1RST1ksXG4gICAgICBhdXRvRGVsZXRlT2JqZWN0czogdHJ1ZSxcbiAgICB9KTtcblxuICAgIC8vIENyZWF0ZSBvciB1c2UgZXhpc3RpbmcgVlBDIChubyBOQVQgR2F0ZXdheSAtIHVzaW5nIFZQQyBFbmRwb2ludHMgaW5zdGVhZClcbiAgICBjb25zdCB2cGMgPSBwcm9wcz8udnBjSWRcbiAgICAgID8gZWMyLlZwYy5mcm9tTG9va3VwKHRoaXMsICdFeGlzdGluZ1ZwYycsIHsgdnBjSWQ6IHByb3BzLnZwY0lkIH0pXG4gICAgICA6IG5ldyBlYzIuVnBjKHRoaXMsICdNY3BTZXJ2ZXJWcGMnLCB7XG4gICAgICAgIG1heEF6czogMixcbiAgICAgICAgbmF0R2F0ZXdheXM6IDAsIC8vIE5vIE5BVCBHYXRld2F5IC0gdXNpbmcgVlBDIEVuZHBvaW50c1xuICAgICAgICBzdWJuZXRDb25maWd1cmF0aW9uOiBbXG4gICAgICAgICAge1xuICAgICAgICAgICAgY2lkck1hc2s6IDI0LFxuICAgICAgICAgICAgbmFtZTogJ1ByaXZhdGUnLFxuICAgICAgICAgICAgc3VibmV0VHlwZTogZWMyLlN1Ym5ldFR5cGUuUFJJVkFURV9JU09MQVRFRCwgLy8gQ2hhbmdlZCB0byBpc29sYXRlZFxuICAgICAgICAgIH0sXG4gICAgICAgICAge1xuICAgICAgICAgICAgY2lkck1hc2s6IDI0LFxuICAgICAgICAgICAgbmFtZTogJ1B1YmxpYycsXG4gICAgICAgICAgICBzdWJuZXRUeXBlOiBlYzIuU3VibmV0VHlwZS5QVUJMSUMsXG4gICAgICAgICAgfSxcbiAgICAgICAgXSxcbiAgICAgIH0pO1xuXG4gICAgLy8gU3VwcHJlc3MgVlBDIEZsb3cgTG9ncyB3YXJuaW5nIC0gbm90IG5lZWRlZCBmb3IgdGhpcyBzaW1wbGUgTUNQIHNlcnZlciB1c2UgY2FzZVxuICAgIGlmICghcHJvcHM/LnZwY0lkKSB7XG4gICAgICBOYWdTdXBwcmVzc2lvbnMuYWRkUmVzb3VyY2VTdXBwcmVzc2lvbnMoXG4gICAgICAgIHZwYyxcbiAgICAgICAgW1xuICAgICAgICAgIHtcbiAgICAgICAgICAgIGlkOiAnQXdzU29sdXRpb25zLVZQQzcnLFxuICAgICAgICAgICAgcmVhc29uOiAnVlBDIEZsb3cgTG9ncyBub3QgcmVxdWlyZWQgZm9yIHNpbXBsZSBNQ1Agc2VydmVyIGRlcGxveW1lbnQuIENhbiBiZSBlbmFibGVkIGxhdGVyIGlmIGRldGFpbGVkIG5ldHdvcmsgbW9uaXRvcmluZyBpcyBuZWVkZWQuJyxcbiAgICAgICAgICB9LFxuICAgICAgICBdXG4gICAgICApO1xuICAgIH1cblxuICAgIC8vIENyZWF0ZSBWUEMgRW5kcG9pbnRzIHRvIHJlcGxhY2UgTkFUIEdhdGV3YXkgZnVuY3Rpb25hbGl0eVxuICAgIC8vIFMzIEdhdGV3YXkgRW5kcG9pbnQgKEZSRUUgLSBmb3IgQUxCIGxvZ3MgYW5kIGdlbmVyYWwgUzMgYWNjZXNzKVxuICAgIG5ldyBlYzIuR2F0ZXdheVZwY0VuZHBvaW50KHRoaXMsICdTM0VuZHBvaW50Jywge1xuICAgICAgdnBjLFxuICAgICAgc2VydmljZTogZWMyLkdhdGV3YXlWcGNFbmRwb2ludEF3c1NlcnZpY2UuUzMsXG4gICAgICBzdWJuZXRzOiBbXG4gICAgICAgIHtcbiAgICAgICAgICBzdWJuZXRUeXBlOiBlYzIuU3VibmV0VHlwZS5QUklWQVRFX0lTT0xBVEVELFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICB9KTtcblxuICAgIC8vIEVDUiBBUEkgRW5kcG9pbnQgKGZvciBEb2NrZXIgcmVnaXN0cnkgQVBJIGNhbGxzKVxuICAgIGNvbnN0IGVjckFwaUVuZHBvaW50ID0gbmV3IGVjMi5JbnRlcmZhY2VWcGNFbmRwb2ludCh0aGlzLCAnRWNyQXBpRW5kcG9pbnQnLCB7XG4gICAgICB2cGMsXG4gICAgICBzZXJ2aWNlOiBlYzIuSW50ZXJmYWNlVnBjRW5kcG9pbnRBd3NTZXJ2aWNlLkVDUixcbiAgICAgIHN1Ym5ldHM6IHtcbiAgICAgICAgc3VibmV0VHlwZTogZWMyLlN1Ym5ldFR5cGUuUFJJVkFURV9JU09MQVRFRCxcbiAgICAgIH0sXG4gICAgICBwcml2YXRlRG5zRW5hYmxlZDogdHJ1ZSxcbiAgICB9KTtcblxuICAgIC8vIEVDUiBEb2NrZXIgRW5kcG9pbnQgKGZvciBEb2NrZXIgaW1hZ2UgcHVsbHMpXG4gICAgY29uc3QgZWNyRGtyRW5kcG9pbnQgPSBuZXcgZWMyLkludGVyZmFjZVZwY0VuZHBvaW50KHRoaXMsICdFY3JEa3JFbmRwb2ludCcsIHtcbiAgICAgIHZwYyxcbiAgICAgIHNlcnZpY2U6IGVjMi5JbnRlcmZhY2VWcGNFbmRwb2ludEF3c1NlcnZpY2UuRUNSX0RPQ0tFUixcbiAgICAgIHN1Ym5ldHM6IHtcbiAgICAgICAgc3VibmV0VHlwZTogZWMyLlN1Ym5ldFR5cGUuUFJJVkFURV9JU09MQVRFRCxcbiAgICAgIH0sXG4gICAgICBwcml2YXRlRG5zRW5hYmxlZDogdHJ1ZSxcbiAgICB9KTtcblxuICAgIC8vIENsb3VkV2F0Y2ggTG9ncyBFbmRwb2ludCAoZm9yIGFwcGxpY2F0aW9uIGxvZ2dpbmcpXG4gICAgY29uc3QgbG9nc0VuZHBvaW50ID0gbmV3IGVjMi5JbnRlcmZhY2VWcGNFbmRwb2ludCh0aGlzLCAnTG9nc0VuZHBvaW50Jywge1xuICAgICAgdnBjLFxuICAgICAgc2VydmljZTogZWMyLkludGVyZmFjZVZwY0VuZHBvaW50QXdzU2VydmljZS5DTE9VRFdBVENIX0xPR1MsXG4gICAgICBzdWJuZXRzOiB7XG4gICAgICAgIHN1Ym5ldFR5cGU6IGVjMi5TdWJuZXRUeXBlLlBSSVZBVEVfSVNPTEFURUQsXG4gICAgICB9LFxuICAgICAgcHJpdmF0ZURuc0VuYWJsZWQ6IHRydWUsXG4gICAgfSk7XG5cbiAgICAvLyBCZWRyb2NrIFJ1bnRpbWUgRW5kcG9pbnQgKGZvciBBSSBtb2RlbCBhY2Nlc3MpXG4gICAgY29uc3QgYmVkcm9ja0VuZHBvaW50ID0gbmV3IGVjMi5JbnRlcmZhY2VWcGNFbmRwb2ludCh0aGlzLCAnQmVkcm9ja0VuZHBvaW50Jywge1xuICAgICAgdnBjLFxuICAgICAgc2VydmljZTogbmV3IGVjMi5JbnRlcmZhY2VWcGNFbmRwb2ludFNlcnZpY2UoYGNvbS5hbWF6b25hd3MuJHtjZGsuQXdzLlJFR0lPTn0uYmVkcm9jay1ydW50aW1lYCksXG4gICAgICBzdWJuZXRzOiB7XG4gICAgICAgIHN1Ym5ldFR5cGU6IGVjMi5TdWJuZXRUeXBlLlBSSVZBVEVfSVNPTEFURUQsXG4gICAgICB9LFxuICAgICAgcHJpdmF0ZURuc0VuYWJsZWQ6IHRydWUsXG4gICAgfSk7XG5cblxuXG4gICAgLy8gU1NNIEVuZHBvaW50IChmb3IgcGFyYW1ldGVyIHN0b3JlIHNlY3JldHMpXG4gICAgY29uc3Qgc3NtRW5kcG9pbnQgPSBuZXcgZWMyLkludGVyZmFjZVZwY0VuZHBvaW50KHRoaXMsICdTc21FbmRwb2ludCcsIHtcbiAgICAgIHZwYyxcbiAgICAgIHNlcnZpY2U6IGVjMi5JbnRlcmZhY2VWcGNFbmRwb2ludEF3c1NlcnZpY2UuU1NNLFxuICAgICAgc3VibmV0czoge1xuICAgICAgICBzdWJuZXRUeXBlOiBlYzIuU3VibmV0VHlwZS5QUklWQVRFX0lTT0xBVEVELFxuICAgICAgfSxcbiAgICAgIHByaXZhdGVEbnNFbmFibGVkOiB0cnVlLFxuICAgIH0pO1xuXG4gICAgLy8gTGFtYmRhIEVuZHBvaW50IChmb3IgTGFtYmRhIGZ1bmN0aW9uIGludm9jYXRpb24pXG4gICAgY29uc3QgbGFtYmRhRW5kcG9pbnQgPSBuZXcgZWMyLkludGVyZmFjZVZwY0VuZHBvaW50KHRoaXMsICdMYW1iZGFFbmRwb2ludCcsIHtcbiAgICAgIHZwYyxcbiAgICAgIHNlcnZpY2U6IGVjMi5JbnRlcmZhY2VWcGNFbmRwb2ludEF3c1NlcnZpY2UuTEFNQkRBLFxuICAgICAgc3VibmV0czoge1xuICAgICAgICBzdWJuZXRUeXBlOiBlYzIuU3VibmV0VHlwZS5QUklWQVRFX0lTT0xBVEVELFxuICAgICAgfSxcbiAgICAgIHByaXZhdGVEbnNFbmFibGVkOiB0cnVlLFxuICAgIH0pO1xuXG4gICAgLy8gQ3JlYXRlIEVDUiByZXBvc2l0b3J5IGZvciB0aGUgTUNQIHNlcnZlciBpbWFnZSB3aXRoIHVuaXF1ZSBuYW1lXG4gICAgY29uc3QgZWNyUmVwb3NpdG9yeSA9IG5ldyBlY3IuUmVwb3NpdG9yeSh0aGlzLCAnTWNwU2VydmVyUmVwb3NpdG9yeScsIHtcbiAgICAgIHJlcG9zaXRvcnlOYW1lOiBgbWNwLXNlcnZlci0ke2Nkay5Bd3MuQUNDT1VOVF9JRH1gLFxuICAgICAgaW1hZ2VTY2FuT25QdXNoOiB0cnVlLFxuICAgICAgbGlmZWN5Y2xlUnVsZXM6IFtcbiAgICAgICAge1xuICAgICAgICAgIG1heEltYWdlQ291bnQ6IDEwLFxuICAgICAgICAgIHRhZ1N0YXR1czogZWNyLlRhZ1N0YXR1cy5VTlRBR0dFRCxcbiAgICAgICAgfSxcbiAgICAgIF0sXG4gICAgfSk7XG5cbiAgICAvLyBDcmVhdGUgRUNTIGNsdXN0ZXIgd2l0aCBDb250YWluZXIgSW5zaWdodHNcbiAgICBjb25zdCBjbHVzdGVyID0gbmV3IGVjcy5DbHVzdGVyKHRoaXMsICdNY3BTZXJ2ZXJDbHVzdGVyJywge1xuICAgICAgdnBjLFxuICAgICAgY2x1c3Rlck5hbWU6ICdtY3Atc2VydmVyLWNsdXN0ZXInLFxuICAgICAgZW5hYmxlRmFyZ2F0ZUNhcGFjaXR5UHJvdmlkZXJzOiB0cnVlLFxuICAgIH0pO1xuXG4gICAgLy8gRW5hYmxlIENvbnRhaW5lciBJbnNpZ2h0cyBtYW51YWxseSBzaW5jZSB0aGUgcHJvcGVydHkgaXMgZGVwcmVjYXRlZFxuICAgIGNvbnN0IGNmbkNsdXN0ZXIgPSBjbHVzdGVyLm5vZGUuZGVmYXVsdENoaWxkIGFzIGVjcy5DZm5DbHVzdGVyO1xuICAgIGNmbkNsdXN0ZXIuY2x1c3RlclNldHRpbmdzID0gW1xuICAgICAge1xuICAgICAgICBuYW1lOiAnY29udGFpbmVySW5zaWdodHMnLFxuICAgICAgICB2YWx1ZTogJ2VuYWJsZWQnLFxuICAgICAgfSxcbiAgICBdO1xuXG4gICAgLy8gQ3JlYXRlIENsb3VkV2F0Y2ggbG9nIGdyb3VwXG4gICAgY29uc3QgbG9nR3JvdXAgPSBuZXcgbG9ncy5Mb2dHcm91cCh0aGlzLCAnTWNwU2VydmVyTG9nR3JvdXAnLCB7XG4gICAgICBsb2dHcm91cE5hbWU6ICcvZWNzL21jcC1zZXJ2ZXInLFxuICAgICAgcmV0ZW50aW9uOiBsb2dzLlJldGVudGlvbkRheXMuT05FX1dFRUssXG4gICAgICByZW1vdmFsUG9saWN5OiBjZGsuUmVtb3ZhbFBvbGljeS5ERVNUUk9ZLFxuICAgIH0pO1xuXG4gICAgLy8gQ3JlYXRlIGN1c3RvbSBtYW5hZ2VkIHBvbGljeSBmb3IgdGFzayBleGVjdXRpb24gcm9sZVxuICAgIGNvbnN0IHRhc2tFeGVjdXRpb25Qb2xpY3kgPSBuZXcgaWFtLk1hbmFnZWRQb2xpY3kodGhpcywgJ01jcFNlcnZlclRhc2tFeGVjdXRpb25Qb2xpY3knLCB7XG4gICAgICBzdGF0ZW1lbnRzOiBbXG4gICAgICAgIG5ldyBpYW0uUG9saWN5U3RhdGVtZW50KHtcbiAgICAgICAgICBlZmZlY3Q6IGlhbS5FZmZlY3QuQUxMT1csXG4gICAgICAgICAgYWN0aW9uczogW1xuICAgICAgICAgICAgJ2VjcjpHZXRBdXRob3JpemF0aW9uVG9rZW4nLFxuICAgICAgICAgICAgJ2VjcjpCYXRjaENoZWNrTGF5ZXJBdmFpbGFiaWxpdHknLFxuICAgICAgICAgICAgJ2VjcjpHZXREb3dubG9hZFVybEZvckxheWVyJyxcbiAgICAgICAgICAgICdlY3I6QmF0Y2hHZXRJbWFnZScsXG4gICAgICAgICAgXSxcbiAgICAgICAgICByZXNvdXJjZXM6IFtlY3JSZXBvc2l0b3J5LnJlcG9zaXRvcnlBcm5dLFxuICAgICAgICB9KSxcbiAgICAgICAgbmV3IGlhbS5Qb2xpY3lTdGF0ZW1lbnQoe1xuICAgICAgICAgIGVmZmVjdDogaWFtLkVmZmVjdC5BTExPVyxcbiAgICAgICAgICBhY3Rpb25zOiBbXG4gICAgICAgICAgICAnbG9nczpDcmVhdGVMb2dTdHJlYW0nLFxuICAgICAgICAgICAgJ2xvZ3M6UHV0TG9nRXZlbnRzJyxcbiAgICAgICAgICBdLFxuICAgICAgICAgIHJlc291cmNlczogW2xvZ0dyb3VwLmxvZ0dyb3VwQXJuXSxcbiAgICAgICAgfSksXG4gICAgICBdLFxuICAgIH0pO1xuXG4gICAgLy8gQ3JlYXRlIHRhc2sgZXhlY3V0aW9uIHJvbGVcbiAgICBjb25zdCB0YXNrRXhlY3V0aW9uUm9sZSA9IG5ldyBpYW0uUm9sZSh0aGlzLCAnTWNwU2VydmVyVGFza0V4ZWN1dGlvblJvbGUnLCB7XG4gICAgICBhc3N1bWVkQnk6IG5ldyBpYW0uU2VydmljZVByaW5jaXBhbCgnZWNzLXRhc2tzLmFtYXpvbmF3cy5jb20nKSxcbiAgICAgIG1hbmFnZWRQb2xpY2llczogW3Rhc2tFeGVjdXRpb25Qb2xpY3ldLFxuICAgIH0pO1xuXG5cbiAgICAvLyBDcmVhdGUgdGFzayByb2xlIHdpdGggbmVjZXNzYXJ5IHBlcm1pc3Npb25zXG4gICAgY29uc3QgdGFza1JvbGUgPSBuZXcgaWFtLlJvbGUodGhpcywgJ01jcFNlcnZlclRhc2tSb2xlJywge1xuICAgICAgYXNzdW1lZEJ5OiBuZXcgaWFtLlNlcnZpY2VQcmluY2lwYWwoJ2Vjcy10YXNrcy5hbWF6b25hd3MuY29tJyksXG4gICAgICBpbmxpbmVQb2xpY2llczoge1xuICAgICAgICBNY3BTZXJ2ZXJQb2xpY3k6IG5ldyBpYW0uUG9saWN5RG9jdW1lbnQoe1xuICAgICAgICAgIHN0YXRlbWVudHM6IFtcbiAgICAgICAgICAgIG5ldyBpYW0uUG9saWN5U3RhdGVtZW50KHtcbiAgICAgICAgICAgICAgZWZmZWN0OiBpYW0uRWZmZWN0LkFMTE9XLFxuICAgICAgICAgICAgICBhY3Rpb25zOiBbXG4gICAgICAgICAgICAgICAgJ2JlZHJvY2s6SW52b2tlTW9kZWwnLFxuICAgICAgICAgICAgICAgICdiZWRyb2NrOkludm9rZU1vZGVsV2l0aFJlc3BvbnNlU3RyZWFtJyxcbiAgICAgICAgICAgICAgXSxcbiAgICAgICAgICAgICAgcmVzb3VyY2VzOiBbXG4gICAgICAgICAgICAgICAgYGFybjphd3M6YmVkcm9jazoke2Nkay5Bd3MuUkVHSU9OfTo6Zm91bmRhdGlvbi1tb2RlbC8qYCxcbiAgICAgICAgICAgICAgICBgYXJuOmF3czpiZWRyb2NrOio6OmZvdW5kYXRpb24tbW9kZWwvKmAsXG4gICAgICAgICAgICAgICAgYGFybjphd3M6YmVkcm9jazoke2Nkay5Bd3MuUkVHSU9OfToke2Nkay5Bd3MuQUNDT1VOVF9JRH06aW5mZXJlbmNlLXByb2ZpbGUvKmAsXG4gICAgICAgICAgICAgIF0sXG4gICAgICAgICAgICB9KSxcblxuICAgICAgICAgICAgbmV3IGlhbS5Qb2xpY3lTdGF0ZW1lbnQoe1xuICAgICAgICAgICAgICBlZmZlY3Q6IGlhbS5FZmZlY3QuQUxMT1csXG4gICAgICAgICAgICAgIGFjdGlvbnM6IFtcbiAgICAgICAgICAgICAgICAnbGFtYmRhOkludm9rZUZ1bmN0aW9uJyxcbiAgICAgICAgICAgICAgXSxcbiAgICAgICAgICAgICAgcmVzb3VyY2VzOiBbXG4gICAgICAgICAgICAgICAgLi4uKHByb3BzPy5kb21haW5BbmFseXplckZ1bmN0aW9uID8gW3Byb3BzLmRvbWFpbkFuYWx5emVyRnVuY3Rpb24uZnVuY3Rpb25Bcm5dIDogW10pLFxuICAgICAgICAgICAgICAgIC4uLihwcm9wcz8uZG9jR2VuZXJhdG9yRnVuY3Rpb24gPyBbcHJvcHMuZG9jR2VuZXJhdG9yRnVuY3Rpb24uZnVuY3Rpb25Bcm5dIDogW10pLFxuICAgICAgICAgICAgICBdLFxuICAgICAgICAgICAgfSksXG4gICAgICAgICAgICAvLyBTMyBwZXJtaXNzaW9ucyByZW1vdmVkIC0gTGFtYmRhIGZ1bmN0aW9ucyBub3cgcmV0dXJuIHJlc3BvbnNlcyBkaXJlY3RseVxuICAgICAgICAgICAgbmV3IGlhbS5Qb2xpY3lTdGF0ZW1lbnQoe1xuICAgICAgICAgICAgICBlZmZlY3Q6IGlhbS5FZmZlY3QuQUxMT1csXG4gICAgICAgICAgICAgIGFjdGlvbnM6IFtcbiAgICAgICAgICAgICAgICAnbG9nczpDcmVhdGVMb2dTdHJlYW0nLFxuICAgICAgICAgICAgICAgICdsb2dzOlB1dExvZ0V2ZW50cycsXG4gICAgICAgICAgICAgIF0sXG4gICAgICAgICAgICAgIHJlc291cmNlczogW2xvZ0dyb3VwLmxvZ0dyb3VwQXJuXSxcbiAgICAgICAgICAgIH0pLFxuICAgICAgICAgIF0sXG4gICAgICAgIH0pLFxuICAgICAgfSxcbiAgICB9KTtcblxuICAgIC8vIENyZWF0ZSBGYXJnYXRlIHRhc2sgZGVmaW5pdGlvbiB3aXRoIGV4cGxpY2l0IHg4Nl82NCBhcmNoaXRlY3R1cmVcbiAgICBjb25zdCB0YXNrRGVmaW5pdGlvbiA9IG5ldyBlY3MuRmFyZ2F0ZVRhc2tEZWZpbml0aW9uKHRoaXMsICdNY3BTZXJ2ZXJUYXNrRGVmaW5pdGlvbicsIHtcbiAgICAgIG1lbW9yeUxpbWl0TWlCOiAxMDI0LFxuICAgICAgY3B1OiA1MTIsXG4gICAgICBleGVjdXRpb25Sb2xlOiB0YXNrRXhlY3V0aW9uUm9sZSxcbiAgICAgIHRhc2tSb2xlOiB0YXNrUm9sZSxcbiAgICAgIHJ1bnRpbWVQbGF0Zm9ybToge1xuICAgICAgICBjcHVBcmNoaXRlY3R1cmU6IGVjcy5DcHVBcmNoaXRlY3R1cmUuWDg2XzY0LFxuICAgICAgICBvcGVyYXRpbmdTeXN0ZW1GYW1pbHk6IGVjcy5PcGVyYXRpbmdTeXN0ZW1GYW1pbHkuTElOVVgsXG4gICAgICB9LFxuICAgIH0pO1xuXG4gICAgLy8gQWRkIGNvbnRhaW5lciB0byB0YXNrIGRlZmluaXRpb24gKHVzaW5nIHNlY3JldHMgaW5zdGVhZCBvZiBlbnZpcm9ubWVudCB2YXJpYWJsZXMpXG4gICAgY29uc3QgY29udGFpbmVyID0gdGFza0RlZmluaXRpb24uYWRkQ29udGFpbmVyKCdNY3BTZXJ2ZXJDb250YWluZXInLCB7XG4gICAgICBpbWFnZTogZWNzLkNvbnRhaW5lckltYWdlLmZyb21FY3JSZXBvc2l0b3J5KGVjclJlcG9zaXRvcnksICdsYXRlc3QnKSxcbiAgICAgIGxvZ2dpbmc6IGVjcy5Mb2dEcml2ZXJzLmF3c0xvZ3Moe1xuICAgICAgICBzdHJlYW1QcmVmaXg6ICdtY3Atc2VydmVyJyxcbiAgICAgICAgbG9nR3JvdXA6IGxvZ0dyb3VwLFxuICAgICAgfSksXG4gICAgICAvLyBVc2UgZW52aXJvbm1lbnQgdmFyaWFibGVzIGZvciBjb25maWd1cmF0aW9uIC0gdXBkYXRlZCBmb3IgVVMgaW5mZXJlbmNlIHByb2ZpbGVcbiAgICAgIGVudmlyb25tZW50OiB7XG4gICAgICAgIE5PREVfRU5WOiBwcm9jZXNzLmVudi5OT0RFX0VOViB8fCAncHJvZHVjdGlvbicsXG4gICAgICAgIFBPUlQ6IHByb2Nlc3MuZW52LlBPUlQgfHwgJzMwMDAnLFxuICAgICAgICBNQ1BfUE9SVDogcHJvY2Vzcy5lbnYuTUNQX1BPUlQgfHwgJzMwMDEnLFxuICAgICAgICBBV1NfUkVHSU9OOiBjZGsuQXdzLlJFR0lPTixcbiAgICAgICAgQkVEUk9DS19SRUdJT046IHByb2Nlc3MuZW52LkJFRFJPQ0tfUkVHSU9OIHx8ICd1cy1lYXN0LTEnLFxuICAgICAgICBNT0RFTF9JRDogcHJvY2Vzcy5lbnYuTU9ERUxfSUQgfHwgJ3VzLmFudGhyb3BpYy5jbGF1ZGUtMy03LXNvbm5ldC0yMDI1MDIxOS12MTowJyxcbiAgICAgICAgLy8gQlVDS0VUX05BTUUgcmVtb3ZlZCAtIExhbWJkYSBmdW5jdGlvbnMgbm93IHJldHVybiByZXNwb25zZXMgZGlyZWN0bHlcbiAgICAgICAgRE9NQUlOX0FOQUxZWkVSX0xBTUJEQV9BUk46IHByb3BzPy5kb21haW5BbmFseXplckZ1bmN0aW9uPy5mdW5jdGlvbkFybiB8fCAnJyxcbiAgICAgICAgRE9DX0dFTkVSQVRPUl9MQU1CREFfQVJOOiBwcm9wcz8uZG9jR2VuZXJhdG9yRnVuY3Rpb24/LmZ1bmN0aW9uQXJuIHx8ICcnLFxuXG4gICAgICAgIE1DUF9TRVJWRVJfTkFNRTogcHJvY2Vzcy5lbnYuTUNQX1NFUlZFUl9OQU1FIHx8ICdvcGVuYXBpLWRvY3VtZW50YXRpb24tbWNwLXByb2QnLFxuICAgICAgICBNQ1BfU0VSVkVSX1ZFUlNJT046IHByb2Nlc3MuZW52Lk1DUF9TRVJWRVJfVkVSU0lPTiB8fCAnMS4wLjEnLFxuICAgICAgICBMT0dfTEVWRUw6IHByb2Nlc3MuZW52LkxPR19MRVZFTCB8fCAnaW5mbycsXG4gICAgICAgIEhFQUxUSF9DSEVDS19FTkFCTEVEOiBwcm9jZXNzLmVudi5IRUFMVEhfQ0hFQ0tfRU5BQkxFRCB8fCAndHJ1ZScsXG4gICAgICAgIEVOQUJMRV9SRVFVRVNUX0xPR0dJTkc6IHByb2Nlc3MuZW52LkVOQUJMRV9SRVFVRVNUX0xPR0dJTkcgfHwgJ3RydWUnLFxuICAgICAgfSxcbiAgICAgIGhlYWx0aENoZWNrOiB7XG4gICAgICAgIGNvbW1hbmQ6IFsnQ01ELVNIRUxMJywgJ25vZGUgLWUgXCJyZXF1aXJlKFxcJ2h0dHBcXCcpLmdldChcXCdodHRwOi8vbG9jYWxob3N0OjMwMDAvaGVhbHRoXFwnLCAocmVzKSA9PiB7IHByb2Nlc3MuZXhpdChyZXMuc3RhdHVzQ29kZSA9PT0gMjAwID8gMCA6IDEpIH0pXCIgfHwgZXhpdCAxJ10sXG4gICAgICAgIGludGVydmFsOiBjZGsuRHVyYXRpb24uc2Vjb25kcygzMCksXG4gICAgICAgIHRpbWVvdXQ6IGNkay5EdXJhdGlvbi5zZWNvbmRzKDUpLFxuICAgICAgICByZXRyaWVzOiAzLFxuICAgICAgICBzdGFydFBlcmlvZDogY2RrLkR1cmF0aW9uLnNlY29uZHMoNjApLFxuICAgICAgfSxcbiAgICB9KTtcblxuICAgIGNvbnRhaW5lci5hZGRQb3J0TWFwcGluZ3Moe1xuICAgICAgY29udGFpbmVyUG9ydDogMzAwMSxcbiAgICAgIHByb3RvY29sOiBlY3MuUHJvdG9jb2wuVENQLFxuICAgIH0pO1xuXG4gICAgLy8gQWRkIHBvcnQgbWFwcGluZyBmb3IgaGVhbHRoIGVuZHBvaW50XG4gICAgY29udGFpbmVyLmFkZFBvcnRNYXBwaW5ncyh7XG4gICAgICBjb250YWluZXJQb3J0OiAzMDAwLFxuICAgICAgcHJvdG9jb2w6IGVjcy5Qcm90b2NvbC5UQ1AsXG4gICAgfSk7XG5cbiAgICAvLyBDcmVhdGUgc2VjdXJpdHkgZ3JvdXAgZm9yIEVDUyBzZXJ2aWNlXG4gICAgY29uc3QgZWNzU2VjdXJpdHlHcm91cCA9IG5ldyBlYzIuU2VjdXJpdHlHcm91cCh0aGlzLCAnTWNwU2VydmVyRWNzU2VjdXJpdHlHcm91cCcsIHtcbiAgICAgIHZwYyxcbiAgICAgIGRlc2NyaXB0aW9uOiAnU2VjdXJpdHkgZ3JvdXAgZm9yIE1DUCBTZXJ2ZXIgRUNTIHNlcnZpY2UnLFxuICAgICAgYWxsb3dBbGxPdXRib3VuZDogdHJ1ZSxcbiAgICB9KTtcblxuICAgIC8vIENyZWF0ZSBzZWN1cml0eSBncm91cCBmb3IgbG9hZCBiYWxhbmNlclxuICAgIGNvbnN0IGFsYlNlY3VyaXR5R3JvdXAgPSBuZXcgZWMyLlNlY3VyaXR5R3JvdXAodGhpcywgJ01jcFNlcnZlckFsYlNlY3VyaXR5R3JvdXAnLCB7XG4gICAgICB2cGMsXG4gICAgICBkZXNjcmlwdGlvbjogJ1NlY3VyaXR5IGdyb3VwIGZvciBNQ1AgU2VydmVyIEFMQicsXG4gICAgICBhbGxvd0FsbE91dGJvdW5kOiB0cnVlLFxuICAgIH0pO1xuXG4gICAgLy8gQWxsb3cgaW5ib3VuZCB0cmFmZmljIGZyb20gQUxCIHRvIEVDUyBvbiBib3RoIHBvcnRzXG4gICAgZWNzU2VjdXJpdHlHcm91cC5hZGRJbmdyZXNzUnVsZShcbiAgICAgIGFsYlNlY3VyaXR5R3JvdXAsXG4gICAgICBlYzIuUG9ydC50Y3AoMzAwMSksXG4gICAgICAnQWxsb3cgQUxCIHRvIHJlYWNoIE1DUCBzZXJ2ZXIgcG9ydCdcbiAgICApO1xuXG4gICAgZWNzU2VjdXJpdHlHcm91cC5hZGRJbmdyZXNzUnVsZShcbiAgICAgIGFsYlNlY3VyaXR5R3JvdXAsXG4gICAgICBlYzIuUG9ydC50Y3AoMzAwMCksXG4gICAgICAnQWxsb3cgQUxCIHRvIHJlYWNoIGhlYWx0aCBjaGVjayBwb3J0J1xuICAgICk7XG5cbiAgICAvLyBBbGxvdyBpbmJvdW5kIEhUVFAgdHJhZmZpYyB0byBBTEIgZnJvbSBzcGVjaWZpYyBJUHMgb25seVxuICAgIGNvbnN0IGFsbG93ZWRJcHMgPSBwcm9wcz8uYWxsb3dlZElwcyB8fCBbXTtcblxuICAgIGlmIChhbGxvd2VkSXBzLmxlbmd0aCA9PT0gMCkge1xuICAgICAgLy8gSWYgbm8gSVBzIHNwZWNpZmllZCwgd2FybiBhbmQgcmVxdWlyZSBleHBsaWNpdCBJUCBjb25maWd1cmF0aW9uXG4gICAgICBjb25zb2xlLndhcm4oJ1dBUk5JTkc6IE5vIGFsbG93ZWQgSVBzIHNwZWNpZmllZC4gQUxCIGFjY2VzcyB3aWxsIGJlIHJlc3RyaWN0ZWQuJyk7XG4gICAgICBjb25zb2xlLndhcm4oJ1VzZSAtLWFsbG93ZWQtaXBzIHBhcmFtZXRlciBvciBzZXQgYWxsb3dlZElwcyBpbiBzdGFjayBwcm9wcyB0byBhbGxvdyBhY2Nlc3MuJyk7XG4gICAgICAvLyBEb24ndCBhZGQgYW55IGluZ3Jlc3MgcnVsZXMgLSBBTEIgd2lsbCBiZSBpbmFjY2Vzc2libGUgdW50aWwgSVBzIGFyZSBzcGVjaWZpZWRcbiAgICB9IGVsc2Uge1xuICAgICAgLy8gQWRkIHJ1bGVzIGZvciBlYWNoIGFsbG93ZWQgSVBcbiAgICAgIGFsbG93ZWRJcHMuZm9yRWFjaCgoaXApID0+IHtcbiAgICAgICAgYWxiU2VjdXJpdHlHcm91cC5hZGRJbmdyZXNzUnVsZShcbiAgICAgICAgICBlYzIuUGVlci5pcHY0KGlwKSxcbiAgICAgICAgICBlYzIuUG9ydC50Y3AoODApLFxuICAgICAgICAgIGBBbGxvdyBIVFRQIHRyYWZmaWMgZnJvbSAke2lwfWBcbiAgICAgICAgKTtcblxuICAgICAgICAvLyBBbHNvIGFsbG93IEhUVFBTIGluIGNhc2Ugd2UgYWRkIGNlcnRpZmljYXRlcyBsYXRlclxuICAgICAgICBhbGJTZWN1cml0eUdyb3VwLmFkZEluZ3Jlc3NSdWxlKFxuICAgICAgICAgIGVjMi5QZWVyLmlwdjQoaXApLFxuICAgICAgICAgIGVjMi5Qb3J0LnRjcCg0NDMpLFxuICAgICAgICAgIGBBbGxvdyBIVFRQUyB0cmFmZmljIGZyb20gJHtpcH1gXG4gICAgICAgICk7XG4gICAgICB9KTtcblxuICAgICAgY29uc29sZS5sb2coYEFMQiBhY2Nlc3MgcmVzdHJpY3RlZCB0byBJUHM6ICR7YWxsb3dlZElwcy5qb2luKCcsICcpfWApO1xuICAgIH1cblxuICAgIC8vIENyZWF0ZSB0aGUgQUxCIGZpcnN0IHNvIHdlIGNhbiBnZXQgaXRzIEROUyBuYW1lXG4gICAgdGhpcy5sb2FkQmFsYW5jZXIgPSBuZXcgZWxidjIuQXBwbGljYXRpb25Mb2FkQmFsYW5jZXIodGhpcywgJ01jcFNlcnZlckxvYWRCYWxhbmNlcicsIHtcbiAgICAgIHZwYyxcbiAgICAgIGludGVybmV0RmFjaW5nOiB0cnVlLCAvLyBQdWJsaWMgQUxCIGZvciB3ZWIgYXBwIGFjY2Vzc1xuICAgICAgc2VjdXJpdHlHcm91cDogYWxiU2VjdXJpdHlHcm91cCxcbiAgICAgIHZwY1N1Ym5ldHM6IHtcbiAgICAgICAgc3VibmV0VHlwZTogZWMyLlN1Ym5ldFR5cGUuUFVCTElDLFxuICAgICAgfSxcbiAgICB9KTtcblxuICAgIC8vIFNldCBBTEIgaWRsZSB0aW1lb3V0IHRvIDIwIG1pbnV0ZXMgKDEyMDAgc2Vjb25kcykgZm9yIGxvbmctcnVubmluZyBvcGVyYXRpb25zXG4gICAgY29uc3QgY2ZuTG9hZEJhbGFuY2VyID0gdGhpcy5sb2FkQmFsYW5jZXIubm9kZS5kZWZhdWx0Q2hpbGQgYXMgZWxidjIuQ2ZuTG9hZEJhbGFuY2VyO1xuICAgIGNmbkxvYWRCYWxhbmNlci5hZGRQcm9wZXJ0eU92ZXJyaWRlKCdMb2FkQmFsYW5jZXJBdHRyaWJ1dGVzJywgW1xuICAgICAge1xuICAgICAgICBLZXk6ICdpZGxlX3RpbWVvdXQudGltZW91dF9zZWNvbmRzJyxcbiAgICAgICAgVmFsdWU6ICcxMjAwJ1xuICAgICAgfVxuICAgIF0pO1xuXG4gICAgLy8gRW5hYmxlIEFMQiBhY2Nlc3MgbG9nc1xuICAgIHRoaXMubG9hZEJhbGFuY2VyLmxvZ0FjY2Vzc0xvZ3MoYWxiTG9nc0J1Y2tldCwgJ21jcC1zZXJ2ZXItYWxiJyk7XG5cbiAgICAvLyBDcmVhdGUgRmFyZ2F0ZSBzZXJ2aWNlIHdpdGggbG93ZXIgZGVzaXJlZCBjb3VudCBpbml0aWFsbHlcbiAgICBjb25zdCBzZXJ2aWNlID0gbmV3IGVjcy5GYXJnYXRlU2VydmljZSh0aGlzLCAnTWNwU2VydmVyU2VydmljZScsIHtcbiAgICAgIGNsdXN0ZXIsXG4gICAgICB0YXNrRGVmaW5pdGlvbixcbiAgICAgIGRlc2lyZWRDb3VudDogMCwgLy8gU3RhcnQgd2l0aCAwLCBzY2FsZSB1cCBhZnRlciBpbWFnZSBpcyBwdXNoZWRcbiAgICAgIGFzc2lnblB1YmxpY0lwOiBmYWxzZSxcbiAgICAgIHNlY3VyaXR5R3JvdXBzOiBbZWNzU2VjdXJpdHlHcm91cF0sXG4gICAgICB2cGNTdWJuZXRzOiB7XG4gICAgICAgIHN1Ym5ldFR5cGU6IGVjMi5TdWJuZXRUeXBlLlBSSVZBVEVfSVNPTEFURUQsXG4gICAgICB9LFxuICAgICAgZW5hYmxlRXhlY3V0ZUNvbW1hbmQ6IHRydWUsXG4gICAgICBtaW5IZWFsdGh5UGVyY2VudDogMCwgLy8gQWxsb3cgc2NhbGluZyBmcm9tIDBcbiAgICAgIG1heEhlYWx0aHlQZXJjZW50OiAyMDAsXG4gICAgfSk7XG5cbiAgICAvLyBDcmVhdGUgdGFyZ2V0IGdyb3VwXG4gICAgY29uc3QgdGFyZ2V0R3JvdXAgPSBuZXcgZWxidjIuQXBwbGljYXRpb25UYXJnZXRHcm91cCh0aGlzLCAnTWNwU2VydmVyVGFyZ2V0R3JvdXAnLCB7XG4gICAgICB2cGMsXG4gICAgICBwb3J0OiAzMDAxLFxuICAgICAgcHJvdG9jb2w6IGVsYnYyLkFwcGxpY2F0aW9uUHJvdG9jb2wuSFRUUCxcbiAgICAgIHRhcmdldFR5cGU6IGVsYnYyLlRhcmdldFR5cGUuSVAsXG4gICAgICBoZWFsdGhDaGVjazoge1xuICAgICAgICBlbmFibGVkOiB0cnVlLFxuICAgICAgICBwYXRoOiAnL2hlYWx0aCcsXG4gICAgICAgIHByb3RvY29sOiBlbGJ2Mi5Qcm90b2NvbC5IVFRQLFxuICAgICAgICBwb3J0OiAnMzAwMCcsIC8vIEhlYWx0aCBlbmRwb2ludCBpcyBvbiBwb3J0IDMwMDBcbiAgICAgICAgaGVhbHRoeUh0dHBDb2RlczogJzIwMCcsXG4gICAgICAgIGludGVydmFsOiBjZGsuRHVyYXRpb24uc2Vjb25kcygzMCksXG4gICAgICAgIHRpbWVvdXQ6IGNkay5EdXJhdGlvbi5zZWNvbmRzKDUpLFxuICAgICAgICBoZWFsdGh5VGhyZXNob2xkQ291bnQ6IDIsXG4gICAgICAgIHVuaGVhbHRoeVRocmVzaG9sZENvdW50OiAzLFxuICAgICAgfSxcbiAgICB9KTtcblxuICAgIC8vIEFkZCBFQ1Mgc2VydmljZSB0byB0YXJnZXQgZ3JvdXBcbiAgICBzZXJ2aWNlLmF0dGFjaFRvQXBwbGljYXRpb25UYXJnZXRHcm91cCh0YXJnZXRHcm91cCk7XG5cbiAgICAvLyBNQ1AgU2VydmVyIGhhbmRsZXMgaXRzIG93biBhdXRoZW50aWNhdGlvbiAtIG5vIENvZ25pdG8gbmVlZGVkXG5cbiAgICAvLyBTaW1wbGUgSFRUUC9IVFRQUyBzZXR1cCB3aXRob3V0IENvZ25pdG8gYXV0aGVudGljYXRpb25cbiAgICAvLyBNQ1Agc2VydmVyIGhhbmRsZXMgaXRzIG93biBhdXRoZW50aWNhdGlvblxuICAgIGlmIChwcm9wcz8uY2VydGlmaWNhdGVBcm4gfHwgcHJvcHM/LmRvbWFpbk5hbWUpIHtcbiAgICAgIGxldCBjZXJ0aWZpY2F0ZTtcbiAgICAgIGlmIChwcm9wcz8uY2VydGlmaWNhdGVBcm4pIHtcbiAgICAgICAgY2VydGlmaWNhdGUgPSBjZXJ0aWZpY2F0ZW1hbmFnZXIuQ2VydGlmaWNhdGUuZnJvbUNlcnRpZmljYXRlQXJuKFxuICAgICAgICAgIHRoaXMsXG4gICAgICAgICAgJ01jcFNlcnZlckNlcnRpZmljYXRlJyxcbiAgICAgICAgICBwcm9wcy5jZXJ0aWZpY2F0ZUFyblxuICAgICAgICApO1xuICAgICAgfSBlbHNlIGlmIChwcm9wcz8uZG9tYWluTmFtZSkge1xuICAgICAgICBjZXJ0aWZpY2F0ZSA9IG5ldyBjZXJ0aWZpY2F0ZW1hbmFnZXIuQ2VydGlmaWNhdGUodGhpcywgJ01jcFNlcnZlckNlcnRpZmljYXRlJywge1xuICAgICAgICAgIGRvbWFpbk5hbWU6IHByb3BzLmRvbWFpbk5hbWUsXG4gICAgICAgICAgdmFsaWRhdGlvbjogY2VydGlmaWNhdGVtYW5hZ2VyLkNlcnRpZmljYXRlVmFsaWRhdGlvbi5mcm9tRG5zKCksXG4gICAgICAgIH0pO1xuICAgICAgfVxuXG4gICAgICAvLyBDcmVhdGUgSFRUUCBsaXN0ZW5lciB0aGF0IHJlZGlyZWN0cyBhbGwgdHJhZmZpYyB0byBIVFRQU1xuICAgICAgdGhpcy5sb2FkQmFsYW5jZXIuYWRkTGlzdGVuZXIoJ01jcFNlcnZlckh0dHBMaXN0ZW5lcicsIHtcbiAgICAgICAgcG9ydDogODAsXG4gICAgICAgIHByb3RvY29sOiBlbGJ2Mi5BcHBsaWNhdGlvblByb3RvY29sLkhUVFAsXG4gICAgICAgIGRlZmF1bHRBY3Rpb246IGVsYnYyLkxpc3RlbmVyQWN0aW9uLnJlZGlyZWN0KHtcbiAgICAgICAgICBwcm90b2NvbDogJ0hUVFBTJyxcbiAgICAgICAgICBwb3J0OiAnNDQzJyxcbiAgICAgICAgICBwZXJtYW5lbnQ6IHRydWUsXG4gICAgICAgIH0pLFxuICAgICAgfSk7XG5cbiAgICAgIC8vIENyZWF0ZSBIVFRQUyBsaXN0ZW5lclxuICAgICAgdGhpcy5sb2FkQmFsYW5jZXIuYWRkTGlzdGVuZXIoJ01jcFNlcnZlckh0dHBzTGlzdGVuZXInLCB7XG4gICAgICAgIHBvcnQ6IDQ0MyxcbiAgICAgICAgcHJvdG9jb2w6IGVsYnYyLkFwcGxpY2F0aW9uUHJvdG9jb2wuSFRUUFMsXG4gICAgICAgIGNlcnRpZmljYXRlczogW2NlcnRpZmljYXRlIV0sXG4gICAgICAgIGRlZmF1bHRBY3Rpb246IGVsYnYyLkxpc3RlbmVyQWN0aW9uLmZvcndhcmQoW3RhcmdldEdyb3VwXSksXG4gICAgICB9KTtcblxuICAgICAgLy8gU2V0IHNlcnZpY2UgVVJMIHRvIHVzZSBIVFRQU1xuICAgICAgdGhpcy5zZXJ2aWNlVXJsID0gYGh0dHBzOi8vJHt0aGlzLmxvYWRCYWxhbmNlci5sb2FkQmFsYW5jZXJEbnNOYW1lfWA7XG4gICAgfSBlbHNlIHtcbiAgICAgIC8vIFVzZSBIVFRQIG9ubHlcbiAgICAgIHRoaXMubG9hZEJhbGFuY2VyLmFkZExpc3RlbmVyKCdNY3BTZXJ2ZXJIdHRwT25seUxpc3RlbmVyJywge1xuICAgICAgICBwb3J0OiA4MCxcbiAgICAgICAgcHJvdG9jb2w6IGVsYnYyLkFwcGxpY2F0aW9uUHJvdG9jb2wuSFRUUCxcbiAgICAgICAgZGVmYXVsdEFjdGlvbjogZWxidjIuTGlzdGVuZXJBY3Rpb24uZm9yd2FyZChbdGFyZ2V0R3JvdXBdKSxcbiAgICAgIH0pO1xuXG4gICAgICAvLyBTZXQgc2VydmljZSBVUkwgdG8gdXNlIEhUVFBcbiAgICAgIHRoaXMuc2VydmljZVVybCA9IGBodHRwOi8vJHt0aGlzLmxvYWRCYWxhbmNlci5sb2FkQmFsYW5jZXJEbnNOYW1lfWA7XG4gICAgfVxuXG4gICAgLy8gT3V0cHV0c1xuICAgIG5ldyBjZGsuQ2ZuT3V0cHV0KHRoaXMsICdNY3BTZXJ2ZXJVcmwnLCB7XG4gICAgICB2YWx1ZTogdGhpcy5zZXJ2aWNlVXJsLFxuICAgICAgZGVzY3JpcHRpb246ICdNQ1AgU2VydmVyIFVSTCcsXG4gICAgfSk7XG5cbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCAnRWNyUmVwb3NpdG9yeVVyaScsIHtcbiAgICAgIHZhbHVlOiBlY3JSZXBvc2l0b3J5LnJlcG9zaXRvcnlVcmksXG4gICAgICBkZXNjcmlwdGlvbjogJ0VDUiBSZXBvc2l0b3J5IFVSSSBmb3IgTUNQIFNlcnZlcicsXG4gICAgfSk7XG5cbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCAnQ2x1c3Rlck5hbWUnLCB7XG4gICAgICB2YWx1ZTogY2x1c3Rlci5jbHVzdGVyTmFtZSxcbiAgICAgIGRlc2NyaXB0aW9uOiAnRUNTIENsdXN0ZXIgTmFtZScsXG4gICAgfSk7XG5cbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCAnU2VydmljZU5hbWUnLCB7XG4gICAgICB2YWx1ZTogc2VydmljZS5zZXJ2aWNlTmFtZSxcbiAgICAgIGRlc2NyaXB0aW9uOiAnRUNTIFNlcnZpY2UgTmFtZScsXG4gICAgfSk7XG5cbiAgICAvLyBBZGQgQ0RLLW5hZyBzdXBwcmVzc2lvbnMgZm9yIGFjY2VwdGFibGUgc2VjdXJpdHkgdHJhZGUtb2Zmc1xuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgIGFsYkxvZ3NCdWNrZXQsXG4gICAgICBbXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogJ0F3c1NvbHV0aW9ucy1TMScsXG4gICAgICAgICAgcmVhc29uOiAnQUxCIGFjY2VzcyBsb2dzIGJ1Y2tldCBkb2VzIG5vdCBuZWVkIHNlcnZlciBhY2Nlc3MgbG9nZ2luZyBmb3IgdGhpcyB1c2UgY2FzZScsXG4gICAgICAgIH0sXG4gICAgICBdXG4gICAgKTtcblxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgIHRhc2tFeGVjdXRpb25Sb2xlLFxuICAgICAgW1xuICAgICAgICB7XG4gICAgICAgICAgaWQ6ICdBd3NTb2x1dGlvbnMtSUFNNCcsXG4gICAgICAgICAgcmVhc29uOiAnVGFzayBleGVjdXRpb24gcm9sZSB1c2VzIGN1c3RvbSBtYW5hZ2VkIHBvbGljeSBpbnN0ZWFkIG9mIEFXUyBtYW5hZ2VkIHBvbGljeScsXG4gICAgICAgIH0sXG4gICAgICBdXG4gICAgKTtcblxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgIHRhc2tFeGVjdXRpb25Qb2xpY3ksXG4gICAgICBbXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogJ0F3c1NvbHV0aW9ucy1JQU01JyxcbiAgICAgICAgICByZWFzb246ICdFQ1IgR2V0QXV0aG9yaXphdGlvblRva2VuIHJlcXVpcmVzIHdpbGRjYXJkIHBlcm1pc3Npb24gYXMgaXQgZG9lcyBub3Qgc3VwcG9ydCByZXNvdXJjZS1sZXZlbCBwZXJtaXNzaW9ucycsXG4gICAgICAgICAgYXBwbGllc1RvOiBbJ1Jlc291cmNlOjoqJ10sXG4gICAgICAgIH0sXG4gICAgICBdXG4gICAgKTtcblxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgIHRhc2tFeGVjdXRpb25Sb2xlLm5vZGUuZmluZENoaWxkKCdEZWZhdWx0UG9saWN5JyksXG4gICAgICBbXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogJ0F3c1NvbHV0aW9ucy1JQU01JyxcbiAgICAgICAgICByZWFzb246ICdUYXNrIGV4ZWN1dGlvbiByb2xlIGRlZmF1bHQgcG9saWN5IHJlcXVpcmVzIHdpbGRjYXJkIHBlcm1pc3Npb25zIGZvciBFQ1IgYW5kIENsb3VkV2F0Y2ggb3BlcmF0aW9ucycsXG4gICAgICAgICAgYXBwbGllc1RvOiBbJ1Jlc291cmNlOjoqJ10sXG4gICAgICAgIH0sXG4gICAgICBdXG4gICAgKTtcblxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgIHRhc2tSb2xlLFxuICAgICAgW1xuICAgICAgICB7XG4gICAgICAgICAgaWQ6ICdBd3NTb2x1dGlvbnMtSUFNNScsXG4gICAgICAgICAgcmVhc29uOiAnQmVkcm9jayBmb3VuZGF0aW9uIG1vZGVscyByZXF1aXJlIHdpbGRjYXJkIHBlcm1pc3Npb25zIGFzIG1vZGVsIEFSTnMgYXJlIG5vdCBwcmVkaWN0YWJsZScsXG4gICAgICAgICAgYXBwbGllc1RvOiBbXG4gICAgICAgICAgICAnUmVzb3VyY2U6OmFybjphd3M6YmVkcm9jazo8QVdTOjpSZWdpb24+Ojpmb3VuZGF0aW9uLW1vZGVsLyonLFxuICAgICAgICAgICAgJ1Jlc291cmNlOjphcm46YXdzOmJlZHJvY2stYWdlbnQ6PEFXUzo6UmVnaW9uPjo8QVdTOjpBY2NvdW50SWQ+OmFnZW50LyonLFxuICAgICAgICAgIF0sXG4gICAgICAgIH0sXG4gICAgICBdXG4gICAgKTtcblxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgIHRhc2tSb2xlLm5vZGUuZmluZENoaWxkKCdEZWZhdWx0UG9saWN5JyksXG4gICAgICBbXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogJ0F3c1NvbHV0aW9ucy1JQU01JyxcbiAgICAgICAgICByZWFzb246ICdDbG91ZFdhdGNoIExvZ3MgcGVybWlzc2lvbnMgYXJlIHNjb3BlZCB0byBzcGVjaWZpYyBsb2cgZ3JvdXAnLFxuICAgICAgICAgIGFwcGxpZXNUbzogWydSZXNvdXJjZTo6KiddLFxuICAgICAgICB9LFxuICAgICAgXVxuICAgICk7XG5cbiAgICBOYWdTdXBwcmVzc2lvbnMuYWRkUmVzb3VyY2VTdXBwcmVzc2lvbnMoXG4gICAgICBhbGJTZWN1cml0eUdyb3VwLFxuICAgICAgW1xuICAgICAgICB7XG4gICAgICAgICAgaWQ6ICdDZGtOYWdWYWxpZGF0aW9uRmFpbHVyZScsXG4gICAgICAgICAgcmVhc29uOiAnVlBDIENJRFIgYmxvY2sgcmVmZXJlbmNlIGlzIGFjY2VwdGFibGUgZm9yIHByaXZhdGUgQUxCIHNlY3VyaXR5IGdyb3VwJyxcbiAgICAgICAgfSxcbiAgICAgICAge1xuICAgICAgICAgIGlkOiAnQXdzU29sdXRpb25zLUVDMjMnLFxuICAgICAgICAgIHJlYXNvbjogJ0FMQiBzZWN1cml0eSBncm91cCBhbGxvd3MgaW50ZXJuZXQgYWNjZXNzIHdoaWNoIGlzIHJlcXVpcmVkIGZvciBwdWJsaWMtZmFjaW5nIGxvYWQgYmFsYW5jZXInLFxuICAgICAgICB9LFxuICAgICAgXVxuICAgICk7XG5cbiAgICAvLyBTdXBwcmVzcyBWUEMgRW5kcG9pbnQgc2VjdXJpdHkgZ3JvdXAgd2FybmluZ3NcbiAgICBbZWNyQXBpRW5kcG9pbnQsIGVjckRrckVuZHBvaW50LCBsb2dzRW5kcG9pbnQsIGJlZHJvY2tFbmRwb2ludCwgc3NtRW5kcG9pbnQsIGxhbWJkYUVuZHBvaW50XS5mb3JFYWNoKChlbmRwb2ludCkgPT4ge1xuICAgICAgTmFnU3VwcHJlc3Npb25zLmFkZFJlc291cmNlU3VwcHJlc3Npb25zKFxuICAgICAgICBlbmRwb2ludCxcbiAgICAgICAgW1xuICAgICAgICAgIHtcbiAgICAgICAgICAgIGlkOiAnQ2RrTmFnVmFsaWRhdGlvbkZhaWx1cmUnLFxuICAgICAgICAgICAgcmVhc29uOiAnVlBDIGVuZHBvaW50IHNlY3VyaXR5IGdyb3VwcyB3aXRoIFZQQyBDSURSIHJlZmVyZW5jZXMgYXJlIGFjY2VwdGFibGUgZm9yIHByaXZhdGUgY29ubmVjdGl2aXR5JyxcbiAgICAgICAgICB9LFxuICAgICAgICBdXG4gICAgICApO1xuXG4gICAgICAvLyBBZGQgc3VwcHJlc3Npb25zIGZvciB0aGUgc2VjdXJpdHkgZ3JvdXBzXG4gICAgICBjb25zdCBzZWN1cml0eUdyb3VwID0gZW5kcG9pbnQubm9kZS5maW5kQ2hpbGQoJ1NlY3VyaXR5R3JvdXAnKTtcbiAgICAgIGlmIChzZWN1cml0eUdyb3VwKSB7XG4gICAgICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgICAgICBzZWN1cml0eUdyb3VwLFxuICAgICAgICAgIFtcbiAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgaWQ6ICdBd3NTb2x1dGlvbnMtRUMyMycsXG4gICAgICAgICAgICAgIHJlYXNvbjogJ1ZQQyBlbmRwb2ludCBzZWN1cml0eSBncm91cHMgdXNlIFZQQyBDSURSIHJlZmVyZW5jZXMgd2hpY2ggaXMgYWNjZXB0YWJsZSBmb3IgcHJpdmF0ZSBjb25uZWN0aXZpdHknLFxuICAgICAgICAgICAgfSxcbiAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgaWQ6ICdDZGtOYWdWYWxpZGF0aW9uRmFpbHVyZScsXG4gICAgICAgICAgICAgIHJlYXNvbjogJ1ZQQyBlbmRwb2ludCBzZWN1cml0eSBncm91cHMgd2l0aCBWUEMgQ0lEUiByZWZlcmVuY2VzIGFyZSBhY2NlcHRhYmxlIGZvciBwcml2YXRlIGNvbm5lY3Rpdml0eScsXG4gICAgICAgICAgICB9LFxuICAgICAgICAgIF1cbiAgICAgICAgKTtcbiAgICAgIH1cbiAgICB9KTtcblxuICAgIC8vIENESyBOYWcgc3VwcHJlc3Npb25zIHJlbW92ZWQgLSBubyBTMyBwZXJtaXNzaW9ucyBuZWVkZWRcblxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyh0YXNrRGVmaW5pdGlvbiwgW1xuICAgICAge1xuICAgICAgICBpZDogJ0F3c1NvbHV0aW9ucy1FQ1MyJyxcbiAgICAgICAgcmVhc29uOiAnRW52aXJvbm1lbnQgdmFyaWFibGVzIGFyZSBhY2NlcHRhYmxlIGZvciB0aGlzIHVzZSBjYXNlIGFzIHRoZXkgY29udGFpbiBub24tc2Vuc2l0aXZlIGNvbmZpZ3VyYXRpb24nLFxuICAgICAgfSxcbiAgICBdKTtcblxuICAgIC8vIENvZ25pdG8gcmVtb3ZlZCAtIE1DUCBzZXJ2ZXIgaGFuZGxlcyBpdHMgb3duIGF1dGhlbnRpY2F0aW9uXG5cbiAgICAvLyBTdXBwcmVzcyBMYW1iZGEgSUFNIHJvbGUgd2FybmluZ3MgaWYgdGhleSBleGlzdFxuICAgIHRyeSB7XG4gICAgICBjb25zdCBjdXN0b21SZXNvdXJjZVByb3ZpZGVyID0gdGhpcy5ub2RlLmZpbmRDaGlsZCgnQVdTNjc5ZjUzZmFjMDAyNDMwY2IwZGE1Yjc5ODJiZDIyODcnKTtcbiAgICAgIGlmIChjdXN0b21SZXNvdXJjZVByb3ZpZGVyKSB7XG4gICAgICAgIGNvbnN0IHNlcnZpY2VSb2xlID0gY3VzdG9tUmVzb3VyY2VQcm92aWRlci5ub2RlLmZpbmRDaGlsZCgnU2VydmljZVJvbGUnKTtcbiAgICAgICAgaWYgKHNlcnZpY2VSb2xlKSB7XG4gICAgICAgICAgTmFnU3VwcHJlc3Npb25zLmFkZFJlc291cmNlU3VwcHJlc3Npb25zKHNlcnZpY2VSb2xlLCBbXG4gICAgICAgICAgICB7XG4gICAgICAgICAgICAgIGlkOiAnQXdzU29sdXRpb25zLUlBTTQnLFxuICAgICAgICAgICAgICByZWFzb246ICdBV1MgTGFtYmRhIGN1c3RvbSByZXNvdXJjZSBwcm92aWRlciB1c2VzIEFXUyBtYW5hZ2VkIHBvbGljeSBieSBkZXNpZ24nLFxuICAgICAgICAgICAgICBhcHBsaWVzVG86IFsnUG9saWN5Ojphcm46PEFXUzo6UGFydGl0aW9uPjppYW06OmF3czpwb2xpY3kvc2VydmljZS1yb2xlL0FXU0xhbWJkYUJhc2ljRXhlY3V0aW9uUm9sZSddLFxuICAgICAgICAgICAgfSxcbiAgICAgICAgICBdKTtcbiAgICAgICAgfVxuICAgICAgfVxuICAgIH0gY2F0Y2ggKGVycm9yKSB7XG4gICAgICAvLyBJZ25vcmUgaWYgdGhlIHJlc291cmNlIGRvZXNuJ3QgZXhpc3RcbiAgICAgIGNvbnNvbGUubG9nKCdDdXN0b20gcmVzb3VyY2UgcHJvdmlkZXIgbm90IGZvdW5kLCBza2lwcGluZyBzdXBwcmVzc2lvbnMnKTtcbiAgICB9XG4gIH1cbn0iXX0=