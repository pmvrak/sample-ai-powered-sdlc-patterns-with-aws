"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.StorageStack = void 0;
const cdk = require("aws-cdk-lib");
const s3 = require("aws-cdk-lib/aws-s3");
const iam = require("aws-cdk-lib/aws-iam");
class StorageStack extends cdk.Stack {
    constructor(scope, id, props) {
        super(scope, id, props);
        // S3 bucket for knowledge base data storage with enhanced security
        this.knowledgeBaseBucket = new s3.Bucket(this, 'KnowledgeBaseBucket', {
            bucketName: `openapi-knowledge-base-${this.account}-${this.region}`,
            versioned: true,
            encryption: s3.BucketEncryption.S3_MANAGED,
            blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
            removalPolicy: cdk.RemovalPolicy.RETAIN,
            enforceSSL: true,
            lifecycleRules: [
                {
                    id: 'DeleteIncompleteMultipartUploads',
                    abortIncompleteMultipartUploadAfter: cdk.Duration.days(7),
                },
                {
                    id: 'TransitionOldVersions',
                    noncurrentVersionTransitions: [{
                            storageClass: s3.StorageClass.INFREQUENT_ACCESS,
                            transitionAfter: cdk.Duration.days(30)
                        }]
                }
            ]
        });
        // S3 bucket for domain analyzer output with enhanced security
        this.domainAnalyzerBucket = new s3.Bucket(this, 'DomainAnalyzerBucket', {
            bucketName: `openapi-domain-analyzer-${this.account}-${this.region}`,
            versioned: false,
            encryption: s3.BucketEncryption.S3_MANAGED,
            blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
            enforceSSL: true,
            lifecycleRules: [
                {
                    id: 'DeleteOldAnalyzerResults',
                    expiration: cdk.Duration.days(30),
                },
                {
                    id: 'DeleteIncompleteMultipartUploads',
                    abortIncompleteMultipartUploadAfter: cdk.Duration.days(1),
                }
            ]
        });
        // Grant Lambda service access to domain analyzer bucket
        this.domainAnalyzerBucket.addToResourcePolicy(new iam.PolicyStatement({
            sid: 'DomainAnalyzerLambdaAccess',
            effect: iam.Effect.ALLOW,
            principals: [new iam.ServicePrincipal('lambda.amazonaws.com')],
            actions: [
                's3:GetObject',
                's3:PutObject',
                's3:DeleteObject',
                's3:ListBucket'
            ],
            resources: [
                this.domainAnalyzerBucket.bucketArn,
                `${this.domainAnalyzerBucket.bucketArn}/*`
            ],
            conditions: {
                StringEquals: {
                    'aws:SourceAccount': this.account
                }
            }
        }));
        // Grant Bedrock service access to knowledge base bucket
        this.knowledgeBaseBucket.addToResourcePolicy(new iam.PolicyStatement({
            sid: 'BedrockKnowledgeBaseAccess',
            effect: iam.Effect.ALLOW,
            principals: [new iam.ServicePrincipal('bedrock.amazonaws.com')],
            actions: [
                's3:GetObject',
                's3:ListBucket'
            ],
            resources: [
                this.knowledgeBaseBucket.bucketArn,
                `${this.knowledgeBaseBucket.bucketArn}/*`
            ],
            conditions: {
                StringEquals: {
                    'aws:SourceAccount': this.account
                }
            }
        }));
        // Export bucket names as stack outputs
        new cdk.CfnOutput(this, 'KnowledgeBaseBucketName', {
            value: this.knowledgeBaseBucket.bucketName,
            description: 'S3 bucket name for knowledge base data storage',
            exportName: `${this.stackName}-KnowledgeBaseBucketName`
        });
        new cdk.CfnOutput(this, 'DomainAnalyzerBucketName', {
            value: this.domainAnalyzerBucket.bucketName,
            description: 'S3 bucket name for domain analyzer output',
            exportName: `${this.stackName}-DomainAnalyzerBucketName`
        });
    }
}
exports.StorageStack = StorageStack;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoic3RvcmFnZS1zdGFjay5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbInN0b3JhZ2Utc3RhY2sudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6Ijs7O0FBQUEsbUNBQW1DO0FBQ25DLHlDQUF5QztBQUN6QywyQ0FBMkM7QUFHM0MsTUFBYSxZQUFhLFNBQVEsR0FBRyxDQUFDLEtBQUs7SUFJekMsWUFBWSxLQUFnQixFQUFFLEVBQVUsRUFBRSxLQUFzQjtRQUM5RCxLQUFLLENBQUMsS0FBSyxFQUFFLEVBQUUsRUFBRSxLQUFLLENBQUMsQ0FBQztRQUV4QixtRUFBbUU7UUFDbkUsSUFBSSxDQUFDLG1CQUFtQixHQUFHLElBQUksRUFBRSxDQUFDLE1BQU0sQ0FBQyxJQUFJLEVBQUUscUJBQXFCLEVBQUU7WUFDcEUsVUFBVSxFQUFFLDBCQUEwQixJQUFJLENBQUMsT0FBTyxJQUFJLElBQUksQ0FBQyxNQUFNLEVBQUU7WUFDbkUsU0FBUyxFQUFFLElBQUk7WUFDZixVQUFVLEVBQUUsRUFBRSxDQUFDLGdCQUFnQixDQUFDLFVBQVU7WUFDMUMsaUJBQWlCLEVBQUUsRUFBRSxDQUFDLGlCQUFpQixDQUFDLFNBQVM7WUFDakQsYUFBYSxFQUFFLEdBQUcsQ0FBQyxhQUFhLENBQUMsTUFBTTtZQUN2QyxVQUFVLEVBQUUsSUFBSTtZQUNoQixjQUFjLEVBQUU7Z0JBQ2Q7b0JBQ0UsRUFBRSxFQUFFLGtDQUFrQztvQkFDdEMsbUNBQW1DLEVBQUUsR0FBRyxDQUFDLFFBQVEsQ0FBQyxJQUFJLENBQUMsQ0FBQyxDQUFDO2lCQUMxRDtnQkFDRDtvQkFDRSxFQUFFLEVBQUUsdUJBQXVCO29CQUMzQiw0QkFBNEIsRUFBRSxDQUFDOzRCQUM3QixZQUFZLEVBQUUsRUFBRSxDQUFDLFlBQVksQ0FBQyxpQkFBaUI7NEJBQy9DLGVBQWUsRUFBRSxHQUFHLENBQUMsUUFBUSxDQUFDLElBQUksQ0FBQyxFQUFFLENBQUM7eUJBQ3ZDLENBQUM7aUJBQ0g7YUFDRjtTQUNGLENBQUMsQ0FBQztR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QVMsMkJBQTJCO1NBQ3pELENBQUMsQ0FBQztJQUNMLENBQUM7Q0FDRjtBQTdHRCxvQ0E2R0MiLCJzb3VyY2VzQ29udGVudCI6WyJpbXBvcnQgKiBhcyBjZGsgZnJvbSAnYXdzLWNkay1saWInO1xuaW1wb3J0ICogYXMgczMgZnJvbSAnYXdzLWNkay1saWIvYXdzLXMzJztcbmltcG9ydCAqIGFzIGlhbSBmcm9tICdhd3MtY2RrLWxpYi9hd3MtaWFtJztcbmltcG9ydCB7IENvbnN0cnVjdCB9IGZyb20gJ2NvbnN0cnVjdHMnO1xuXG5leHBvcnQgY2xhc3MgU3RvcmFnZVN0YWNrIGV4dGVuZHMgY2RrLlN0YWNrIHtcbiAgcHVibGljIHJlYWRvbmx5IGtub3dsZWRnZUJhc2VCdWNrZXQ6IHMzLkJ1Y2tldDtcbiAgcHVibGljIHJlYWRvbmx5IGRvbWFpbkFuYWx5emVyQnVja2V0OiBzMy5CdWNrZXQ7XG5cbiAgY29uc3RydWN0b3Ioc2NvcGU6IENvbnN0cnVjdCwgaWQ6IHN0cmluZywgcHJvcHM/OiBjZGsuU3RhY2tQcm9wcykge1xuICAgIHN1cGVyKHNjb3BlLCBpZCwgcHJvcHMpO1xuXG4gICAgLy8gUzMgYnVja2V0IGZvciBrbm93bGVkZ2UgYmFzZSBkYXRhIHN0b3JhZ2Ugd2l0aCBlbmhhbmNlZCBzZWN1cml0eVxuICAgIHRoaXMua25vd2xlZGdlQmFzZUJ1Y2tldCA9IG5ldyBzMy5CdWNrZXQodGhpcywgJ0tub3dsZWRnZUJhc2VCdWNrZXQnLCB7XG4gICAgICBidWNrZXROYW1lOiBgb3BlbmFwaS1rbm93bGVkZ2UtYmFzZS0ke3RoaXMuYWNjb3VudH0tJHt0aGlzLnJlZ2lvbn1gLFxuICAgICAgdmVyc2lvbmVkOiB0cnVlLFxuICAgICAgZW5jcnlwdGlvbjogczMuQnVja2V0RW5jcnlwdGlvbi5TM19NQU5BR0VELFxuICAgICAgYmxvY2tQdWJsaWNBY2Nlc3M6IHMzLkJsb2NrUHVibGljQWNjZXNzLkJMT0NLX0FMTCxcbiAgICAgIHJlbW92YWxQb2xpY3k6IGNkay5SZW1vdmFsUG9saWN5LlJFVEFJTixcbiAgICAgIGVuZm9yY2VTU0w6IHRydWUsXG4gICAgICBsaWZlY3ljbGVSdWxlczogW1xuICAgICAgICB7XG4gICAgICAgICAgaWQ6ICdEZWxldGVJbmNvbXBsZXRlTXVsdGlwYXJ0VXBsb2FkcycsXG4gICAgICAgICAgYWJvcnRJbmNvbXBsZXRlTXVsdGlwYXJ0VXBsb2FkQWZ0ZXI6IGNkay5EdXJhdGlvbi5kYXlzKDcpLFxuICAgICAgICB9LFxuICAgICAgICB7XG4gICAgICAgICAgaWQ6ICdUcmFuc2l0aW9uT2xkVmVyc2lvbnMnLFxuICAgICAgICAgIG5vbmN1cnJlbnRWZXJzaW9uVHJhbnNpdGlvbnM6IFt7XG4gICAgICAgICAgICBzdG9yYWdlQ2xhc3M6IHMzLlN0b3JhZ2VDbGFzcy5JTkZSRVFVRU5UX0FDQ0VTUyxcbiAgICAgICAgICAgIHRyYW5zaXRpb25BZnRlcjogY2RrLkR1cmF0aW9uLmRheXMoMzApXG4gICAgICAgICAgfV1cbiAgICAgICAgfVxuICAgICAgXVxuICAgIH0pO1xuXG4gICAgLy8gUzMgYnVja2V0IGZvciBkb21haW4gYW5hbHl6ZXIgb3V0cHV0IHdpdGggZW5oYW5jZWQgc2VjdXJpdHlcbiAgICB0aGlzLmRvbWFpbkFuYWx5emVyQnVja2V0ID0gbmV3IHMzLkJ1Y2tldCh0aGlzLCAnRG9tYWluQW5hbHl6ZXJCdWNrZXQnLCB7XG4gICAgICBidWNrZXROYW1lOiBgb3BlbmFwaS1kb21haW4tYW5hbHl6ZXItJHt0aGlzLmFjY291bnR9LSR7dGhpcy5yZWdpb259YCxcbiAgICAgIHZlcnNpb25lZDogZmFsc2UsXG4gICAgICBlbmNyeXB0aW9uOiBzMy5CdWNrZXRFbmNyeXB0aW9uLlMzX01BTkFHRUQsXG4gICAgICBibG9ja1B1YmxpY0FjY2VzczogczMuQmxvY2tQdWJsaWNBY2Nlc3MuQkxPQ0tfQUxMLFxuICAgICAgcmVtb3ZhbFBvbGljeTogY2RrLlJlbW92YWxQb2xpY3kuREVTVFJPWSxcbiAgICAgIGVuZm9yY2VTU0w6IHRydWUsXG4gICAgICBsaWZlY3ljbGVSdWxlczogW1xuICAgICAgICB7XG4gICAgICAgICAgaWQ6ICdEZWxldGVPbGRBbmFseXplclJlc3VsdHMnLFxuICAgICAgICAgIGV4cGlyYXRpb246IGNkay5EdXJhdGlvbi5kYXlzKDMwKSxcbiAgICAgICAgfSxcbiAgICAgICAge1xuICAgICAgICAgIGlkOiAnRGVsZXRlSW5jb21wbGV0ZU11bHRpcGFydFVwbG9hZHMnLFxuICAgICAgICAgIGFib3J0SW5jb21wbGV0ZU11bHRpcGFydFVwbG9hZEFmdGVyOiBjZGsuRHVyYXRpb24uZGF5cygxKSxcbiAgICAgICAgfVxuICAgICAgXVxuICAgIH0pO1xuXG4gICAgLy8gR3JhbnQgTGFtYmRhIHNlcnZpY2UgYWNjZXNzIHRvIGRvbWFpbiBhbmFseXplciBidWNrZXRcbiAgICB0aGlzLmRvbWFpbkFuYWx5emVyQnVja2V0LmFkZFRvUmVzb3VyY2VQb2xpY3koXG4gICAgICBuZXcgaWFtLlBvbGljeVN0YXRlbWVudCh7XG4gICAgICAgIHNpZDogJ0RvbWFpbkFuYWx5emVyTGFtYmRhQWNjZXNzJyxcbiAgICAgICAgZWZmZWN0OiBpYW0uRWZmZWN0LkFMTE9XLFxuICAgICAgICBwcmluY2lwYWxzOiBbbmV3IGlhbS5TZXJ2aWNlUHJpbmNpcGFsKCdsYW1iZGEuYW1hem9uYXdzLmNvbScpXSxcbiAgICAgICAgYWN0aW9uczogW1xuICAgICAgICAgICdzMzpHZXRPYmplY3QnLFxuICAgICAgICAgICdzMzpQdXRPYmplY3QnLFxuICAgICAgICAgICdzMzpEZWxldGVPYmplY3QnLFxuICAgICAgICAgICdzMzpMaXN0QnVja2V0J1xuICAgICAgICBdLFxuICAgICAgICByZXNvdXJjZXM6IFtcbiAgICAgICAgICB0aGlzLmRvbWFpbkFuYWx5emVyQnVja2V0LmJ1Y2tldEFybixcbiAgICAgICAgICBgJHt0aGlzLmRvbWFpbkFuYWx5emVyQnVja2V0LmJ1Y2tldEFybn0vKmBcbiAgICAgICAgXSxcbiAgICAgICAgY29uZGl0aW9uczoge1xuICAgICAgICAgIFN0cmluZ0VxdWFsczoge1xuICAgICAgICAgICAgJ2F3czpTb3VyY2VBY2NvdW50JzogdGhpcy5hY2NvdW50XG4gICAgICAgICAgfVxuICAgICAgICB9XG4gICAgICB9KVxuICAgICk7XG5cbiAgICAvLyBHcmFudCBCZWRyb2NrIHNlcnZpY2UgYWNjZXNzIHRvIGtub3dsZWRnZSBiYXNlIGJ1Y2tldFxuICAgIHRoaXMua25vd2xlZGdlQmFzZUJ1Y2tldC5hZGRUb1Jlc291cmNlUG9saWN5KFxuICAgICAgbmV3IGlhbS5Qb2xpY3lTdGF0ZW1lbnQoe1xuICAgICAgICBzaWQ6ICdCZWRyb2NrS25vd2xlZGdlQmFzZUFjY2VzcycsXG4gICAgICAgIGVmZmVjdDogaWFtLkVmZmVjdC5BTExPVyxcbiAgICAgICAgcHJpbmNpcGFsczogW25ldyBpYW0uU2VydmljZVByaW5jaXBhbCgnYmVkcm9jay5hbWF6b25hd3MuY29tJyldLFxuICAgICAgICBhY3Rpb25zOiBbXG4gICAgICAgICAgJ3MzOkdldE9iamVjdCcsXG4gICAgICAgICAgJ3MzOkxpc3RCdWNrZXQnXG4gICAgICAgIF0sXG4gICAgICAgIHJlc291cmNlczogW1xuICAgICAgICAgIHRoaXMua25vd2xlZGdlQmFzZUJ1Y2tldC5idWNrZXRBcm4sXG4gICAgICAgICAgYCR7dGhpcy5rbm93bGVkZ2VCYXNlQnVja2V0LmJ1Y2tldEFybn0vKmBcbiAgICAgICAgXSxcbiAgICAgICAgY29uZGl0aW9uczoge1xuICAgICAgICAgIFN0cmluZ0VxdWFsczoge1xuICAgICAgICAgICAgJ2F3czpTb3VyY2VBY2NvdW50JzogdGhpcy5hY2NvdW50XG4gICAgICAgICAgfVxuICAgICAgICB9XG4gICAgICB9KVxuICAgICk7XG5cbiAgICAvLyBFeHBvcnQgYnVja2V0IG5hbWVzIGFzIHN0YWNrIG91dHB1dHNcbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCAnS25vd2xlZGdlQmFzZUJ1Y2tldE5hbWUnLCB7XG4gICAgICB2YWx1ZTogdGhpcy5rbm93bGVkZ2VCYXNlQnVja2V0LmJ1Y2tldE5hbWUsXG4gICAgICBkZXNjcmlwdGlvbjogJ1MzIGJ1Y2tldCBuYW1lIGZvciBrbm93bGVkZ2UgYmFzZSBkYXRhIHN0b3JhZ2UnLFxuICAgICAgZXhwb3J0TmFtZTogYCR7dGhpcy5zdGFja05hbWV9LUtub3dsZWRnZUJhc2VCdWNrZXROYW1lYFxuICAgIH0pO1xuXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ0RvbWFpbkFuYWx5emVyQnVja2V0TmFtZScsIHtcbiAgICAgIHZhbHVlOiB0aGlzLmRvbWFpbkFuYWx5emVyQnVja2V0LmJ1Y2tldE5hbWUsXG4gICAgICBkZXNjcmlwdGlvbjogJ1MzIGJ1Y2tldCBuYW1lIGZvciBkb21haW4gYW5hbHl6ZXIgb3V0cHV0JyxcbiAgICAgIGV4cG9ydE5hbWU6IGAke3RoaXMuc3RhY2tOYW1lfS1Eb21haW5BbmFseXplckJ1Y2tldE5hbWVgXG4gICAgfSk7XG4gIH1cbn0iXX0=