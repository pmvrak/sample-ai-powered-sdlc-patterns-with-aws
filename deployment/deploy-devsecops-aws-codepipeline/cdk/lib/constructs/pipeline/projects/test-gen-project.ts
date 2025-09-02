import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export class TestGenProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'AITestGenProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_6_0,
        privileged: true,
      },
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          build: {
            commands: [
              'echo "This is AI Test Generation Stage"',
            ],
          },
        },
      }),
    });

    this.project.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'bedrock:InvokeModel',
        'bedrock-runtime:InvokeModel',
      ],
      resources: ['*'],
    }));
  }
}
