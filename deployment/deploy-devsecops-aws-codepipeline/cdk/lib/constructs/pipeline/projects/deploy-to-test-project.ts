import * as cdk from 'aws-cdk-lib';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export class DeploytoTestProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'DeploytoTestProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
        privileged: true,
        environmentVariables: {
          AWS_REGION: {
            value: cdk.Stack.of(this).region,
            type: codebuild.BuildEnvironmentVariableType.PLAINTEXT
          },
        }
      },
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          install: {
            commands: [
              'npm install -g aws-cdk',
              'npm install',
              'npm run build'
            ]
          },
          build: {
            commands: [
              'echo "Deploying CDK stacks..."',
              'npx cdk deploy --all --require-approval never'
            ],
          },
        },
      }),
    });

    // Add required permissions
    this.project.addToRolePolicy(new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
            'cloudformation:CreateStack',
            'cloudformation:UpdateStack',
            'cloudformation:DeleteStack',
            'cloudformation:DescribeStacks',
            'cloudformation:ListStacks',
            'cloudformation:CreateChangeSet',
            'cloudformation:ExecuteChangeSet',
            'cloudformation:DeleteChangeSet',
            'cloudformation:DescribeChangeSet',
            'cloudformation:ValidateTemplate',
            'cloudformation:GetTemplateSummary',
            'cloudformation:DescribeStackEvents',
            'cloudformation:ListStackResources'
        ],
        resources: ['*']
    }));

    // Add permissions for creating and managing resources
    this.project.addToRolePolicy(new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['*'],
        resources: ['*']
    }));

  }
}
