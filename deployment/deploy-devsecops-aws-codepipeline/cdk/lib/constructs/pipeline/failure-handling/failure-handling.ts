import * as cdk from 'aws-cdk-lib';
import * as events from 'aws-cdk-lib/aws-events';
import * as events_targets from 'aws-cdk-lib/aws-events-targets';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as sns_subscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import { Construct } from 'constructs';
import { PipelineConfig } from '../../../configs/pipeline-config';
import { FailureAnalysisProject } from './failure-analysis-project';
import { NotificationProcessor } from './notification-processor';

export interface FailureHandlingProps {
  pipeline: codepipeline.Pipeline;
}

export class FailureHandling extends Construct {
  public readonly pipelineFailureRule: events.Rule;
  public readonly debugLogGroup: logs.LogGroup;
  public readonly failureNotificationTopic: sns.Topic;
  public readonly failureHandlerFunction: lambda.Function;

  constructor(scope: Construct, id: string, props: FailureHandlingProps) {
    super(scope, id);

    // Create SNS topic for notifications
    this.failureNotificationTopic = new sns.Topic(this, 'FailureNotificationTopic', {
      displayName: 'Pipeline Analysis Notifications'
    });

    // Add email subscription
    this.failureNotificationTopic.addSubscription(
      new sns_subscriptions.EmailSubscription(PipelineConfig.notification.email)
    );

    // Create CloudWatch Log Group
    const uniqueId = cdk.Names.uniqueId(this);
    this.debugLogGroup = new logs.LogGroup(this, 'FailureDebugLogGroup', {
      logGroupName: `/aws/events/pipeline-failure-debug-${uniqueId}`,
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Create failure analysis project
    const failureAnalysisProject = new FailureAnalysisProject(this, 'FailureAnalysis', {
      notificationTopic: this.failureNotificationTopic
    });

    // Create failure handler Lambda
    this.failureHandlerFunction = this.createFailureHandler();

    // Create EventBridge rule for pipeline failures
    this.pipelineFailureRule = new events.Rule(this, 'PipelineFailureRule', {
      eventPattern: {
        source: ['aws.codepipeline'],
        detailType: ['CodePipeline Stage Execution State Change'],
        detail: {
          pipeline: [props.pipeline.pipelineName],
          state: ['FAILED']
        }
      },
      enabled: true
    });

    // Add Lambda as target for the rule
    this.pipelineFailureRule.addTarget(new events_targets.LambdaFunction(this.failureHandlerFunction));

    // Create notification processor for analysis completion
    new NotificationProcessor(this, 'NotificationProcessor', {
      failureAnalysisProject: failureAnalysisProject,
      notificationTopic: this.failureNotificationTopic
    });

    // Add necessary permissions
    this.addPermissions();
  }

  // private createFailureHandler(): lambda.Function {
  //   return new lambda.Function(this, 'FailureHandlerFunction', {
  //     runtime: lambda.Runtime.NODEJS_18_X,
  //     handler: 'index.handler',
  //     code: lambda.Code.fromInline(`
  //       const { SNSClient, PublishCommand } = require('@aws-sdk/client-sns');
  //       const { CodePipelineClient, GetPipelineExecutionCommand, ListActionExecutionsCommand } = require('@aws-sdk/client-codepipeline');
  //       const { CodeBuildClient, BatchGetBuildsCommand } = require('@aws-sdk/client-codebuild');
  //       const { BedrockRuntimeClient, InvokeModelCommand } = require('@aws-sdk/client-bedrock-runtime');
        
  //       async function analyzeFailure(failureInfo) {
  //         const bedrock = new BedrockRuntimeClient({ region: process.env.AWS_REGION });
          
  //         console.log('Preparing Bedrock request with failureInfo:', JSON.stringify(failureInfo, null, 2));
          
  //         // Get CodeBuild logs for the failed action
  //         let buildLogs = 'No build logs available';
  //         if (failureInfo.buildId) {
  //           try {
  //             const codebuild = new CodeBuildClient({ region: process.env.AWS_REGION });
  //             const builds = await codebuild.send(new BatchGetBuildsCommand({
  //               ids: [failureInfo.buildId]
  //             }));
  //             if (builds.builds && builds.builds.length > 0) {
  //               const build = builds.builds[0];
  //               buildLogs = build.logs?.deepLink || 'No CodeBuild logs URL available';
  //               console.log('Retrieved CodeBuild logs URL:', buildLogs);
                
  //               // If deepLink is not available, construct the URL manually
  //               if (!buildLogs || buildLogs === 'No CodeBuild logs URL available') {
  //                 /* eslint-disable no-useless-escape */
  //                 buildLogs = \`https://\${process.env.AWS_REGION}.console.aws.amazon.com/codesuite/codebuild/\${process.env.AWS_ACCOUNT_ID}/projects/\${build.projectName}/build/\${build.id}/?region=\${process.env.AWS_REGION}\`;
  //                 console.log('Constructed CodeBuild logs URL:', buildLogs);
  //                 /* eslint-disable no-useless-escape */
  //               }
  //             }
  //           } catch (error) {
  //             console.error('Error fetching CodeBuild logs:', error);
  //             buildLogs = \`Error fetching CodeBuild logs: \${error.message}\`;
  //           }
  //         }
          
  //         /* eslint-disable no-useless-escape */
  //         const prompt = {
  //           anthropic_version: "bedrock-2023-05-31",
  //           max_tokens: 1000,
  //           messages: [{
  //             role: "user",
  //             content: \`Analyze this pipeline failure and provide specific recommendations:
  //               Pipeline:\${failureInfo.pipelineName}
  //               Stage: \${failureInfo.stageName}
  //               Action: \${failureInfo.action}
  //               State: \${failureInfo.state}
  //               Build ID: \${failureInfo.buildId}
  //               Error Details: \${failureInfo.errorDetails}
  //               Build Logs: \${buildLogs}
                
  //               Based on the error details and build logs:
  //               1. What specifically caused this \${failureInfo.action} action to fail?
  //               2. What are the exact steps to fix this failure?
  //               3. How can we prevent this specific type of failure in the future?
                
  //               Format the response in plain text with clear sections.\`
  //           }]
  //         };
  //         /* eslint-disable no-useless-escape */
          
  //         console.log('Sending request to Bedrock:', JSON.stringify(prompt, null, 2));
          
  //         try {
  //           const response = await bedrock.send(new InvokeModelCommand({
  //             modelId: 'anthropic.claude-3-haiku-20240307-v1:0',
  //             contentType: 'application/json',
  //             accept: 'application/json',
  //             body: JSON.stringify(prompt)
  //           }));
            
  //           console.log('Raw Bedrock response:', JSON.stringify(response, null, 2));
            
  //           const responseText = new TextDecoder().decode(response.body);
  //           console.log('Decoded response:', responseText);
            
  //           const analysis = JSON.parse(responseText);
  //           console.log('Parsed analysis:', JSON.stringify(analysis, null, 2));
            
  //           if (analysis?.content?.[0]?.text) {
  //             return {
  //               analysisText: analysis.content[0].text,
  //               buildLogs: buildLogs
  //             };
  //           } else {
  //             console.log('Unexpected response structure:', JSON.stringify(analysis, null, 2));
  //             return {
  //               analysisText: 'Unable to generate analysis due to unexpected response format.',
  //               buildLogs: buildLogs
  //             };
  //           }
  //         } catch (error) {
  //           console.error('Bedrock analysis error:', error);
  //           return {
  //             analysisText: \`Error performing failure analysis: \${error.message}\`,
  //             buildLogs: buildLogs
  //           };
  //         }
  //       }
        
  //       exports.handler = async (event) => {
  //         console.log('Event received:', JSON.stringify(event, null, 2));
          
  //         try {
  //           const detail = event.detail;
  //           console.log('Initial event detail:', {
  //             pipeline: detail.pipeline,
  //             stage: detail.stage,
  //             action: detail.action, // This might be undefined
  //             executionId: detail['execution-id'],
  //             state: detail.state
  //           });
            
  //           const codepipeline = new CodePipelineClient({ region: process.env.AWS_REGION });
  //           const sns = new SNSClient({ region: process.env.AWS_REGION });
            
  //           // Get action execution details to get the buildId
  //           let buildId = '';
  //           let errorDetails = '';
  //           let actionName = detail.action; // Store original action name
            
  //           try {
  //             const actionExecutionsResult = await codepipeline.send(new ListActionExecutionsCommand({
  //               pipelineName: detail.pipeline,
  //               filter: {
  //                 pipelineExecutionId: detail['execution-id']
  //               }
  //             }));
              
  //             console.log('Action executions result:', JSON.stringify(actionExecutionsResult, null, 2));
              
  //             // Find failed actions in the specified stage
  //             const failedActions = actionExecutionsResult.actionExecutionDetails?.filter(action => 
  //               action.stageName === detail.stage && action.status === 'Failed'
  //             ) || [];
              
  //             console.log('Found failed actions:', JSON.stringify(failedActions, null, 2));
              
  //             // If we have a specific action name, use that, otherwise take the first failed action
  //             const failedAction = detail.action 
  //               ? failedActions.find(action => action.actionName === detail.action)
  //               : failedActions[0];
              
  //             if (failedAction) {
  //               buildId = failedAction.output?.executionResult?.externalExecutionId || '';
  //               errorDetails = failedAction.output?.executionResult?.externalExecutionSummary || '';
  //               actionName = failedAction.actionName; // Update action name from the failed action
                
  //               console.log('Selected failed action details:', {
  //                 actionName: failedAction.actionName,
  //                 buildId,
  //                 errorDetails
  //               });
  //             } else {
  //               console.log('No matching failed action found');
                
  //               // Log all failed actions for debugging
  //               console.log('All failed actions in stage:', 
  //                 failedActions.map(action => ({
  //                   name: action.actionName,
  //                   status: action.status,
  //                   stage: action.stageName
  //                 }))
  //               );
  //             }
  //           } catch (error) {
  //             console.error('Error getting action execution details:', error);
  //           }
            
  //           const failureInfo = {
  //             pipelineName: detail.pipeline,
  //             stageName: detail.stage,
  //             state: detail.state,
  //             executionId: detail['execution-id'],
  //             action: actionName || 'Unknown Action', // Use the discovered action name or fallback
  //             buildId: buildId,
  //             errorDetails: errorDetails || 'No error details available'
  //           };
            
  //           console.log('Final failure info:', JSON.stringify(failureInfo, null, 2));
            
  //           // Get AI analysis with build logs
  //           const { analysisText, buildLogs } = await analyzeFailure(failureInfo);
            
  //           // Send notification
  //           /* eslint-disable no-useless-escape */
  //           await sns.send(new PublishCommand({
  //             TopicArn: process.env.SNS_TOPIC_ARN,
  //             Subject: \`Pipeline Stage Failed - \${failureInfo.pipelineName} (\${failureInfo.stageName} - \${failureInfo.action})\`,
  //             Message: \`
  //   Pipeline Failure Report
  //   ======================
    
  //   Failure Details
  //   --------------
  //   Pipeline: \${failureInfo.pipelineName}
  //   Stage: \${failureInfo.stageName}
  //   State: \${failureInfo.state}
  //   Execution ID: \${failureInfo.executionId}
  //   Action: \${failureInfo.action}
  //   Build ID: \${buildId || 'N/A'}
  //   Error Details: \${failureInfo.errorDetails}
    
  //   AI Analysis
  //   ----------
  //   \${analysisText}
    
  //   Build Logs
  //   ----------
  //   \${buildLogs}
    
  //   Next Steps
  //   ----------
  //   1. Review the analysis above
  //   2. Check the AWS CodePipeline console for more details
  //   3. Apply recommended fixes
  //   4. Re-run the pipeline
    
  //   Pipeline Console Link: https://\${process.env.AWS_REGION}.console.aws.amazon.com/codesuite/codepipeline/pipelines/\${failureInfo.pipelineName}/view
  //             \`
  //           }));
  //           /* eslint-disable no-useless-escape */
            
  //         } catch (error) {
  //           console.error('Error processing event:', error);
  //           throw error;
  //         }
  //       }
  //     `),
  //     environment: {
  //       SNS_TOPIC_ARN: this.failureNotificationTopic.topicArn,
  //       AWS_ACCOUNT_ID: cdk.Stack.of(this).account
  //     },
  //     timeout: cdk.Duration.minutes(5),
  //     memorySize: 256,
  //     logRetention: logs.RetentionDays.ONE_WEEK
  //   });
  // }

  private createFailureHandler(): lambda.Function {
  return new lambda.Function(this, 'FailureHandlerFunction', {
    runtime: lambda.Runtime.NODEJS_18_X,
    handler: 'index.handler',
    code: lambda.Code.fromInline(`
      const { SNSClient, PublishCommand } = require('@aws-sdk/client-sns');
      const { CodePipelineClient, GetPipelineExecutionCommand, ListActionExecutionsCommand } = require('@aws-sdk/client-codepipeline');
      const { CodeBuildClient, BatchGetBuildsCommand } = require('@aws-sdk/client-codebuild');
      const { CloudWatchLogsClient, GetLogEventsCommand } = require('@aws-sdk/client-cloudwatch-logs');
      const { BedrockRuntimeClient, InvokeModelCommand } = require('@aws-sdk/client-bedrock-runtime');

      async function getCodeBuildLogs(buildId) {
        const codebuild = new CodeBuildClient({ region: process.env.AWS_REGION });
        const cloudWatchLogs = new CloudWatchLogsClient({ region: process.env.AWS_REGION });

        try {
          const builds = await codebuild.send(new BatchGetBuildsCommand({ ids: [buildId] }));
          if (builds.builds && builds.builds.length > 0) {
            const build = builds.builds[0];
            const logGroupName = build.logs?.groupName;
            const logStreamName = build.logs?.streamName;

            if (logGroupName && logStreamName) {
              const logEvents = await cloudWatchLogs.send(new GetLogEventsCommand({
                logGroupName,
                logStreamName,
                limit: 100 // Adjust this value as needed
              }));

              return logEvents.events.map(event => event.message).join('\\n');
            }
          }
        } catch (error) {
          console.error('Error fetching CodeBuild logs:', error);
        }

        return 'No logs available';
      }

      async function analyzeFailure(failureInfo) {
        const bedrock = new BedrockRuntimeClient({ region: process.env.AWS_REGION });
        
        console.log('Preparing Bedrock request with failureInfo:', JSON.stringify(failureInfo, null, 2));
        
        // Get CodeBuild logs for the failed action
        let buildLogs = 'No build logs available';
        if (failureInfo.buildId) {
          buildLogs = await getCodeBuildLogs(failureInfo.buildId);
          console.log('Retrieved CodeBuild logs:', buildLogs);
        }
        
        const prompt = {
          anthropic_version: "bedrock-2023-05-31",
          max_tokens: 1000,
          messages: [{
            role: "user",
            content: \`Analyze this pipeline failure and provide specific recommendations:
              Pipeline:\${failureInfo.pipelineName}
              Stage: \${failureInfo.stageName}
              Action: \${failureInfo.action}
              State: \${failureInfo.state}
              Build ID: \${failureInfo.buildId}
              Error Details: \${failureInfo.errorDetails}
              Build Logs: \${buildLogs}
              
              Based on the error details and build logs:
              1. What specifically caused this \${failureInfo.action} action to fail?
              2. What are the exact steps to fix this failure?
              3. How can we prevent this specific type of failure in the future?
              
              Format the response in plain text with clear sections.\`
          }]
        };
        /* eslint-disable no-useless-escape */
        
        console.log('Sending request to Bedrock:', JSON.stringify(prompt, null, 2));
        
        try {
          const response = await bedrock.send(new InvokeModelCommand({
            modelId: 'anthropic.claude-3-haiku-20240307-v1:0',
            contentType: 'application/json',
            accept: 'application/json',
            body: JSON.stringify(prompt)
          }));
          
          const responseText = new TextDecoder().decode(response.body);
          const analysis = JSON.parse(responseText);
          
          if (analysis?.content?.[0]?.text) {
            return {
              analysisText: analysis.content[0].text,
              buildLogs: buildLogs
            };
          } else {
            console.log('Unexpected response structure:', JSON.stringify(analysis, null, 2));
            return {
              analysisText: 'Unable to generate analysis due to unexpected response format.',
              buildLogs: buildLogs
            };
          }
        } catch (error) {
          console.error('Bedrock analysis error:', error);
          return {
            analysisText: \`Error performing failure analysis: \${error.message}\`,
            buildLogs: buildLogs
          };
        }
      }

      exports.handler = async (event) => {
          console.log('Event received:', JSON.stringify(event, null, 2));
          
          try {
            const detail = event.detail;
            console.log('Initial event detail:', {
              pipeline: detail.pipeline,
              stage: detail.stage,
              action: detail.action, // This might be undefined
              executionId: detail['execution-id'],
              state: detail.state
            });
            
            const codepipeline = new CodePipelineClient({ region: process.env.AWS_REGION });
            const sns = new SNSClient({ region: process.env.AWS_REGION });
            
            // Get action execution details to get the buildId
            let buildId = '';
            let errorDetails = '';
            let actionName = detail.action; // Store original action name
            
            try {
              const actionExecutionsResult = await codepipeline.send(new ListActionExecutionsCommand({
                pipelineName: detail.pipeline,
                filter: {
                  pipelineExecutionId: detail['execution-id']
                }
              }));
              
              console.log('Action executions result:', JSON.stringify(actionExecutionsResult, null, 2));
              
              // Find failed actions in the specified stage
              const failedActions = actionExecutionsResult.actionExecutionDetails?.filter(action => 
                action.stageName === detail.stage && action.status === 'Failed'
              ) || [];
              
              console.log('Found failed actions:', JSON.stringify(failedActions, null, 2));
              
              // If we have a specific action name, use that, otherwise take the first failed action
              const failedAction = detail.action 
                ? failedActions.find(action => action.actionName === detail.action)
                : failedActions[0];
              
              if (failedAction) {
                buildId = failedAction.output?.executionResult?.externalExecutionId || '';
                errorDetails = failedAction.output?.executionResult?.externalExecutionSummary || '';
                actionName = failedAction.actionName; // Update action name from the failed action
                
                console.log('Selected failed action details:', {
                  actionName: failedAction.actionName,
                  buildId,
                  errorDetails
                });
              } else {
                console.log('No matching failed action found');
                
                // Log all failed actions for debugging
                console.log('All failed actions in stage:', 
                  failedActions.map(action => ({
                    name: action.actionName,
                    status: action.status,
                    stage: action.stageName
                  }))
                );
              }
            } catch (error) {
              console.error('Error getting action execution details:', error);
            }
            
            const failureInfo = {
              pipelineName: detail.pipeline,
              stageName: detail.stage,
              state: detail.state,
              executionId: detail['execution-id'],
              action: actionName || 'Unknown Action', // Use the discovered action name or fallback
              buildId: buildId,
              errorDetails: errorDetails || 'No error details available'
            };
            
            console.log('Final failure info:', JSON.stringify(failureInfo, null, 2));
            
            // Get AI analysis with build logs
            const { analysisText, buildLogs } = await analyzeFailure(failureInfo);
            
            // Send notification
            /* eslint-disable no-useless-escape */
            await sns.send(new PublishCommand({
              TopicArn: process.env.SNS_TOPIC_ARN,
              Subject: \`Pipeline Stage Failed - \${failureInfo.pipelineName} (\${failureInfo.stageName} - \${failureInfo.action})\`,
              Message: \`
    Pipeline Failure Report
    ======================
    
    Failure Details
    --------------
    Pipeline: \${failureInfo.pipelineName}
    Stage: \${failureInfo.stageName}
    State: \${failureInfo.state}
    Execution ID: \${failureInfo.executionId}
    Action: \${failureInfo.action}
    Build ID: \${buildId || 'N/A'}
    Error Details: \${failureInfo.errorDetails}
    
    AI Analysis
    ----------
    \${analysisText}
    
    Build Logs
    ----------
    CodeBuild Console: https://\${process.env.AWS_REGION}.console.aws.amazon.com/codesuite/codebuild/\${process.env.AWS_ACCOUNT_ID}/projects/\${buildId?.split(':')[0]}/build/\${buildId}/?region=\${process.env.AWS_REGION}
    
    Next Steps
    ----------
    1. Review the analysis above
    2. Check the AWS CodePipeline console for more details
    3. Apply recommended fixes
    4. Re-run the pipeline
    
    Pipeline Console Link: https://\${process.env.AWS_REGION}.console.aws.amazon.com/codesuite/codepipeline/pipelines/\${failureInfo.pipelineName}/view
              \`
            }));
            /* eslint-disable no-useless-escape */
            
          } catch (error) {
            console.error('Error processing event:', error);
            throw error;
          }
        }
    `),
    environment: {
      SNS_TOPIC_ARN: this.failureNotificationTopic.topicArn,
      AWS_ACCOUNT_ID: cdk.Stack.of(this).account
    },
    timeout: cdk.Duration.minutes(5),
    memorySize: 256,
    logRetention: logs.RetentionDays.ONE_WEEK
  });
}


  private addPermissions() {
    // Add permissions to Lambda
    this.failureHandlerFunction.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'sns:Publish',
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents',
        'codepipeline:GetPipelineExecution',
        'codepipeline:ListActionExecutions',
        'codebuild:BatchGetBuilds',
        'bedrock:InvokeModel',
        'bedrock-runtime:InvokeModel'
      ],
      resources: ['*']
    }));

    // Add permissions for EventBridge to write to CloudWatch Logs
    this.debugLogGroup.addToResourcePolicy(new iam.PolicyStatement({
      actions: [
        'logs:CreateLogStream',
        'logs:PutLogEvents'
      ],
      principals: [new iam.ServicePrincipal('events.amazonaws.com')],
      resources: [this.debugLogGroup.logGroupArn]
    }));

    // Add permissions for SNS
    this.failureNotificationTopic.addToResourcePolicy(new iam.PolicyStatement({
      actions: ['sns:Publish'],
      principals: [new iam.ServicePrincipal('events.amazonaws.com')],
      resources: [this.failureNotificationTopic.topicArn]
    }));

    // Add permissions to read CloudWatch Logs
    this.failureHandlerFunction.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'logs:GetLogEvents',
        'logs:FilterLogEvents',
      ],
      resources: ['arn:aws:logs:*:*:log-group:/aws/codebuild/*:log-stream:*'],
    }));

  }
}
