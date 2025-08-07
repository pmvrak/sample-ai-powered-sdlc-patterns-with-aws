"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.LambdaStack = void 0;
const cdk = require("aws-cdk-lib");
const lambda = require("aws-cdk-lib/aws-lambda");
const iam = require("aws-cdk-lib/aws-iam");
const cdk_nag_1 = require("cdk-nag");
class LambdaStack extends cdk.Stack {
    constructor(scope, id, props) {
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
        cdk_nag_1.NagSuppressions.addResourceSuppressions(domainAnalyzerRole, [
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
        cdk_nag_1.NagSuppressions.addResourceSuppressions(docGeneratorRole, [
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
exports.LambdaStack = LambdaStack;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoibGFtYmRhLXN0YWNrLmpzIiwic291cmNlUm9vdCI6IiIsInNvdXJjZXMiOlsibGFtYmRhLXN0YWNrLnRzIl0sIm5hbWVzIjpbXSwibWFwcGluZ3MiOiI7OztBQUFBLG1DQUFtQztBQUNuQyxpREFBaUQ7QUFDakQsMkNBQTJDO0FBRTNDLHFDQUEwQztBQVExQyxNQUFhLFdBQVksU0FBUSxHQUFHLENBQUMsS0FBSztJQUl4QyxZQUFZLEtBQWdCLEVBQUUsRUFBVSxFQUFFLEtBQXVCO1FBQy9ELEtBQUssQ0FBQyxLQUFLLEVBQUUsRUFBRSxFQUFFLEtBQUssQ0FBQyxDQUFDO1FBRXhCLHVGQUF1RjtRQUN2RixNQUFNLGtCQUFrQixHQUFHLElBQUksR0FBRyxDQUFDLElBQUksQ0FBQyxJQUFJLEVBQUUsMEJBQTBCLEVBQUU7WUFDeEUsU0FBUyxFQUFFLElBQUksR0FBRyxDQUFDLGdCQUFnQixDQUFDLHNCQUFzQixDQUFDO1lBQzNELFdBQVcsRUFBRSx5RkFBeUY7U0FDdkcsQ0FBQyxDQUFDO1FBRUgsMEVBQTBFO1FBQzFFLGtCQUFrQixDQUFDLFdBQVcsQ0FBQyxJQUFJLEdBQUcsQ0FBQyxlQUFlLENBQUM7WUFDckQsTUFBTSxFQUFFLEdBQUcsQ0FBQyxNQUFNLENBQUMsS0FBSztZQUN4QixPQUFPLEVBQUU7Z0JBQ1AscUJBQXFCO2dCQUNyQixzQkFBc0I7Z0JBQ3RCLG1CQUFtQjthQUNwQjtZQUNELFNBQVMsRUFBRTtnQkFDVCxnQkFBZ0IsSUFBSSxDQUFDLE1BQU0sSUFBSSxJQUFJLENBQUMsT0FBTywwQkFBMEI7YUFDdEU7U0FDRixDQUFDLENBQUMsQ0FBQztRQUVKLHVEQUF1RDtRQUN2RCxJQUFJLEtBQUssQ0FBQyxjQUFjLElBQUksS0FBSyxDQUFDLG1CQUFtQixFQUFFLENBQUM7WUFDdEQsa0JBQWtCLENBQUMsV0FBVyxDQUFDLElBQUksR0FBRyxDQUFDLGVBQWUsQ0FBQztnQkFDckQsTUFBTSxFQUFFLEdBQUcsQ0FBQyxNQUFNLENBQUMsS0FBSztnQkFDeEIs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QUFTLDJCQUEyQjtTQUN6RCxDQUFDLENBQUM7UUFFSCxxRUFBcUU7SUFDdkUsQ0FBQztDQUNGO0FBakxELGtDQWlMQyIsInNvdXJjZXNDb250ZW50IjpbImltcG9ydCAqIGFzIGNkayBmcm9tICdhd3MtY2RrLWxpYic7XG5pbXBvcnQgKiBhcyBsYW1iZGEgZnJvbSAnYXdzLWNkay1saWIvYXdzLWxhbWJkYSc7XG5pbXBvcnQgKiBhcyBpYW0gZnJvbSAnYXdzLWNkay1saWIvYXdzLWlhbSc7XG5pbXBvcnQgeyBDb25zdHJ1Y3QgfSBmcm9tICdjb25zdHJ1Y3RzJztcbmltcG9ydCB7IE5hZ1N1cHByZXNzaW9ucyB9IGZyb20gJ2Nkay1uYWcnO1xuXG5leHBvcnQgaW50ZXJmYWNlIExhbWJkYVN0YWNrUHJvcHMgZXh0ZW5kcyBjZGsuU3RhY2tQcm9wcyB7XG4gIGJlZHJvY2tBZ2VudElkPzogc3RyaW5nO1xuICBiZWRyb2NrQWdlbnRBbGlhc0lkPzogc3RyaW5nO1xuICBrbm93bGVkZ2VCYXNlSWQ/OiBzdHJpbmc7XG59XG5cbmV4cG9ydCBjbGFzcyBMYW1iZGFTdGFjayBleHRlbmRzIGNkay5TdGFjayB7XG4gIHB1YmxpYyByZWFkb25seSBkb21haW5BbmFseXplckZ1bmN0aW9uOiBsYW1iZGEuRnVuY3Rpb247XG4gIHB1YmxpYyByZWFkb25seSBkb2NHZW5lcmF0b3JGdW5jdGlvbjogbGFtYmRhLkZ1bmN0aW9uO1xuXG4gIGNvbnN0cnVjdG9yKHNjb3BlOiBDb25zdHJ1Y3QsIGlkOiBzdHJpbmcsIHByb3BzOiBMYW1iZGFTdGFja1Byb3BzKSB7XG4gICAgc3VwZXIoc2NvcGUsIGlkLCBwcm9wcyk7XG5cbiAgICAvLyBDcmVhdGUgSUFNIHJvbGUgZm9yIGRvbWFpbiBhbmFseXplciBMYW1iZGEgZnVuY3Rpb24gd2l0aCBsZWFzdC1wcml2aWxlZ2UgcGVybWlzc2lvbnNcbiAgICBjb25zdCBkb21haW5BbmFseXplclJvbGUgPSBuZXcgaWFtLlJvbGUodGhpcywgJ0RvbWFpbkFuYWx5emVyTGFtYmRhUm9sZScsIHtcbiAgICAgIGFzc3VtZWRCeTogbmV3IGlhbS5TZXJ2aWNlUHJpbmNpcGFsKCdsYW1iZGEuYW1hem9uYXdzLmNvbScpLFxuICAgICAgZGVzY3JpcHRpb246ICdJQU0gcm9sZSBmb3IgZG9tYWluIGFuYWx5emVyIExhbWJkYSBmdW5jdGlvbiB3aXRoIGxlYXN0LXByaXZpbGVnZSBCZWRyb2NrIGFuZCBTMyBhY2Nlc3MnXG4gICAgfSk7XG5cbiAgICAvLyBBZGQgQ2xvdWRXYXRjaCBMb2dzIHBlcm1pc3Npb25zIChtaW5pbXVtIHJlcXVpcmVkIGZvciBMYW1iZGEgZXhlY3V0aW9uKVxuICAgIGRvbWFpbkFuYWx5emVyUm9sZS5hZGRUb1BvbGljeShuZXcgaWFtLlBvbGljeVN0YXRlbWVudCh7XG4gICAgICBlZmZlY3Q6IGlhbS5FZmZlY3QuQUxMT1csXG4gICAgICBhY3Rpb25zOiBbXG4gICAgICAgICdsb2dzOkNyZWF0ZUxvZ0dyb3VwJyxcbiAgICAgICAgJ2xvZ3M6Q3JlYXRlTG9nU3RyZWFtJyxcbiAgICAgICAgJ2xvZ3M6UHV0TG9nRXZlbnRzJ1xuICAgICAgXSxcbiAgICAgIHJlc291cmNlczogW1xuICAgICAgICBgYXJuOmF3czpsb2dzOiR7dGhpcy5yZWdpb259OiR7dGhpcy5hY2NvdW50fTpsb2ctZ3JvdXA6L2F3cy9sYW1iZGEvKmBcbiAgICAgIF1cbiAgICB9KSk7XG5cbiAgICAvLyBBZGQgQmVkcm9jayBhZ2VudCBwZXJtaXNzaW9ucyBpZiBhZ2VudCBpcyBjb25maWd1cmVkXG4gICAgaWYgKHByb3BzLmJlZHJvY2tBZ2VudElkICYmIHByb3BzLmJlZHJvY2tBZ2VudEFsaWFzSWQpIHtcbiAgICAgIGRvbWFpbkFuYWx5emVyUm9sZS5hZGRUb1BvbGljeShuZXcgaWFtLlBvbGljeVN0YXRlbWVudCh7XG4gICAgICAgIGVmZmVjdDogaWFtLkVmZmVjdC5BTExPVyxcbiAgICAgICAgYWN0aW9uczogW1xuICAgICAgICAgICdiZWRyb2NrOkludm9rZUFnZW50JyxcbiAgICAgICAgICAnYmVkcm9jazpHZXRBZ2VudCcsXG4gICAgICAgICAgJ2JlZHJvY2s6R2V0QWdlbnRBbGlhcydcbiAgICAgICAgXSxcbiAgICAgICAgcmVzb3VyY2VzOiBbXG4gICAgICAgICAgYGFybjphd3M6YmVkcm9jazoke3RoaXMucmVnaW9ufToke3RoaXMuYWNjb3VudH06YWdlbnQvJHtwcm9wcy5iZWRyb2NrQWdlbnRJZH1gLFxuICAgICAgICAgIGBhcm46YXdzOmJlZHJvY2s6JHt0aGlzLnJlZ2lvbn06JHt0aGlzLmFjY291bnR9OmFnZW50LWFsaWFzLyR7cHJvcHMuYmVkcm9ja0FnZW50SWR9LyR7cHJvcHMuYmVkcm9ja0FnZW50QWxpYXNJZH1gXG4gICAgICAgIF1cbiAgICAgIH0pKTtcbiAgICB9XG5cbiAgICAvLyBBZGQgc2VwYXJhdGUgcG9saWN5IGZvciBtb2RlbCBpbnZvY2F0aW9uIHdpdGggc3BlY2lmaWMgbW9kZWxcbiAgICBkb21haW5BbmFseXplclJvbGUuYWRkVG9Qb2xpY3kobmV3IGlhbS5Qb2xpY3lTdGF0ZW1lbnQoe1xuICAgICAgZWZmZWN0OiBpYW0uRWZmZWN0LkFMTE9XLFxuICAgICAgYWN0aW9uczogW1xuICAgICAgICAnYmVkcm9jazpJbnZva2VNb2RlbCdcbiAgICAgIF0sXG4gICAgICByZXNvdXJjZXM6IFtcbiAgICAgICAgYCpgXG4gICAgICBdXG4gICAgfSkpO1xuXG4gICAgLy8gUzMgcGVybWlzc2lvbnMgcmVtb3ZlZCAtIExhbWJkYSBmdW5jdGlvbnMgbm93IHJldHVybiByZXNwb25zZXMgZGlyZWN0bHlcblxuICAgIC8vIFN1cHByZXNzIGNkay1uYWcgd2FybmluZ3MgZm9yIElBTSByb2xlIHBvbGljaWVzXG4gICAgTmFnU3VwcHJlc3Npb25zLmFkZFJlc291cmNlU3VwcHJlc3Npb25zKGRvbWFpbkFuYWx5emVyUm9sZSwgW1xuICAgICAge1xuICAgICAgICBpZDogJ0F3c1NvbHV0aW9ucy1JQU01JyxcbiAgICAgICAgcmVhc29uOiAnV2lsZGNhcmQgcGVybWlzc2lvbnMgYXJlIG5lY2Vzc2FyeSBmb3IgQ2xvdWRXYXRjaCBMb2dzIChMYW1iZGEgcnVudGltZSByZXF1aXJlbWVudCkgYW5kIEJlZHJvY2sgbW9kZWwgYWNjZXNzIChjcm9zcy1yZWdpb24gaW5mZXJlbmNlIHByb2ZpbGVzKScsXG4gICAgICAgIGFwcGxpZXNUbzogW1xuICAgICAgICAgIGBSZXNvdXJjZTo6YXJuOmF3czpsb2dzOiR7Y2RrLkF3cy5SRUdJT059OiR7Y2RrLkF3cy5BQ0NPVU5UX0lEfTpsb2ctZ3JvdXA6L2F3cy9sYW1iZGEvKmAsXG4gICAgICAgICAgYFJlc291cmNlOjphcm46YXdzOmJlZHJvY2s6Kjoke2Nkay5Bd3MuQUNDT1VOVF9JRH06aW5mZXJlbmNlLXByb2ZpbGUvZXUuYW50aHJvcGljLmNsYXVkZS0zLTctc29ubmV0LTIwMjUwMjE5LXYxOjBgXG4gICAgICAgIF1cbiAgICAgIH1cbiAgICBdLCB0cnVlKTtcblxuICAgIC8vIENyZWF0ZSBkb21haW4gYW5hbHl6ZXIgTGFtYmRhIGZ1bmN0aW9uXG4gICAgdGhpcy5kb21haW5BbmFseXplckZ1bmN0aW9uID0gbmV3IGxhbWJkYS5GdW5jdGlvbih0aGlzLCAnRG9tYWluQW5hbHl6ZXJGdW5jdGlvbicsIHtcbiAgICAgIHJ1bnRpbWU6IGxhbWJkYS5SdW50aW1lLk5PREVKU18yMl9YLFxuICAgICAgaGFuZGxlcjogJ2RvbWFpbi1hbmFseXplci5oYW5kbGVyJyxcbiAgICAgIGNvZGU6IGxhbWJkYS5Db2RlLmZyb21Bc3NldCgnLi4vZG9tYWluLWFuYWx5emVyLWxhbWJkYScpLFxuICAgICAgcm9sZTogZG9tYWluQW5hbHl6ZXJSb2xlLFxuICAgICAgdGltZW91dDogY2RrLkR1cmF0aW9uLm1pbnV0ZXMoNSksXG4gICAgICBtZW1vcnlTaXplOiAxMDI0LFxuICAgICAgZW52aXJvbm1lbnQ6IHtcbiAgICAgICAgQkVEUk9DS19SRUdJT046IHByb2Nlc3MuZW52LkJFRFJPQ0tfUkVHSU9OIHx8IHRoaXMucmVnaW9uLFxuICAgICAgICBNT0RFTF9JRDogcHJvY2Vzcy5lbnYuTU9ERUxfSUQgfHwgJ2FudGhyb3BpYy5jbGF1ZGUtMy03LXNvbm5ldC0yMDI1MDIxOS12MTowJyxcbiAgICAgICAgLi4uKHByb3BzLmJlZHJvY2tBZ2VudElkICYmIHsgQkVEUk9DS19BR0VOVF9JRDogcHJvcHMuYmVkcm9ja0FnZW50SWQgfSksXG4gICAgICAgIC4uLihwcm9wcy5iZWRyb2NrQWdlbnRBbGlhc0lkICYmIHsgQkVEUk9DS19BR0VOVF9BTElBU19JRDogcHJvcHMuYmVkcm9ja0FnZW50QWxpYXNJZCB9KSxcbiAgICAgICAgQVVUSF9SRVFVSVJFRDogJ2ZhbHNlJyAvLyBEaXNhYmxlIGF1dGhlbnRpY2F0aW9uIGZvciBpbnRlcm5hbCBjYWxsc1xuICAgICAgfSxcbiAgICAgIGRlc2NyaXB0aW9uOiAnTGFtYmRhIGZ1bmN0aW9uIGZvciBkb21haW4gbW9kZWwgYW5hbHlzaXMgdXNpbmcgQmVkcm9jayBDbGF1ZGUgMy43IFNvbm5ldCdcbiAgICB9KTtcblxuXG5cbiAgICAvLyBFeHBvcnQgTGFtYmRhIGZ1bmN0aW9uIEFSTiBmb3IgYXBwbGljYXRpb24gdXNlXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ0RvbWFpbkFuYWx5emVyRnVuY3Rpb25Bcm4nLCB7XG4gICAgICB2YWx1ZTogdGhpcy5kb21haW5BbmFseXplckZ1bmN0aW9uLmZ1bmN0aW9uQXJuLFxuICAgICAgZGVzY3JpcHRpb246ICdBUk4gb2YgdGhlIGRvbWFpbiBhbmFseXplciBMYW1iZGEgZnVuY3Rpb24nLFxuICAgICAgZXhwb3J0TmFtZTogYCR7dGhpcy5zdGFja05hbWV9LURvbWFpbkFuYWx5emVyRnVuY3Rpb25Bcm5gXG4gICAgfSk7XG5cbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCAnRG9tYWluQW5hbHl6ZXJGdW5jdGlvbk5hbWUnLCB7XG4gICAgICB2YWx1ZTogdGhpcy5kb21haW5BbmFseXplckZ1bmN0aW9uLmZ1bmN0aW9uTmFtZSxcbiAgICAgIGRlc2NyaXB0aW9uOiAnTmFtZSBvZiB0aGUgZG9tYWluIGFuYWx5emVyIExhbWJkYSBmdW5jdGlvbicsXG4gICAgICBleHBvcnROYW1lOiBgJHt0aGlzLnN0YWNrTmFtZX0tRG9tYWluQW5hbHl6ZXJGdW5jdGlvbk5hbWVgXG4gICAgfSk7XG5cbiAgICAvLyBDcmVhdGUgSUFNIHJvbGUgZm9yIGRvYyBnZW5lcmF0b3IgTGFtYmRhIGZ1bmN0aW9uIHdpdGggbGVhc3QtcHJpdmlsZWdlIHBlcm1pc3Npb25zXG4gICAgY29uc3QgZG9jR2VuZXJhdG9yUm9sZSA9IG5ldyBpYW0uUm9sZSh0aGlzLCAnRG9jR2VuZXJhdG9yTGFtYmRhUm9sZScsIHtcbiAgICAgIGFzc3VtZWRCeTogbmV3IGlhbS5TZXJ2aWNlUHJpbmNpcGFsKCdsYW1iZGEuYW1hem9uYXdzLmNvbScpLFxuICAgICAgZGVzY3JpcHRpb246ICdJQU0gcm9sZSBmb3IgZG9jIGdlbmVyYXRvciBMYW1iZGEgZnVuY3Rpb24gd2l0aCBtaW5pbWFsIEJlZHJvY2sgYWNjZXNzJ1xuICAgIH0pO1xuXG4gICAgLy8gQWRkIENsb3VkV2F0Y2ggTG9ncyBwZXJtaXNzaW9ucyAobWluaW11bSByZXF1aXJlZCBmb3IgTGFtYmRhIGV4ZWN1dGlvbilcbiAgICBkb2NHZW5lcmF0b3JSb2xlLmFkZFRvUG9saWN5KG5ldyBpYW0uUG9saWN5U3RhdGVtZW50KHtcbiAgICAgIGVmZmVjdDogaWFtLkVmZmVjdC5BTExPVyxcbiAgICAgIGFjdGlvbnM6IFtcbiAgICAgICAgJ2xvZ3M6Q3JlYXRlTG9nR3JvdXAnLFxuICAgICAgICAnbG9nczpDcmVhdGVMb2dTdHJlYW0nLFxuICAgICAgICAnbG9nczpQdXRMb2dFdmVudHMnXG4gICAgICBdLFxuICAgICAgcmVzb3VyY2VzOiBbXG4gICAgICAgIGBhcm46YXdzOmxvZ3M6JHt0aGlzLnJlZ2lvbn06JHt0aGlzLmFjY291bnR9OmxvZy1ncm91cDovYXdzL2xhbWJkYS8qYFxuICAgICAgXVxuICAgIH0pKTtcblxuICAgIC8vIEFkZCBtaW5pbWFsIEJlZHJvY2sgcGVybWlzc2lvbnMgZm9yIG1vZGVsIGludm9jYXRpb24gb25seVxuICAgIGRvY0dlbmVyYXRvclJvbGUuYWRkVG9Qb2xpY3kobmV3IGlhbS5Qb2xpY3lTdGF0ZW1lbnQoe1xuICAgICAgZWZmZWN0OiBpYW0uRWZmZWN0LkFMTE9XLFxuICAgICAgYWN0aW9uczogW1xuICAgICAgICAnYmVkcm9jazpJbnZva2VNb2RlbCdcbiAgICAgIF0sXG4gICAgICByZXNvdXJjZXM6IFtcbiAgICAgICAgYCpgXG4gICAgICBdXG4gICAgfSkpO1xuXG4gICAgLy8gUzMgcGVybWlzc2lvbnMgcmVtb3ZlZCAtIExhbWJkYSBmdW5jdGlvbnMgbm93IHJldHVybiByZXNwb25zZXMgZGlyZWN0bHlcblxuICAgIC8vIENyZWF0ZSBkb2MgZ2VuZXJhdG9yIExhbWJkYSBmdW5jdGlvblxuICAgIHRoaXMuZG9jR2VuZXJhdG9yRnVuY3Rpb24gPSBuZXcgbGFtYmRhLkZ1bmN0aW9uKHRoaXMsICdEb2NHZW5lcmF0b3JGdW5jdGlvbicsIHtcbiAgICAgIHJ1bnRpbWU6IGxhbWJkYS5SdW50aW1lLk5PREVKU18yMl9YLFxuICAgICAgaGFuZGxlcjogJ2RvYy1nZW4uaGFuZGxlcicsXG4gICAgICBjb2RlOiBsYW1iZGEuQ29kZS5mcm9tQXNzZXQoJy4uL2RvYy1nZW4tbGFtYmRhJyksXG4gICAgICByb2xlOiBkb2NHZW5lcmF0b3JSb2xlLFxuICAgICAgdGltZW91dDogY2RrLkR1cmF0aW9uLm1pbnV0ZXMoNSksXG4gICAgICBtZW1vcnlTaXplOiAxMDI0LFxuICAgICAgZW52aXJvbm1lbnQ6IHtcbiAgICAgICAgQkVEUk9DS19SRUdJT046IHByb2Nlc3MuZW52LkJFRFJPQ0tfUkVHSU9OIHx8IHRoaXMucmVnaW9uLFxuICAgICAgICBNT0RFTF9JRDogcHJvY2Vzcy5lbnYuTU9ERUxfSUQgfHwgJ2FudGhyb3BpYy5jbGF1ZGUtMy03LXNvbm5ldC0yMDI1MDIxOS12MTowJyxcbiAgICAgICAgQVVUSF9SRVFVSVJFRDogJ2ZhbHNlJyAvLyBEaXNhYmxlIGF1dGhlbnRpY2F0aW9uIGZvciBpbnRlcm5hbCBjYWxsc1xuICAgICAgfSxcbiAgICAgIGRlc2NyaXB0aW9uOiAnTGFtYmRhIGZ1bmN0aW9uIGZvciBBUEkgZG9jdW1lbnRhdGlvbiBnZW5lcmF0aW9uIHVzaW5nIEJlZHJvY2sgQ2xhdWRlIDMuNyBTb25uZXQnXG4gICAgfSk7XG5cblxuXG4gICAgLy8gU3VwcHJlc3MgY2RrLW5hZyB3YXJuaW5ncyBmb3IgZG9jIGdlbmVyYXRvciBJQU0gcm9sZSBwb2xpY2llc1xuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhkb2NHZW5lcmF0b3JSb2xlLCBbXG4gICAgICB7XG4gICAgICAgIGlkOiAnQXdzU29sdXRpb25zLUlBTTUnLFxuICAgICAgICByZWFzb246ICdXaWxkY2FyZCBwZXJtaXNzaW9ucyBhcmUgbmVjZXNzYXJ5IGZvciBDbG91ZFdhdGNoIExvZ3MgKExhbWJkYSBydW50aW1lIHJlcXVpcmVtZW50KSBhbmQgQmVkcm9jayBtb2RlbCBhY2Nlc3MgKGNyb3NzLXJlZ2lvbiBpbmZlcmVuY2UgcHJvZmlsZXMpJyxcbiAgICAgICAgYXBwbGllc1RvOiBbXG4gICAgICAgICAgYFJlc291cmNlOjphcm46YXdzOmxvZ3M6JHtjZGsuQXdzLlJFR0lPTn06JHtjZGsuQXdzLkFDQ09VTlRfSUR9OmxvZy1ncm91cDovYXdzL2xhbWJkYS8qYCxcbiAgICAgICAgICBgUmVzb3VyY2U6OmFybjphd3M6YmVkcm9jazoqOiR7Y2RrLkF3cy5BQ0NPVU5UX0lEfTppbmZlcmVuY2UtcHJvZmlsZS9ldS5hbnRocm9waWMuY2xhdWRlLTMtNy1zb25uZXQtMjAyNTAyMTktdjE6MGBcbiAgICAgICAgXVxuICAgICAgfVxuICAgIF0sIHRydWUpO1xuXG4gICAgLy8gRXhwb3J0IGRvYyBnZW5lcmF0b3IgTGFtYmRhIGZ1bmN0aW9uIEFSTiBmb3IgYXBwbGljYXRpb24gdXNlXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ0RvY0dlbmVyYXRvckZ1bmN0aW9uQXJuJywge1xuICAgICAgdmFsdWU6IHRoaXMuZG9jR2VuZXJhdG9yRnVuY3Rpb24uZnVuY3Rpb25Bcm4sXG4gICAgICBkZXNjcmlwdGlvbjogJ0FSTiBvZiB0aGUgZG9jIGdlbmVyYXRvciBMYW1iZGEgZnVuY3Rpb24nLFxuICAgICAgZXhwb3J0TmFtZTogYCR7dGhpcy5zdGFja05hbWV9LURvY0dlbmVyYXRvckZ1bmN0aW9uQXJuYFxuICAgIH0pO1xuXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ0RvY0dlbmVyYXRvckZ1bmN0aW9uTmFtZScsIHtcbiAgICAgIHZhbHVlOiB0aGlzLmRvY0dlbmVyYXRvckZ1bmN0aW9uLmZ1bmN0aW9uTmFtZSxcbiAgICAgIGRlc2NyaXB0aW9uOiAnTmFtZSBvZiB0aGUgZG9jIGdlbmVyYXRvciBMYW1iZGEgZnVuY3Rpb24nLFxuICAgICAgZXhwb3J0TmFtZTogYCR7dGhpcy5zdGFja05hbWV9LURvY0dlbmVyYXRvckZ1bmN0aW9uTmFtZWBcbiAgICB9KTtcblxuICAgIC8vIEJhY2tlbmQgZnVuY3Rpb25hbGl0eSBpcyBub3cgaGFuZGxlZCBieSB0aGUgTUNQIHNlcnZlciBFQ1Mgc2VydmljZVxuICB9XG59Il19