import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as sns from 'aws-cdk-lib/aws-sns';
import { Construct } from 'constructs';

export interface FailureAnalysisProjectProps {
  notificationTopic: sns.Topic;
}

export class FailureAnalysisProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string, props: FailureAnalysisProjectProps) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'FailureAnalysisProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
        privileged: true,
      },
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          install: {
            commands: [
              'npm install -g aws-cdk',
              'npm install @aws-sdk/client-bedrock-runtime',
              'aws --version',
            ],
          },
          build: {
            commands: [
              'echo "Pipeline failure detected"',
              'echo "Pipeline Name: $PIPELINE_NAME"',
              'echo "Failed Stage: $FAILED_STAGE"',
              'echo "Failed Action: $FAILED_ACTION"',
              'echo "Execution ID: $EXECUTION_ID"',
              
              // Get failure details
              'aws codepipeline get-pipeline-execution \
                --pipeline-name $PIPELINE_NAME \
                --pipeline-execution-id $EXECUTION_ID > pipeline_execution.json',
              
              // Run failure analysis
              'node ./cdk-pipeline/scripts/analyze-failure.js',
              
              'echo "Failure Analysis Report:"',
              'cat failure_analysis.md'
            ],
          },
        },
        artifacts: {
          files: [
            'failure_analysis.json',
            'failure_analysis.md',
            'pipeline_execution.json'
          ],
          'base-directory': '.',
          'name': 'failure-analysis'
        },
      }),
    });

    // Add permissions
    this.project.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'bedrock:InvokeModel',
        'bedrock-runtime:InvokeModel',
        'codepipeline:GetPipelineExecution',
        'codepipeline:ListPipelineExecutions',
        'codebuild:BatchGetBuilds'
      ],
      resources: ['*'],
    }));

    // Grant permission to publish to the SNS topic
    props.notificationTopic.grantPublish(this.project);
  }
}
