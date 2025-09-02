import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { PipelineConstruct } from '../constructs/pipeline/pipeline-construct';
import { PipelineMonitoring } from '../constructs/pipeline/monitoring';
import { PipelineConfig } from '../configs/pipeline-config';

export class CdkPipelineStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create the main pipeline construct
    const pipelineConstruct = new PipelineConstruct(this, 'Pipeline');

    // Add monitoring
    new PipelineMonitoring(this, 'Monitoring', {
      pipeline: pipelineConstruct.pipeline
    });

    // Outputs
    // new cdk.CfnOutput(this, 'CodeCommitHTTPSCloneURL', {
    //   value: pipelineConstruct.repository.repositoryCloneUrlHttp,
    // });

    new cdk.CfnOutput(this, 'GitLabRepositoryName', {
      value: `${PipelineConfig.source.repositoryOwner}/${PipelineConfig.source.repositoryName}`,
      description: 'GitLab Repository Name'
    });

    new cdk.CfnOutput(this, 'EventRuleArn', {
      value: pipelineConstruct.failureHandling.pipelineFailureRule.ruleArn,
      description: 'EventBridge Rule ARN'
    });

    new cdk.CfnOutput(this, 'LogGroupName', {
      value: pipelineConstruct.failureHandling.debugLogGroup.logGroupName,
      description: 'Debug Log Group Name'
    });

    new cdk.CfnOutput(this, 'SnsTopicArn', {
      value: pipelineConstruct.failureHandling.failureNotificationTopic.topicArn,
      description: 'SNS Topic ARN'
    });

    new cdk.CfnOutput(this, 'LambdaFunctionName', {
      value: pipelineConstruct.failureHandling.failureHandlerFunction.functionName,
      description: 'Failure Handler Lambda Function Name'
    });
  }
}
