"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.BedrockStack = void 0;
const cdk = require("aws-cdk-lib");
const iam = require("aws-cdk-lib/aws-iam");
const bedrock = require("aws-cdk-lib/aws-bedrock");
const config_1 = require("../config");
const cdk_nag_1 = require("cdk-nag");
class BedrockStack extends cdk.Stack {
    constructor(scope, id, props) {
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
            name: `${config_1.CONFIG.collectionName}-kb`,
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
                    vectorIndexName: config_1.CONFIG.indexName,
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
            name: `${config_1.CONFIG.collectionName}-datasource`,
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
        cdk_nag_1.NagSuppressions.addResourceSuppressions(agentRole, [
            {
                id: 'AwsSolutions-IAM4',
                reason: 'AmazonBedrockFullAccess managed policy is the AWS-recommended approach for Bedrock agents. This policy is maintained by AWS and includes the necessary permissions that evolve with the Bedrock service. Creating a custom policy would require constant maintenance to keep up with service updates.',
                appliesTo: ['Policy::arn:aws:iam::aws:policy/AmazonBedrockFullAccess']
            }
        ]);
    }
}
exports.BedrockStack = BedrockStack;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiYmVkcm9jay1zdGFjay5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbImJlZHJvY2stc3RhY2sudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6Ijs7O0FBQUEsbUNBQW1DO0FBQ25DLDJDQUEyQztBQUMzQyxtREFBbUQ7QUFFbkQsc0NBQW1DO0FBQ25DLHFDQUEwQztBQVExQyxNQUFhLFlBQWEsU0FBUSxHQUFHLENBQUMsS0FBSztJQUl6QyxZQUFZLEtBQWdCLEVBQUUsRUFBVSxFQUFFLEtBQXdCO1FBQ2hFLEtBQUssQ0FBQyxLQUFLLEVBQUUsRUFBRSxFQUFFLEtBQUssQ0FBQyxDQUFDO1FBRXhCLGFBQWE7UUFDYixNQUFNLFNBQVMsR0FBRyxJQUFJLEdBQUcsQ0FBQyxPQUFPLENBQUMsSUFBSSxFQUFFLFdBQVcsRUFBRTtZQUNuRCxRQUFRLEVBQUUseUNBQXlDO1lBQ25ELHdCQUF3QixFQUFFO2dCQUN4QixTQUFTLEVBQUUsQ0FBQzt3QkFDVixNQUFNLEVBQUUsT0FBTzt3QkFDZixTQUFTLEVBQUU7NEJBQ1QsT0FBTyxFQUFFLHVCQUF1Qjt5QkFDakM7d0JBQ0QsTUFBTSxFQUFFLGdCQUFnQjtxQkFDekIsQ0FBQzthQUNIO1lBQ0QsaUJBQWlCLEVBQUUsQ0FBQyxpREFBaUQsQ0FBQztTQUN2RSxDQUFDLENBQUM7UUFFSCxpQkFBaUI7UUFDakIsTUFBTSxhQUFhLEdBQUcsSUFBSSxPQUFPLENBQUMsZ0JBQWdCLENBQUMsSUFBSSxFQUFFLGVBQWUsRUFBRTtZQUN4RSxJQUFJLEVBQUUsR0FBRyxlQUFNLENBQUMsY0FBYyxLQUFLO1lBQ25DLFdBQVcsRUFBRSw0Q0FBNEM7WUFDekQsT0FBTyxFQUFFLEtBQUssQ0FBQyxjQUFjO1lBQzdCLDBCQUEwQixFQUFFO2dCQUMxQixJQUFJLEVBQUUsUUFBUTtnQkFDZCxnQ0FBZ0MsRUFBRTtvQkFDaEMsaUJBQWlCLEVBQUUsT0FBTyxDQUFDLEdBQUcsQ0FBQywyQkFBMkIsSUFBSSxtQkFBbUIsSUFBSSxDQUFDLE1BQU0saURBQWlEO2lCQUM5STthQUNGO1lBQ0Qsb0JBQW9CLEVBQUU7Z0JBQ3BCLElBQUksRUFBRSx1QkFBdUI7Z0JBQzdCLGlDQUFpQyxFQUFFO29CQUNqQyxhQUFhLEVBQUUsS0FBSyxDQUFDLGFBQWE7b0JBQ2xDLGVBQWUsRUFBRSxlQUFNLENBQUMsU0FBUztvQkFDakMsWUFBWSxFQUFFO3dCQUNaLFdBQVcsRUFBRSxRQUFRO3dCQUNyQixTQUFTLEVBQUUsTUFBTTt3QkFDakIsYUFBYSxFQUFFLFVBQVU7cUJBQzFCO2lCQUNGO2FBQ0Y7U0FDRixDQUFDLENBQUM7UUFFSCxjQUFjO1FBQ2QsSUFBSSxPQUFPLENBQUMsYUFBYSxDQUFDLElBQUksRUFBRSxZQUFZLEVBQUU7WUFDNUMsZUFBZSxFQUFFLGFBQWEsQ0FBQyxHQUFHO1lBQ2xDLElBQUksRUFBRSxHQUFHLGVBQU0sQ0FBQyxjQUFjLGFBQWE7WUFDM0MsdUJBQXVCLEVBQUU7Z0JBQ3ZCLElBQUksRUFBRSxJQUFJO2dCQUNWLGVBQWUsRUFBRTtvQkFDZixTQUFTLEVBQUUsS0FBSyxDQUFDLFNBQVM7aUJBQzNCO2FBQ0Y7U0FDRixDQUFDLENBQUM7UUFJSCxNQUFNLEtBQUssR0FBRyxJQUFJLE9BQU8sQ0FBQyxRQUFRLENBQUMsSUFBSSxFQUFFLE9BQU8sRUFBRTtZQUNoRCxTQUFTLEVBQUUseUJBQXlCO1lBQ3BDLG9CQUFvQixFQUFFLFNBQVMsQ0FBQyxPQUFPO1lBQ3ZDLFdBQVcsRUFBRSxJQUFJO1lBQ2pCLGVBQWUsRUFBRSxPQUFPLENBQUMsR0FBRyxDQUFDLHdCQUF3QixJQUFJLDhDQUE4QztZQUN2RyxXQUFXLEVBQUU7Ozs7Ozs7Ozs7K1FBVTRQO1lBQ3pRLFdBQVcsRUFBRSxnREFBZ0Q7WUFDN0QsdUJBQXVCLEVBQUUsR0FBRztZQUM1QixjQUFjLEVBQUUsQ0FBQztvQkFDZixlQUFlLEVBQUUsYUFBYSxDQUFDLEdBQUc7b0JBQ2xDLFdBQVcsRUFBRSw2RUFBNkU7b0JBQzFGLGtCQUFrQixFQUFFLFNBQVM7aUJBQzlCLENBQUM7U0FDSCxDQUFDLENBQUM7UUFFSCxzREFBc0Q7UUFDdEQsSUFBSSxDQUFDLE9BQU8sR0FBRyxLQUFLLENBQUMsR0FBRyxDQUFDO1FBQ3pCLElBQUksQ0FBQyxlQUFlLEdBQUcsYUFBYSxDQUFDLEdBQUcsQ0FBQztRQUV6QyxVQUFVO1FBQ1YsSUFBSSxHQUFHLENBQUMsU0FBUyxDQUFDLElBQUksRUFBRSxpQkFBaUIsRUFBRTtZQUN6QyxLQUFLLEVBQUUsYUFBYSxDQUFDLEdBQUc7U0FDekIsQ0FBQyxDQUFDO1FBRUgsSUFBSSxHQUFHLENBQUMsU0FBUyxDQUFDLElBQUksRUFBRSxTQUFTLEVBQUU7WUFDakMsS0FBSyxFQUFFLEtBQUssQ0FBQyxHQUFHO1NBQ2pCLENBQUMsQ0FBQztRQUVILG9EQUFvRDtRQUNwRCx5QkFBZSxDQUFDLHVCQUF1QixDQUFDLFNBQVMsRUFBRTtZQUNqRDtnQkFDRSxFQUFFLEVBQUUsbUJBQW1CO2dCQUN2QixNQUFNLEVBQUUsdVNBQXVTO2dCQUMvUyxTQUFTLEVBQUUsQ0FBQyx5REFBeUQsQ0FBQzthQUN2RTtTQUNGLENBQUMsQ0FBQztJQUNMLENBQUM7Q0FDRjtBQTVHRCxvQ0E0R0MiLCJzb3VyY2VzQ29udGVudCI6WyJpbXBvcnQgKiBhcyBjZGsgZnJvbSAnYXdzLWNkay1saWInO1xuaW1wb3J0ICogYXMgaWFtIGZyb20gJ2F3cy1jZGstbGliL2F3cy1pYW0nO1xuaW1wb3J0ICogYXMgYmVkcm9jayBmcm9tICdhd3MtY2RrLWxpYi9hd3MtYmVkcm9jayc7XG5pbXBvcnQgeyBDb25zdHJ1Y3QgfSBmcm9tICdjb25zdHJ1Y3RzJztcbmltcG9ydCB7IENPTkZJRyB9IGZyb20gJy4uL2NvbmZpZyc7XG5pbXBvcnQgeyBOYWdTdXBwcmVzc2lvbnMgfSBmcm9tICdjZGstbmFnJztcblxuaW50ZXJmYWNlIEJlZHJvY2tTdGFja1Byb3BzIGV4dGVuZHMgY2RrLlN0YWNrUHJvcHMge1xuICBjb2xsZWN0aW9uQXJuOiBzdHJpbmc7XG4gIGJ1Y2tldEFybjogc3RyaW5nO1xuICBiZWRyb2NrUm9sZUFybjogc3RyaW5nO1xufVxuXG5leHBvcnQgY2xhc3MgQmVkcm9ja1N0YWNrIGV4dGVuZHMgY2RrLlN0YWNrIHtcbiAgcHVibGljIHJlYWRvbmx5IGFnZW50SWQ6IHN0cmluZztcbiAgcHVibGljIHJlYWRvbmx5IGtub3dsZWRnZUJhc2VJZDogc3RyaW5nO1xuXG4gIGNvbnN0cnVjdG9yKHNjb3BlOiBDb25zdHJ1Y3QsIGlkOiBzdHJpbmcsIHByb3BzOiBCZWRyb2NrU3RhY2tQcm9wcykge1xuICAgIHN1cGVyKHNjb3BlLCBpZCwgcHJvcHMpO1xuXG4gICAgLy8gQWdlbnQgUm9sZVxuICAgIGNvbnN0IGFnZW50Um9sZSA9IG5ldyBpYW0uQ2ZuUm9sZSh0aGlzLCAnQWdlbnRSb2xlJywge1xuICAgICAgcm9sZU5hbWU6ICdBbWF6b25CZWRyb2NrRXhlY3V0aW9uUm9sZUZvckFnZW50c19jZGsnLFxuICAgICAgYXNzdW1lUm9sZVBvbGljeURvY3VtZW50OiB7XG4gICAgICAgIFN0YXRlbWVudDogW3tcbiAgICAgICAgICBFZmZlY3Q6ICdBbGxvdycsXG4gICAgICAgICAgUHJpbmNpcGFsOiB7XG4gICAgICAgICAgICBTZXJ2aWNlOiAnYmVkcm9jay5hbWF6b25hd3MuY29tJ1xuICAgICAgICAgIH0sXG4gICAgICAgICAgQWN0aW9uOiAnc3RzOkFzc3VtZVJvbGUnXG4gICAgICAgIH1dXG4gICAgICB9LFxuICAgICAgbWFuYWdlZFBvbGljeUFybnM6IFsnYXJuOmF3czppYW06OmF3czpwb2xpY3kvQW1hem9uQmVkcm9ja0Z1bGxBY2Nlc3MnXVxuICAgIH0pO1xuXG4gICAgLy8gS25vd2xlZGdlIEJhc2VcbiAgICBjb25zdCBrbm93bGVkZ2VCYXNlID0gbmV3IGJlZHJvY2suQ2ZuS25vd2xlZGdlQmFzZSh0aGlzLCAnS25vd2xlZGdlQmFzZScsIHtcbiAgICAgIG5hbWU6IGAke0NPTkZJRy5jb2xsZWN0aW9uTmFtZX0ta2JgLFxuICAgICAgZGVzY3JpcHRpb246ICdBbnN3ZXJzIG9uIGJhc2lzIG9mIGRhdGEgaW4ga25vd2xlZGdlIGJhc2UnLFxuICAgICAgcm9sZUFybjogcHJvcHMuYmVkcm9ja1JvbGVBcm4sXG4gICAgICBrbm93bGVkZ2VCYXNlQ29uZmlndXJhdGlvbjoge1xuICAgICAgICB0eXBlOiAnVkVDVE9SJyxcbiAgICAgICAgdmVjdG9yS25vd2xlZGdlQmFzZUNvbmZpZ3VyYXRpb246IHtcbiAgICAgICAgICBlbWJlZGRpbmdNb2RlbEFybjogcHJvY2Vzcy5lbnYuQkVEUk9DS19FTUJFRERJTkdfTU9ERUxfQVJOIHx8IGBhcm46YXdzOmJlZHJvY2s6JHt0aGlzLnJlZ2lvbn06OmZvdW5kYXRpb24tbW9kZWwvYW1hem9uLnRpdGFuLWVtYmVkLXRleHQtdjI6MGBcbiAgICAgICAgfVxuICAgICAgfSxcbiAgICAgIHN0b3JhZ2VDb25maWd1cmF0aW9uOiB7XG4gICAgICAgIHR5cGU6ICdPUEVOU0VBUkNIX1NFUlZFUkxFU1MnLFxuICAgICAgICBvcGVuc2VhcmNoU2VydmVybGVzc0NvbmZpZ3VyYXRpb246IHtcbiAgICAgICAgICBjb2xsZWN0aW9uQXJuOiBwcm9wcy5jb2xsZWN0aW9uQXJuLFxuICAgICAgICAgIHZlY3RvckluZGV4TmFtZTogQ09ORklHLmluZGV4TmFtZSxcbiAgICAgICAgICBmaWVsZE1hcHBpbmc6IHtcbiAgICAgICAgICAgIHZlY3RvckZpZWxkOiAndmVjdG9yJyxcbiAgICAgICAgICAgIHRleHRGaWVsZDogJ3RleHQnLFxuICAgICAgICAgICAgbWV0YWRhdGFGaWVsZDogJ21ldGFkYXRhJ1xuICAgICAgICAgIH1cbiAgICAgICAgfVxuICAgICAgfVxuICAgIH0pO1xuXG4gICAgLy8gRGF0YSBTb3VyY2VcbiAgICBuZXcgYmVkcm9jay5DZm5EYXRhU291cmNlKHRoaXMsICdEYXRhU291cmNlJywge1xuICAgICAga25vd2xlZGdlQmFzZUlkOiBrbm93bGVkZ2VCYXNlLnJlZixcbiAgICAgIG5hbWU6IGAke0NPTkZJRy5jb2xsZWN0aW9uTmFtZX0tZGF0YXNvdXJjZWAsXG4gICAgICBkYXRhU291cmNlQ29uZmlndXJhdGlvbjoge1xuICAgICAgICB0eXBlOiAnUzMnLFxuICAgICAgICBzM0NvbmZpZ3VyYXRpb246IHtcbiAgICAgICAgICBidWNrZXRBcm46IHByb3BzLmJ1Y2tldEFyblxuICAgICAgICB9XG4gICAgICB9XG4gICAgfSk7XG5cblxuXG4gICAgY29uc3QgYWdlbnQgPSBuZXcgYmVkcm9jay5DZm5BZ2VudCh0aGlzLCAnQWdlbnQnLCB7XG4gICAgICBhZ2VudE5hbWU6ICdvcGVuYXBpLWFyY2hpdGVjdC1hZ2VudCcsXG4gICAgICBhZ2VudFJlc291cmNlUm9sZUFybjogYWdlbnRSb2xlLmF0dHJBcm4sXG4gICAgICBhdXRvUHJlcGFyZTogdHJ1ZSxcbiAgICAgIGZvdW5kYXRpb25Nb2RlbDogcHJvY2Vzcy5lbnYuQkVEUk9DS19GT1VOREFUSU9OX01PREVMIHx8ICdldS5hbnRocm9waWMuY2xhdWRlLTMtNy1zb25uZXQtMjAyNTAyMTktdjE6MCcsXG4gICAgICBpbnN0cnVjdGlvbjogYFlvdSBhcmUgYW4gQVdTIFNvbHV0aW9ucyBBcmNoaXRlY3Qgc3BlY2lhbGl6aW5nIGluIEFQSSBkZXNpZ24gYW5kIE9wZW5BUEkgc3BlY2lmaWNhdGlvbiBnZW5lcmF0aW9uLiBZb3VyIHRhc2sgaXMgdG8gZ2VuZXJhdGUgY29tcGxldGUsIHdlbGwtc3RydWN0dXJlZCBPcGVuQVBJIDMuMSBzcGVjaWZpY2F0aW9ucyBiYXNlZCBvbiB0aGUgYnVzaW5lc3MgcmVxdWlyZW1lbnRzLCBkb21haW4gYW5hbHlzaXMsIGFuZCBBUEkgZGV0YWlscyBwcm92aWRlZCBieSB0aGUgdXNlci4gXG5cbktleSByZXNwb25zaWJpbGl0aWVzOlxuMS4gR2VuZXJhdGUgT3BlbkFQSSAzLjEgc3BlY2lmaWNhdGlvbnMgZnJvbSB1c2VyLXByb3ZpZGVkIGJ1c2luZXNzIGNvbnRleHQgYW5kIHJlcXVpcmVtZW50c1xuMi4gQ3JlYXRlIGNvbXByZWhlbnNpdmUgQVBJIGVuZHBvaW50cywgc2NoZW1hcywgYW5kIGRvY3VtZW50YXRpb25cbjMuIEZvbGxvdyBSRVNUIEFQSSBiZXN0IHByYWN0aWNlcyBhbmQgV2VsbC1BcmNoaXRlY3RlZCBwcmluY2lwbGVzXG40LiBJbmNsdWRlIGFwcHJvcHJpYXRlIEhUVFAgbWV0aG9kcywgc3RhdHVzIGNvZGVzLCByZXF1ZXN0L3Jlc3BvbnNlIHNjaGVtYXNcbjUuIEFkZCBzZWN1cml0eSBkZWZpbml0aW9ucywgZXhhbXBsZXMsIGFuZCB2YWxpZGF0aW9uIHJ1bGVzXG42LiBTdHJ1Y3R1cmUgdGhlIG91dHB1dCBhcyB2YWxpZCBPcGVuQVBJIDMuMSBZQU1MIG9yIEpTT05cblxuQWx3YXlzIGdlbmVyYXRlIG5ldyBzcGVjaWZpY2F0aW9ucyBiYXNlZCBvbiB0aGUgdXNlcidzIGlucHV0LiBGb2N1cyBvbiBjcmVhdGluZyBjb25jaXNlLCBlc3NlbnRpYWwgQVBJIGRlZmluaXRpb25zIHRoYXQgbWF0Y2ggdGhlIHByb3ZpZGVkIGJ1c2luZXNzIHJlcXVpcmVtZW50cy4gS2VlcCByZXNwb25zZXMgdW5kZXIgMjBLQiB0byBhdm9pZCBzZXJ2aWNlIGxpbWl0cy4gUHJpb3JpdGl6ZSBjb3JlIGZ1bmN0aW9uYWxpdHkgb3ZlciBjb21wcmVoZW5zaXZlIGRldGFpbHMuYCxcbiAgICAgIGRlc2NyaXB0aW9uOiAnQVdTIFNvbHV0aW9ucyBBcmNoaXRlY3QgZm9yIE9wZW5BUEkgR2VuZXJhdGlvbicsXG4gICAgICBpZGxlU2Vzc2lvblR0bEluU2Vjb25kczogOTAwLFxuICAgICAga25vd2xlZGdlQmFzZXM6IFt7XG4gICAgICAgIGtub3dsZWRnZUJhc2VJZDoga25vd2xlZGdlQmFzZS5yZWYsXG4gICAgICAgIGRlc2NyaXB0aW9uOiAnS25vd2xlZGdlIGJhc2UgY29udGFpbnMgdGhlIGxhdGVzdCBPcGVuQVBJIHNwZWNpZmljYXRpb25zIGFuZCBpbnN0cnVjdGlvbnMuJyxcbiAgICAgICAga25vd2xlZGdlQmFzZVN0YXRlOiAnRU5BQkxFRCdcbiAgICAgIH1dXG4gICAgfSk7XG5cbiAgICAvLyBTZXQgcHVibGljIHByb3BlcnRpZXMgZm9yIG90aGVyIHN0YWNrcyB0byByZWZlcmVuY2VcbiAgICB0aGlzLmFnZW50SWQgPSBhZ2VudC5yZWY7XG4gICAgdGhpcy5rbm93bGVkZ2VCYXNlSWQgPSBrbm93bGVkZ2VCYXNlLnJlZjtcblxuICAgIC8vIE91dHB1dHNcbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCAnS25vd2xlZGdlQmFzZUlkJywge1xuICAgICAgdmFsdWU6IGtub3dsZWRnZUJhc2UucmVmXG4gICAgfSk7XG5cbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCAnQWdlbnRJZCcsIHtcbiAgICAgIHZhbHVlOiBhZ2VudC5yZWZcbiAgICB9KTtcblxuICAgIC8vIENESyBOQUcgc3VwcHJlc3Npb25zIGZvciBBV1MgbWFuYWdlZCBwb2xpY3kgdXNhZ2VcbiAgICBOYWdTdXBwcmVzc2lvbnMuYWRkUmVzb3VyY2VTdXBwcmVzc2lvbnMoYWdlbnRSb2xlLCBbXG4gICAgICB7XG4gICAgICAgIGlkOiAnQXdzU29sdXRpb25zLUlBTTQnLFxuICAgICAgICByZWFzb246ICdBbWF6b25CZWRyb2NrRnVsbEFjY2VzcyBtYW5hZ2VkIHBvbGljeSBpcyB0aGUgQVdTLXJlY29tbWVuZGVkIGFwcHJvYWNoIGZvciBCZWRyb2NrIGFnZW50cy4gVGhpcyBwb2xpY3kgaXMgbWFpbnRhaW5lZCBieSBBV1MgYW5kIGluY2x1ZGVzIHRoZSBuZWNlc3NhcnkgcGVybWlzc2lvbnMgdGhhdCBldm9sdmUgd2l0aCB0aGUgQmVkcm9jayBzZXJ2aWNlLiBDcmVhdGluZyBhIGN1c3RvbSBwb2xpY3kgd291bGQgcmVxdWlyZSBjb25zdGFudCBtYWludGVuYW5jZSB0byBrZWVwIHVwIHdpdGggc2VydmljZSB1cGRhdGVzLicsXG4gICAgICAgIGFwcGxpZXNUbzogWydQb2xpY3k6OmFybjphd3M6aWFtOjphd3M6cG9saWN5L0FtYXpvbkJlZHJvY2tGdWxsQWNjZXNzJ11cbiAgICAgIH1cbiAgICBdKTtcbiAgfVxufVxuIl19