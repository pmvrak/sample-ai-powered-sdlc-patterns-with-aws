"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.OpenSearchStack = void 0;
const cdk = require("aws-cdk-lib");
const s3 = require("aws-cdk-lib/aws-s3");
const iam = require("aws-cdk-lib/aws-iam");
const opensearchserverless = require("aws-cdk-lib/aws-opensearchserverless");
const config_1 = require("../config");
class OpenSearchStack extends cdk.Stack {
    constructor(scope, id, props) {
        super(scope, id, props);
        // Encryption Policy
        const encryptionPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'EncryptionPolicy', {
            name: `${config_1.CONFIG.collectionName}-security-policy`,
            type: 'encryption',
            description: 'Encryption policy for OpenSearch Serverless collection',
            policy: JSON.stringify({
                Rules: [{
                        ResourceType: 'collection',
                        Resource: [`collection/${config_1.CONFIG.collectionName}`]
                    }],
                AWSOwnedKey: true
            })
        });
        // Network Policy
        const networkPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'NetworkPolicy', {
            name: `${config_1.CONFIG.collectionName}-network-policy`,
            type: 'network',
            description: 'Network policy for OpenSearch Serverless collection',
            policy: JSON.stringify([{
                    Rules: [
                        { ResourceType: 'collection', Resource: [`collection/${config_1.CONFIG.collectionName}`] },
                        { ResourceType: 'dashboard', Resource: [`collection/${config_1.CONFIG.collectionName}`] }
                    ],
                    AllowFromPublic: true
                }])
        });
        // Bedrock Role
        this.bedrockRole = new iam.CfnRole(this, 'BedrockRole', {
            roleName: `AmazonBedrockExecutionRoleForKB-${config_1.CONFIG.collectionName}`,
            assumeRolePolicyDocument: {
                Statement: [{
                        Effect: 'Allow',
                        Principal: {
                            Service: 'bedrock.amazonaws.com'
                        },
                        Action: 'sts:AssumeRole',
                        Condition: {
                            StringEquals: {
                                'aws:SourceAccount': this.account
                            },
                            ArnLike: {
                                'aws:SourceArn': `arn:aws:bedrock:${this.region}:${this.account}:knowledge-base/*`
                            }
                        }
                    }]
            },
            policies: [
                {
                    policyName: 'OpensearchServerlessAccessPolicy',
                    policyDocument: {
                        Version: '2012-10-17',
                        Statement: [
                            {
                                Effect: 'Allow',
                                Action: [
                                    'aoss:APIAccessAll',
                                    'aoss:DashboardsAccessAll',
                                ],
                                Resource: `arn:aws:aoss:${this.region}:${this.account}:collection/*`
                            }
                        ]
                    }
                },
                {
                    policyName: 'BedrockAccessPolicy',
                    policyDocument: {
                        Version: '2012-10-17',
                        Statement: [
                            {
                                Effect: 'Allow',
                                Action: [
                                    'bedrock:ListCustomModels',
                                    'bedrock:InvokeModel'
                                ],
                                Resource: [
                                    `arn:aws:bedrock:${this.region}::foundation-model/*`,
                                    `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`
                                ]
                            }
                        ]
                    }
                },
                {
                    policyName: 'S3AccessForKnowledgeBase',
                    policyDocument: {
                        Version: '2012-10-17',
                        Statement: [
                            {
                                Effect: 'Allow',
                                Action: [
                                    's3:GetObject',
                                    's3:ListBucket',
                                    's3:GetBucketLocation',
                                    's3:GetObjectVersion',
                                    's3:ListBucketVersions'
                                ],
                                Resource: [
                                    `arn:aws:s3:::${config_1.CONFIG.collectionName}-${this.account}`,
                                    `arn:aws:s3:::${config_1.CONFIG.collectionName}-${this.account}/*`
                                ]
                            }
                        ]
                    }
                },
            ]
        });
        new opensearchserverless.CfnAccessPolicy(this, 'DataAccessPolicy', {
            name: `${config_1.CONFIG.collectionName}-access-policy`,
            type: 'data',
            description: 'Data access policy for OpenSearch Serverless collection',
            policy: JSON.stringify([
                {
                    Description: "Provided Access for Bedrock and IAM user",
                    Rules: [
                        {
                            ResourceType: 'index',
                            Resource: ['index/*/*'],
                            Permission: [
                                'aoss:ReadDocument',
                                'aoss:WriteDocument',
                                'aoss:CreateIndex',
                                'aoss:DeleteIndex',
                                'aoss:UpdateIndex',
                                'aoss:DescribeIndex'
                            ]
                        },
                        {
                            ResourceType: 'collection',
                            Resource: [`collection/${config_1.CONFIG.collectionName}`],
                            Permission: [
                                'aoss:CreateCollectionItems',
                                'aoss:DeleteCollectionItems',
                                'aoss:UpdateCollectionItems',
                                'aoss:DescribeCollectionItems'
                            ]
                        }
                    ],
                    Principal: [
                        config_1.CONFIG.iamUserArn,
                        this.bedrockRole.attrArn,
                        `arn:aws:iam::${this.account}:role/aws-service-role/bedrock.amazonaws.com/AWSServiceRoleForAmazonBedrock`
                    ]
                }
            ])
        });
        // S3 Access Logs Bucket
        const accessLogsBucket = new s3.CfnBucket(this, 'S3AccessLogsBucket', {
            bucketName: `${config_1.CONFIG.collectionName}-access-logs-${this.account}`,
            accessControl: 'Private',
            publicAccessBlockConfiguration: {
                blockPublicAcls: true,
                blockPublicPolicy: true,
                ignorePublicAcls: true,
                restrictPublicBuckets: true
            },
            bucketEncryption: {
                serverSideEncryptionConfiguration: [{
                        serverSideEncryptionByDefault: {
                            sseAlgorithm: 'AES256'
                        }
                    }]
            }
        });
        // S3 Bucket
        this.s3Bucket = new s3.CfnBucket(this, 'S3Bucket', {
            bucketName: `${config_1.CONFIG.collectionName}-${this.account}`,
            accessControl: 'Private',
            publicAccessBlockConfiguration: {
                blockPublicAcls: true,
                blockPublicPolicy: true,
                ignorePublicAcls: true,
                restrictPublicBuckets: true
            },
            versioningConfiguration: { status: "Enabled" },
            bucketEncryption: {
                serverSideEncryptionConfiguration: [{
                        serverSideEncryptionByDefault: {
                            sseAlgorithm: 'AES256'
                        }
                    }]
            },
            loggingConfiguration: {
                destinationBucketName: accessLogsBucket.ref,
                logFilePrefix: 'access-logs/'
            }
        });
        // Add bucket policy to enforce SSL for access logs bucket
        const accessLogsBucketPolicy = new s3.CfnBucketPolicy(this, 'S3AccessLogsBucketPolicy', {
            bucket: accessLogsBucket.ref,
            policyDocument: {
                Statement: [{
                        Sid: 'DenyInsecureConnections',
                        Effect: 'Deny',
                        Principal: '*',
                        Action: 's3:*',
                        Resource: [
                            accessLogsBucket.attrArn,
                            `${accessLogsBucket.attrArn}/*`
                        ],
                        Condition: {
                            Bool: {
                                'aws:SecureTransport': 'false'
                            }
                        }
                    }]
            }
        });
        // Add bucket policy to enforce SSL for main bucket
        const bucketPolicy = new s3.CfnBucketPolicy(this, 'S3BucketPolicy', {
            bucket: this.s3Bucket.ref,
            policyDocument: {
                Statement: [{
                        Sid: 'DenyInsecureConnections',
                        Effect: 'Deny',
                        Principal: '*',
                        Action: 's3:*',
                        Resource: [
                            this.s3Bucket.attrArn,
                            `${this.s3Bucket.attrArn}/*`
                        ],
                        Condition: {
                            Bool: {
                                'aws:SecureTransport': 'false'
                            }
                        }
                    }]
            }
        });
        // S3 bucket to allow deletion
        this.s3Bucket.cfnOptions.deletionPolicy = cdk.CfnDeletionPolicy.DELETE;
        // Collection
        this.collection = new opensearchserverless.CfnCollection(this, 'Collection', {
            name: config_1.CONFIG.collectionName,
            type: 'VECTORSEARCH',
            description: 'Collection for vector search data'
        });
        this.collection.addDependency(encryptionPolicy);
        this.collection.addDependency(networkPolicy);
        // Outputs
        new cdk.CfnOutput(this, 'CollectionArn', {
            value: this.collection.attrArn,
            exportName: 'OpenSearchCollectionArn'
        });
        new cdk.CfnOutput(this, 'BucketArn', {
            value: this.s3Bucket.attrArn,
            exportName: 'OpenSearchBucketArn'
        });
        new cdk.CfnOutput(this, 'BedrockRoleArn', {
            value: this.bedrockRole.attrArn,
            exportName: 'BedrockRoleArn'
        });
        new cdk.CfnOutput(this, 'BucketName', {
            value: this.s3Bucket.ref,
            exportName: 'BucketName'
        });
    }
}
exports.OpenSearchStack = OpenSearchStack;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoib3BlbnNlYXJjaC1zdGFjay5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbIm9wZW5zZWFyY2gtc3RhY2sudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6Ijs7O0FBQUEsbUNBQW1DO0FBQ25DLHlDQUF5QztBQUN6QywyQ0FBMkM7QUFDM0MsNkVBQTZFO0FBRTdFLHNDQUFtQztBQUVuQyxNQUFhLGVBQWdCLFNBQVEsR0FBRyxDQUFDLEtBQUs7SUFLNUMsWUFBWSxLQUFnQixFQUFFLEVBQVUsRUFBRSxLQUFzQjtRQUM5RCxLQUFLLENBQUMsS0FBSyxFQUFFLEVBQUUsRUFBRSxLQUFLLENBQUMsQ0FBQztRQUV4QixvQkFBb0I7UUFDcEIsTUFBTSxnQkFBZ0IsR0FBRyxJQUFJLG9CQUFvQixDQUFDLGlCQUFpQixDQUFDLElBQUksRUFBRSxrQkFBa0IsRUFBRTtZQUM1RixJQUFJLEVBQUUsR0FBRyxlQUFNLENBQUMsY0FBYyxrQkFBa0I7WUFDaEQsSUFBSSxFQUFFLFlBQVk7WUFDbEIsV0FBVyxFQUFFLHdEQUF3RDtZQUNyRSxNQUFNLEVBQUUsSUFBSSxDQUFDLFNBQVMsQ0FBQztnQkFDckIsS0FBSyxFQUFFLENBQUM7d0JBQ04sWUFBWSxFQUFFLFlBQVk7d0JBQzFCLFFBQVEsRUFBRSxDQUFDLGNBQWMsZUFBTSxDQUFDLGNBQWMsRUFBRSxDQUFDO3FCQUNsRCxDQUFDO2dCQUNGLFdBQVcsRUFBRSxJQUFJO2FBQ2xCLENBQUM7U0FDSCxDQUFDLENBQUM7UUFFSCxpQkFBaUI7UUFDakIsTUFBTSxhQUFhLEdBQUcsSUFBSSxvQkFBb0IsQ0FBQyxpQkFBaUIsQ0FBQyxJQUFJLEVBQUUsZUFBZSxFQUFFO1lBQ3RGLElBQUksRUFBRSxHQUFHLGVBQU0sQ0FBQyxjQUFjLGlCQUFpQjtZQUMvQyxJQUFJLEVBQUUsU0FBUztZQUNmLFdBQVcsRUFBRSxxREFBcUQ7WUFDbEUsTUFBTSxFQUFFLElBQUksQ0FBQyxTQUFTLENBQUMsQ0FBQztvQkFDdEIsS0FBSyxFQUFFO3dC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QUFLLEVBQUUsSUFBSSxDQUFDLFVBQVUsQ0FBQyxPQUFPO1lBQzlCLFVBQVUsRUFBRSx5QkFBeUI7U0FDdEMsQ0FBQyxDQUFDO1FBRUgsSUFBSSxHQUFHLENBQUMsU0FBUyxDQUFDLElBQUksRUFBRSxXQUFXLEVBQUU7WUFDbkMsS0FBSyxFQUFFLElBQUksQ0FBQyxRQUFRLENBQUMsT0FBTztZQUM1QixVQUFVLEVBQUUscUJBQXFCO1NBQ2xDLENBQUMsQ0FBQztRQUVILElBQUksR0FBRyxDQUFDLFNBQVMsQ0FBQyxJQUFJLEVBQUUsZ0JBQWdCLEVBQUU7WUFDeEMsS0FBSyxFQUFFLElBQUksQ0FBQyxXQUFXLENBQUMsT0FBTztZQUMvQixVQUFVLEVBQUUsZ0JBQWdCO1NBQzdCLENBQUMsQ0FBQztRQUVILElBQUksR0FBRyxDQUFDLFNBQVMsQ0FBQyxJQUFJLEVBQUUsWUFBWSxFQUFFO1lBQ3BDLEtBQUssRUFBRSxJQUFJLENBQUMsUUFBUSxDQUFDLEdBQUc7WUFDeEIsVUFBVSxFQUFFLFlBQVk7U0FDekIsQ0FBQyxDQUFDO0lBR0wsQ0FBQztDQUNGO0FBM1JELDBDQTJSQyIsInNvdXJjZXNDb250ZW50IjpbImltcG9ydCAqIGFzIGNkayBmcm9tICdhd3MtY2RrLWxpYic7XG5pbXBvcnQgKiBhcyBzMyBmcm9tICdhd3MtY2RrLWxpYi9hd3MtczMnO1xuaW1wb3J0ICogYXMgaWFtIGZyb20gJ2F3cy1jZGstbGliL2F3cy1pYW0nO1xuaW1wb3J0ICogYXMgb3BlbnNlYXJjaHNlcnZlcmxlc3MgZnJvbSAnYXdzLWNkay1saWIvYXdzLW9wZW5zZWFyY2hzZXJ2ZXJsZXNzJztcbmltcG9ydCB7IENvbnN0cnVjdCB9IGZyb20gJ2NvbnN0cnVjdHMnO1xuaW1wb3J0IHsgQ09ORklHIH0gZnJvbSAnLi4vY29uZmlnJztcblxuZXhwb3J0IGNsYXNzIE9wZW5TZWFyY2hTdGFjayBleHRlbmRzIGNkay5TdGFjayB7XG4gIHB1YmxpYyByZWFkb25seSBjb2xsZWN0aW9uOiBvcGVuc2VhcmNoc2VydmVybGVzcy5DZm5Db2xsZWN0aW9uO1xuICBwdWJsaWMgcmVhZG9ubHkgczNCdWNrZXQ6IHMzLkNmbkJ1Y2tldDtcbiAgcHVibGljIHJlYWRvbmx5IGJlZHJvY2tSb2xlOiBpYW0uQ2ZuUm9sZTtcblxuICBjb25zdHJ1Y3RvcihzY29wZTogQ29uc3RydWN0LCBpZDogc3RyaW5nLCBwcm9wcz86IGNkay5TdGFja1Byb3BzKSB7XG4gICAgc3VwZXIoc2NvcGUsIGlkLCBwcm9wcyk7XG5cbiAgICAvLyBFbmNyeXB0aW9uIFBvbGljeVxuICAgIGNvbnN0IGVuY3J5cHRpb25Qb2xpY3kgPSBuZXcgb3BlbnNlYXJjaHNlcnZlcmxlc3MuQ2ZuU2VjdXJpdHlQb2xpY3kodGhpcywgJ0VuY3J5cHRpb25Qb2xpY3knLCB7XG4gICAgICBuYW1lOiBgJHtDT05GSUcuY29sbGVjdGlvbk5hbWV9LXNlY3VyaXR5LXBvbGljeWAsXG4gICAgICB0eXBlOiAnZW5jcnlwdGlvbicsXG4gICAgICBkZXNjcmlwdGlvbjogJ0VuY3J5cHRpb24gcG9saWN5IGZvciBPcGVuU2VhcmNoIFNlcnZlcmxlc3MgY29sbGVjdGlvbicsXG4gICAgICBwb2xpY3k6IEpTT04uc3RyaW5naWZ5KHtcbiAgICAgICAgUnVsZXM6IFt7XG4gICAgICAgICAgUmVzb3VyY2VUeXBlOiAnY29sbGVjdGlvbicsXG4gICAgICAgICAgUmVzb3VyY2U6IFtgY29sbGVjdGlvbi8ke0NPTkZJRy5jb2xsZWN0aW9uTmFtZX1gXVxuICAgICAgICB9XSxcbiAgICAgICAgQVdTT3duZWRLZXk6IHRydWVcbiAgICAgIH0pXG4gICAgfSk7XG5cbiAgICAvLyBOZXR3b3JrIFBvbGljeVxuICAgIGNvbnN0IG5ldHdvcmtQb2xpY3kgPSBuZXcgb3BlbnNlYXJjaHNlcnZlcmxlc3MuQ2ZuU2VjdXJpdHlQb2xpY3kodGhpcywgJ05ldHdvcmtQb2xpY3knLCB7XG4gICAgICBuYW1lOiBgJHtDT05GSUcuY29sbGVjdGlvbk5hbWV9LW5ldHdvcmstcG9saWN5YCxcbiAgICAgIHR5cGU6ICduZXR3b3JrJyxcbiAgICAgIGRlc2NyaXB0aW9uOiAnTmV0d29yayBwb2xpY3kgZm9yIE9wZW5TZWFyY2ggU2VydmVybGVzcyBjb2xsZWN0aW9uJyxcbiAgICAgIHBvbGljeTogSlNPTi5zdHJpbmdpZnkoW3tcbiAgICAgICAgUnVsZXM6IFtcbiAgICAgICAgICB7IFJlc291cmNlVHlwZTogJ2NvbGxlY3Rpb24nLCBSZXNvdXJjZTogW2Bjb2xsZWN0aW9uLyR7Q09ORklHLmNvbGxlY3Rpb25OYW1lfWBdIH0sXG4gICAgICAgICAgeyBSZXNvdXJjZVR5cGU6ICdkYXNoYm9hcmQnLCBSZXNvdXJjZTogW2Bjb2xsZWN0aW9uLyR7Q09ORklHLmNvbGxlY3Rpb25OYW1lfWBdIH1cbiAgICAgICAgXSxcbiAgICAgICAgQWxsb3dGcm9tUHVibGljOiB0cnVlXG4gICAgICB9XSlcbiAgICB9KTtcblxuXG5cbiAgICAvLyBCZWRyb2NrIFJvbGVcbiAgICB0aGlzLmJlZHJvY2tSb2xlID0gbmV3IGlhbS5DZm5Sb2xlKHRoaXMsICdCZWRyb2NrUm9sZScsIHtcbiAgICAgICAgcm9sZU5hbWU6IGBBbWF6b25CZWRyb2NrRXhlY3V0aW9uUm9sZUZvcktCLSR7Q09ORklHLmNvbGxlY3Rpb25OYW1lfWAsXG4gICAgICAgIGFzc3VtZVJvbGVQb2xpY3lEb2N1bWVudDoge1xuICAgICAgICAgIFN0YXRlbWVudDogW3tcbiAgICAgICAgICAgIEVmZmVjdDogJ0FsbG93JyxcbiAgICAgICAgICAgIFByaW5jaXBhbDoge1xuICAgICAgICAgICAgICBTZXJ2aWNlOiAnYmVkcm9jay5hbWF6b25hd3MuY29tJ1xuICAgICAgICAgICAgfSxcbiAgICAgICAgICAgIEFjdGlvbjogJ3N0czpBc3N1bWVSb2xlJyxcbiAgICAgICAgICAgIENvbmRpdGlvbjoge1xuICAgICAgICAgICAgICBTdHJpbmdFcXVhbHM6IHtcbiAgICAgICAgICAgICAgICAnYXdzOlNvdXJjZUFjY291bnQnOiB0aGlzLmFjY291bnRcbiAgICAgICAgICAgICAgfSxcbiAgICAgICAgICAgICAgQXJuTGlrZToge1xuICAgICAgICAgICAgICAgICdhd3M6U291cmNlQXJuJzogYGFybjphd3M6YmVkcm9jazoke3RoaXMucmVnaW9ufToke3RoaXMuYWNjb3VudH06a25vd2xlZGdlLWJhc2UvKmBcbiAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgfVxuICAgICAgICAgIH1dXG4gICAgICAgIH0sXG4gICAgICAgIHBvbGljaWVzOiBbXG4gICAgICAgICAgICB7XG4gICAgICAgICAgICAgICAgcG9saWN5TmFtZTogJ09wZW5zZWFyY2hTZXJ2ZXJsZXNzQWNjZXNzUG9saWN5JyxcbiAgICAgICAgICAgICAgICBwb2xpY3lEb2N1bWVudDoge1xuICAgICAgICAgICAgICAgICAgVmVyc2lvbjogJzIwMTItMTAtMTcnLFxuICAgICAgICAgICAgICAgICAgU3RhdGVtZW50OiBbXG4gICAgICAgICAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgICAgICAgICBFZmZlY3Q6ICdBbGxvdycsXG4gICAgICAgICAgICAgICAgICAgICAgQWN0aW9uOiBbXG4gICAgICAgICAgICAgICAgICAgICAgICAnYW9zczpBUElBY2Nlc3NBbGwnLFxuICAgICAgICAgICAgICAgICAgICAgICAgJ2Fvc3M6RGFzaGJvYXJkc0FjY2Vzc0FsbCcsXG4gICAgICAgICAgICAgICAgICAgICAgXSxcbiAgICAgICAgICAgICAgICAgICAgICBSZXNvdXJjZTogYGFybjphd3M6YW9zczoke3RoaXMucmVnaW9ufToke3RoaXMuYWNjb3VudH06Y29sbGVjdGlvbi8qYFxuICAgICAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICAgICAgICBdXG4gICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgICB9LFxuICAgICAgICAgICAgICB7XG4gICAgICAgICAgICAgICAgcG9saWN5TmFtZTogJ0JlZHJvY2tBY2Nlc3NQb2xpY3knLFxuICAgICAgICAgICAgICAgIHBvbGljeURvY3VtZW50OiB7XG4gICAgICAgICAgICAgICAgICBWZXJzaW9uOiAnMjAxMi0xMC0xNycsXG4gICAgICAgICAgICAgICAgICBTdGF0ZW1lbnQ6IFtcbiAgICAgICAgICAgICAgICAgICAge1xuICAgICAgICAgICAgICAgICAgICAgIEVmZmVjdDogJ0FsbG93JyxcbiAgICAgICAgICAgICAgICAgICAgICBBY3Rpb246IFtcbiAgICAgICAgICAgICAgICAgICAgICAgICdiZWRyb2NrOkxpc3RDdXN0b21Nb2RlbHMnLFxuICAgICAgICAgICAgICAgICAgICAgICAgJ2JlZHJvY2s6SW52b2tlTW9kZWwnXG4gICAgICAgICAgICAgICAgICAgICAgXSxcbiAgICAgICAgICAgICAgICAgICAgICBSZXNvdXJjZTogW1xuICAgICAgICAgICAgICAgICAgICAgICAgYGFybjphd3M6YmVkcm9jazoke3RoaXMucmVnaW9ufTo6Zm91bmRhdGlvbi1tb2RlbC8qYCxcbiAgICAgICAgICAgICAgICAgICAgICAgIGBhcm46YXdzOmJlZHJvY2s6JHt0aGlzLnJlZ2lvbn06OmZvdW5kYXRpb24tbW9kZWwvYW1hem9uLnRpdGFuLWVtYmVkLXRleHQtdjI6MGBcbiAgICAgICAgICAgICAgICAgICAgICBdXG4gICAgICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICAgIF1cbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICAgIH0sXG4gICAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgICBwb2xpY3lOYW1lOiAnUzNBY2Nlc3NGb3JLbm93bGVkZ2VCYXNlJyxcbiAgICAgICAgICAgICAgICBwb2xpY3lEb2N1bWVudDoge1xuICAgICAgICAgICAgICAgICAgVmVyc2lvbjogJzIwMTItMTAtMTcnLFxuICAgICAgICAgICAgICAgICAgU3RhdGVtZW50OiBbXG4gICAgICAgICAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgICAgICAgICBFZmZlY3Q6ICdBbGxvdycsXG4gICAgICAgICAgICAgICAgICAgICAgQWN0aW9uOiBbXG4gICAgICAgICAgICAgICAgICAgICAgICAnczM6R2V0T2JqZWN0JyxcbiAgICAgICAgICAgICAgICAgICAgICAgICdzMzpMaXN0QnVja2V0JyxcbiAgICAgICAgICAgICAgICAgICAgICAgICdzMzpHZXRCdWNrZXRMb2NhdGlvbicsXG4gICAgICAgICAgICAgICAgICAgICAgICAnczM6R2V0T2JqZWN0VmVyc2lvbicsXG4gICAgICAgICAgICAgICAgICAgICAgICAnczM6TGlzdEJ1Y2tldFZlcnNpb25zJ1xuICAgICAgICAgICAgICAgICAgICAgIF0sXG4gICAgICAgICAgICAgICAgICAgICAgUmVzb3VyY2U6IFsgXG4gICAgICAgICAgICAgICAgICAgICAgYGFybjphd3M6czM6Ojoke0NPTkZJRy5jb2xsZWN0aW9uTmFtZX0tJHt0aGlzLmFjY291bnR9YCxcbiAgICAgICAgICAgICAgICAgICAgICBgYXJuOmF3czpzMzo6OiR7Q09ORklHLmNvbGxlY3Rpb25OYW1lfS0ke3RoaXMuYWNjb3VudH0vKmBdXG4gICAgICAgIFxuICAgICAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICAgICAgICBdXG4gICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgICB9LFxuICAgICAgICBdXG4gICAgICB9KTtcbiAgXG5cbiAgICBuZXcgb3BlbnNlYXJjaHNlcnZlcmxlc3MuQ2ZuQWNjZXNzUG9saWN5KHRoaXMsICdEYXRhQWNjZXNzUG9saWN5Jywge1xuICAgICAgICBuYW1lOiBgJHtDT05GSUcuY29sbGVjdGlvbk5hbWV9LWFjY2Vzcy1wb2xpY3lgLFxuICAgICAgICB0eXBlOiAnZGF0YScsXG4gICAgICAgIGRlc2NyaXB0aW9uOiAnRGF0YSBhY2Nlc3MgcG9saWN5IGZvciBPcGVuU2VhcmNoIFNlcnZlcmxlc3MgY29sbGVjdGlvbicsXG4gICAgICAgIHBvbGljeTogSlNPTi5zdHJpbmdpZnkoW1xuICAgICAgICAgIHtcbiAgICAgICAgICAgIERlc2NyaXB0aW9uOiBcIlByb3ZpZGVkIEFjY2VzcyBmb3IgQmVkcm9jayBhbmQgSUFNIHVzZXJcIixcbiAgICAgICAgICAgIFJ1bGVzOiBbXG4gICAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgICBSZXNvdXJjZVR5cGU6ICdpbmRleCcsXG4gICAgICAgICAgICAgICAgUmVzb3VyY2U6IFsnaW5kZXgvKi8qJ10sXG4gICAgICAgICAgICAgICAgUGVybWlzc2lvbjogW1xuICAgICAgICAgICAgICAgICAgJ2Fvc3M6UmVhZERvY3VtZW50JyxcbiAgICAgICAgICAgICAgICAgICdhb3NzOldyaXRlRG9jdW1lbnQnLFxuICAgICAgICAgICAgICAgICAgJ2Fvc3M6Q3JlYXRlSW5kZXgnLFxuICAgICAgICAgICAgICAgICAgJ2Fvc3M6RGVsZXRlSW5kZXgnLFxuICAgICAgICAgICAgICAgICAgJ2Fvc3M6VXBkYXRlSW5kZXgnLFxuICAgICAgICAgICAgICAgICAgJ2Fvc3M6RGVzY3JpYmVJbmRleCdcbiAgICAgICAgICAgICAgICBdXG4gICAgICAgICAgICAgIH0sXG4gICAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgICBSZXNvdXJjZVR5cGU6ICdjb2xsZWN0aW9uJyxcbiAgICAgICAgICAgICAgICBSZXNvdXJjZTogW2Bjb2xsZWN0aW9uLyR7Q09ORklHLmNvbGxlY3Rpb25OYW1lfWBdLFxuICAgICAgICAgICAgICAgIFBlcm1pc3Npb246IFtcbiAgICAgICAgICAgICAgICAgICdhb3NzOkNyZWF0ZUNvbGxlY3Rpb25JdGVtcycsXG4gICAgICAgICAgICAgICAgICAnYW9zczpEZWxldGVDb2xsZWN0aW9uSXRlbXMnLFxuICAgICAgICAgICAgICAgICAgJ2Fvc3M6VXBkYXRlQ29sbGVjdGlvbkl0ZW1zJyxcbiAgICAgICAgICAgICAgICAgICdhb3NzOkRlc2NyaWJlQ29sbGVjdGlvbkl0ZW1zJ1xuICAgICAgICAgICAgICAgIF1cbiAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgXSxcbiAgICAgICAgICAgIFByaW5jaXBhbDogW1xuICAgICAgICAgICAgICBDT05GSUcuaWFtVXNlckFybixcbiAgICAgICAgICAgICAgdGhpcy5iZWRyb2NrUm9sZS5hdHRyQXJuLFxuICAgICAgICAgICAgICBgYXJuOmF3czppYW06OiR7dGhpcy5hY2NvdW50fTpyb2xlL2F3cy1zZXJ2aWNlLXJvbGUvYmVkcm9jay5hbWF6b25hd3MuY29tL0FXU1NlcnZpY2VSb2xlRm9yQW1hem9uQmVkcm9ja2BcbiAgICAgICAgICAgIF1cbiAgICAgICAgICB9XG4gICAgICAgIF0pXG4gICAgICB9KTtcblxuICAgIC8vIFMzIEFjY2VzcyBMb2dzIEJ1Y2tldFxuICAgIGNvbnN0IGFjY2Vzc0xvZ3NCdWNrZXQgPSBuZXcgczMuQ2ZuQnVja2V0KHRoaXMsICdTM0FjY2Vzc0xvZ3NCdWNrZXQnLCB7XG4gICAgICBidWNrZXROYW1lOiBgJHtDT05GSUcuY29sbGVjdGlvbk5hbWV9LWFjY2Vzcy1sb2dzLSR7dGhpcy5hY2NvdW50fWAsXG4gICAgICBhY2Nlc3NDb250cm9sOiAnUHJpdmF0ZScsXG4gICAgICBwdWJsaWNBY2Nlc3NCbG9ja0NvbmZpZ3VyYXRpb246IHtcbiAgICAgICAgYmxvY2tQdWJsaWNBY2xzOiB0cnVlLFxuICAgICAgICBibG9ja1B1YmxpY1BvbGljeTogdHJ1ZSxcbiAgICAgICAgaWdub3JlUHVibGljQWNsczogdHJ1ZSxcbiAgICAgICAgcmVzdHJpY3RQdWJsaWNCdWNrZXRzOiB0cnVlXG4gICAgICB9LFxuICAgICAgYnVja2V0RW5jcnlwdGlvbjoge1xuICAgICAgICBzZXJ2ZXJTaWRlRW5jcnlwdGlvbkNvbmZpZ3VyYXRpb246IFt7XG4gICAgICAgICAgc2VydmVyU2lkZUVuY3J5cHRpb25CeURlZmF1bHQ6IHtcbiAgICAgICAgICAgIHNzZUFsZ29yaXRobTogJ0FFUzI1NidcbiAgICAgICAgICB9XG4gICAgICAgIH1dXG4gICAgICB9XG4gICAgfSk7XG5cbiAgICAvLyBTMyBCdWNrZXRcbiAgICB0aGlzLnMzQnVja2V0ID0gbmV3IHMzLkNmbkJ1Y2tldCh0aGlzLCAnUzNCdWNrZXQnLCB7XG4gICAgICBidWNrZXROYW1lOiBgJHtDT05GSUcuY29sbGVjdGlvbk5hbWV9LSR7dGhpcy5hY2NvdW50fWAsXG4gICAgICBhY2Nlc3NDb250cm9sOiAnUHJpdmF0ZScgLFxuICAgICAgcHVibGljQWNjZXNzQmxvY2tDb25maWd1cmF0aW9uOiB7XG4gICAgICAgIGJsb2NrUHVibGljQWNsczogdHJ1ZSxcbiAgICAgICAgYmxvY2tQdWJsaWNQb2xpY3k6IHRydWUsXG4gICAgICAgIGlnbm9yZVB1YmxpY0FjbHM6IHRydWUsXG4gICAgICAgIHJlc3RyaWN0UHVibGljQnVja2V0czogdHJ1ZVxuICAgICAgfSxcbiAgICAgIHZlcnNpb25pbmdDb25maWd1cmF0aW9uOiB7IHN0YXR1czogXCJFbmFibGVkXCIgfSxcbiAgICAgIGJ1Y2tldEVuY3J5cHRpb246IHtcbiAgICAgICAgc2VydmVyU2lkZUVuY3J5cHRpb25Db25maWd1cmF0aW9uOiBbe1xuICAgICAgICAgIHNlcnZlclNpZGVFbmNyeXB0aW9uQnlEZWZhdWx0OiB7XG4gICAgICAgICAgICBzc2VBbGdvcml0aG06ICdBRVMyNTYnXG4gICAgICAgICAgfVxuICAgICAgICB9XVxuICAgICAgfSxcbiAgICAgIGxvZ2dpbmdDb25maWd1cmF0aW9uOiB7XG4gICAgICAgIGRlc3RpbmF0aW9uQnVja2V0TmFtZTogYWNjZXNzTG9nc0J1Y2tldC5yZWYsXG4gICAgICAgIGxvZ0ZpbGVQcmVmaXg6ICdhY2Nlc3MtbG9ncy8nXG4gICAgICB9XG4gICAgfSk7XG5cbiAgICAvLyBBZGQgYnVja2V0IHBvbGljeSB0byBlbmZvcmNlIFNTTCBmb3IgYWNjZXNzIGxvZ3MgYnVja2V0XG4gICAgY29uc3QgYWNjZXNzTG9nc0J1Y2tldFBvbGljeSA9IG5ldyBzMy5DZm5CdWNrZXRQb2xpY3kodGhpcywgJ1MzQWNjZXNzTG9nc0J1Y2tldFBvbGljeScsIHtcbiAgICAgIGJ1Y2tldDogYWNjZXNzTG9nc0J1Y2tldC5yZWYsXG4gICAgICBwb2xpY3lEb2N1bWVudDoge1xuICAgICAgICBTdGF0ZW1lbnQ6IFt7XG4gICAgICAgICAgU2lkOiAnRGVueUluc2VjdXJlQ29ubmVjdGlvbnMnLFxuICAgICAgICAgIEVmZmVjdDogJ0RlbnknLFxuICAgICAgICAgIFByaW5jaXBhbDogJyonLFxuICAgICAgICAgIEFjdGlvbjogJ3MzOionLFxuICAgICAgICAgIFJlc291cmNlOiBbXG4gICAgICAgICAgICBhY2Nlc3NMb2dzQnVja2V0LmF0dHJBcm4sXG4gICAgICAgICAgICBgJHthY2Nlc3NMb2dzQnVja2V0LmF0dHJBcm59LypgXG4gICAgICAgICAgXSxcbiAgICAgICAgICBDb25kaXRpb246IHtcbiAgICAgICAgICAgIEJvb2w6IHtcbiAgICAgICAgICAgICAgJ2F3czpTZWN1cmVUcmFuc3BvcnQnOiAnZmFsc2UnXG4gICAgICAgICAgICB9XG4gICAgICAgICAgfVxuICAgICAgICB9XVxuICAgICAgfVxuICAgIH0pO1xuXG4gICAgLy8gQWRkIGJ1Y2tldCBwb2xpY3kgdG8gZW5mb3JjZSBTU0wgZm9yIG1haW4gYnVja2V0XG4gICAgY29uc3QgYnVja2V0UG9saWN5ID0gbmV3IHMzLkNmbkJ1Y2tldFBvbGljeSh0aGlzLCAnUzNCdWNrZXRQb2xpY3knLCB7XG4gICAgICBidWNrZXQ6IHRoaXMuczNCdWNrZXQucmVmLFxuICAgICAgcG9saWN5RG9jdW1lbnQ6IHtcbiAgICAgICAgU3RhdGVtZW50OiBbe1xuICAgICAgICAgIFNpZDogJ0RlbnlJbnNlY3VyZUNvbm5lY3Rpb25zJyxcbiAgICAgICAgICBFZmZlY3Q6ICdEZW55JyxcbiAgICAgICAgICBQcmluY2lwYWw6ICcqJyxcbiAgICAgICAgICBBY3Rpb246ICdzMzoqJyxcbiAgICAgICAgICBSZXNvdXJjZTogW1xuICAgICAgICAgICAgdGhpcy5zM0J1Y2tldC5hdHRyQXJuLFxuICAgICAgICAgICAgYCR7dGhpcy5zM0J1Y2tldC5hdHRyQXJufS8qYFxuICAgICAgICAgIF0sXG4gICAgICAgICAgQ29uZGl0aW9uOiB7XG4gICAgICAgICAgICBCb29sOiB7XG4gICAgICAgICAgICAgICdhd3M6U2VjdXJlVHJhbnNwb3J0JzogJ2ZhbHNlJ1xuICAgICAgICAgICAgfVxuICAgICAgICAgIH1cbiAgICAgICAgfV1cbiAgICAgIH1cbiAgICB9KTtcblxuICAgIC8vIFMzIGJ1Y2tldCB0byBhbGxvdyBkZWxldGlvblxuICAgIHRoaXMuczNCdWNrZXQuY2ZuT3B0aW9ucy5kZWxldGlvblBvbGljeSA9IGNkay5DZm5EZWxldGlvblBvbGljeS5ERUxFVEU7XG5cbiAgICAvLyBDb2xsZWN0aW9uXG4gICAgdGhpcy5jb2xsZWN0aW9uID0gbmV3IG9wZW5zZWFyY2hzZXJ2ZXJsZXNzLkNmbkNvbGxlY3Rpb24odGhpcywgJ0NvbGxlY3Rpb24nLCB7XG4gICAgICBuYW1lOiBDT05GSUcuY29sbGVjdGlvbk5hbWUsXG4gICAgICB0eXBlOiAnVkVDVE9SU0VBUkNIJyxcbiAgICAgIGRlc2NyaXB0aW9uOiAnQ29sbGVjdGlvbiBmb3IgdmVjdG9yIHNlYXJjaCBkYXRhJ1xuICAgIH0pO1xuXG4gICAgdGhpcy5jb2xsZWN0aW9uLmFkZERlcGVuZGVuY3koZW5jcnlwdGlvblBvbGljeSk7XG4gICAgdGhpcy5jb2xsZWN0aW9uLmFkZERlcGVuZGVuY3kobmV0d29ya1BvbGljeSk7XG5cbiAgICAvLyBPdXRwdXRzXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ0NvbGxlY3Rpb25Bcm4nLCB7XG4gICAgICB2YWx1ZTogdGhpcy5jb2xsZWN0aW9uLmF0dHJBcm4sXG4gICAgICBleHBvcnROYW1lOiAnT3BlblNlYXJjaENvbGxlY3Rpb25Bcm4nXG4gICAgfSk7XG5cbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCAnQnVja2V0QXJuJywge1xuICAgICAgdmFsdWU6IHRoaXMuczNCdWNrZXQuYXR0ckFybixcbiAgICAgIGV4cG9ydE5hbWU6ICdPcGVuU2VhcmNoQnVja2V0QXJuJ1xuICAgIH0pO1xuXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ0JlZHJvY2tSb2xlQXJuJywge1xuICAgICAgdmFsdWU6IHRoaXMuYmVkcm9ja1JvbGUuYXR0ckFybixcbiAgICAgIGV4cG9ydE5hbWU6ICdCZWRyb2NrUm9sZUFybidcbiAgICB9KTtcblxuICAgIG5ldyBjZGsuQ2ZuT3V0cHV0KHRoaXMsICdCdWNrZXROYW1lJywge1xuICAgICAgdmFsdWU6IHRoaXMuczNCdWNrZXQucmVmLFxuICAgICAgZXhwb3J0TmFtZTogJ0J1Y2tldE5hbWUnXG4gICAgfSk7XG5cblxuICB9XG59XG4iXX0=