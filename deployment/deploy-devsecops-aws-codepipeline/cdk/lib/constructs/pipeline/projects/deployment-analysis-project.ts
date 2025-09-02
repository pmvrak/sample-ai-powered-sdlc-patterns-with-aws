import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as sns from 'aws-cdk-lib/aws-sns';
import { Construct } from 'constructs';

export interface DeploymentAnalysisProjectProps {
  notificationTopic: sns.Topic;
}

export class DeploymentAnalysisProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string, props: DeploymentAnalysisProjectProps) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'AIDeployAnalysisProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
        privileged: true,
        environmentVariables: {
          SNS_TOPIC_ARN: {
            value: props.notificationTopic.topicArn,
            type: codebuild.BuildEnvironmentVariableType.PLAINTEXT
          }
        }
      },
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          install: {
            commands: [
              'npm install -g aws-cdk',
              'npm install @aws-sdk/client-bedrock-runtime @aws-sdk/client-sns',
              'npm install json-stable-stringify',
              'aws --version',
            ],
          },
          build: {
            commands: [
              'echo "Current directory:"',
              'pwd',
              'echo "Directory contents:"',
              'ls -la',

              // Create template directory and copy templates
              'TEMPLATE_DIR="templates"',
              'mkdir -p $TEMPLATE_DIR',
              'for f in $(find /codebuild/output/src* -type f -name "*.template.json"); do cp "$f" "$TEMPLATE_DIR/"; done',
              
              // Verify templates were copied
              'if [ "$(ls -A $TEMPLATE_DIR)" ]; then echo "Templates copied successfully to $TEMPLATE_DIR"; else echo "No template files found" && exit 1; fi',
              
              // List copied templates
              'echo "Copied templates:"',
              'ls -la $TEMPLATE_DIR',

              'echo "Running deployment analysis..."',
              'node ./cdk-pipeline/scripts/analyze-deployment.js',
              'echo "Analysis results:"',
              'cat deployment_report.md'
            ],
          },
          post_build: {
            commands: [
              'echo "Deployment analysis completed"',
              'echo "Generated files:"',
              'ls -la'
            ],
          },
        },
        artifacts: {
          files: [
            'deployment_analysis.json',
            'deployment_report.md',
            'deployment_request.json',
            'template_summary.json',
            'template.json'
          ],
          'base-directory': '.',
        },
        reports: {
          DeploymentReports: {
            files: [
              'deployment_report.md'
            ],
            'base-directory': '.',
          },
        },
      }),
    });

    this.project.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'bedrock:InvokeModel',
        'bedrock-runtime:InvokeModel',
        'sns:Publish',
      ],
      resources: ['*'],
    }));

    props.notificationTopic.grantPublish(this.project);
  }
}
