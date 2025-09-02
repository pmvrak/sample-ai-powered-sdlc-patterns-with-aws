import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as events from 'aws-cdk-lib/aws-events';
import * as events_targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as sns from 'aws-cdk-lib/aws-sns';
import { Construct } from 'constructs';
import { FailureAnalysisProject } from './failure-analysis-project';

interface NotificationProcessorProps {
  failureAnalysisProject: FailureAnalysisProject;
  notificationTopic: sns.Topic;
}

export class NotificationProcessor extends Construct {
  constructor(scope: Construct, id: string, props: NotificationProcessorProps) {
    super(scope, id);

    // Create Lambda function for processing notifications
    const processorFunction = new lambda.Function(this, 'Function', {
      runtime: lambda.Runtime.NODEJS_18_X,
      handler: 'index.handler',
      code: lambda.Code.fromInline(this.getProcessorCode()),
      environment: {
        TOPIC_ARN: props.notificationTopic.topicArn
      },
      timeout: cdk.Duration.minutes(5)
    });

    // Add permissions
    processorFunction.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'codebuild:BatchGetBuilds',
        's3:GetObject',
        'sns:Publish'
      ],
      resources: ['*']
    }));

    // Create EventBridge rule for analysis completion
    new events.Rule(this, 'AnalysisCompletionRule', {
      eventPattern: {
        source: ['aws.codebuild'],
        detailType: ['CodeBuild Build State Change'],
        detail: {
          'project-name': [props.failureAnalysisProject.project.projectName],
          'build-status': ['SUCCEEDED', 'FAILED']
        }
      },
      targets: [new events_targets.LambdaFunction(processorFunction)]
    });
  }

  private getProcessorCode(): string {
    return `
      const AWS = require('aws-sdk');
      const codebuild = new AWS.CodeBuild();
      const sns = new AWS.SNS();

      exports.handler = async (event) => {
        try {
                // Get the build ID
                const buildId = event.detail['build-id'];
                
                // Get build logs and artifacts
                const buildInfo = await codebuild.batchGetBuilds({
                  ids: [buildId]
                }).promise();

                // Get the S3 artifact location
                const artifactLocation = buildInfo.builds[0].artifacts.location;
                
                // Get the failure analysis from S3
                const s3 = new AWS.S3();
                const analysisContent = await s3.getObject({
                  Bucket: artifactLocation.split(':::')[1].split('/')[0],
                  Key: 'failure_analysis.md'
                }).promise();

                const analysis = analysisContent.Body.toString('utf-8');

                // Create detailed message
                const message = \`
    Pipeline Failure Analysis Report
    ==============================

    Pipeline: \${event.detail['project-name']}
    Build ID: \${buildId}
    Status: \${event.detail['build-status']}
    Time: \${new Date().toISOString()}

    Analysis Results:
    ---------------
    \${analysis}

    Build Logs:
    ----------
    \${buildInfo.builds[0].logs.deepLink}

    \`;

                // Send SNS notification with analysis
                await sns.publish({
                  TopicArn: process.env.TOPIC_ARN,
                  Subject: 'Pipeline Failure Analysis Complete',
                  Message: message
                }).promise();

              } catch (error) {
                console.error('Error processing notification:', error);
                // Send error notification
                await sns.publish({
                  TopicArn: process.env.TOPIC_ARN,
                  Subject: 'Pipeline Failure Analysis Error',
                  Message: \`Error processing failure analysis: \${error.message}
    Build ID: \${event.detail['build-id']}
    Please check CodeBuild logs for details.\`
                }).promise();
              }
            };
      };
    `;
  }
}
