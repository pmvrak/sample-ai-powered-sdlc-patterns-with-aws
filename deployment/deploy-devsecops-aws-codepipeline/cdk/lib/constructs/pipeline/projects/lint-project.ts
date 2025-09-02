import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import { Construct } from 'constructs';

export class LintProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'LintProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
        privileged: true,
      },
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          install: {
            commands: [
              'cd cdk-pipeline',
              'npm install',
              'npm install --save-dev eslint@^8.57.0',
              'npm install --save-dev @typescript-eslint/parser@^6.0.0',
              'npm install --save-dev @typescript-eslint/eslint-plugin@^6.0.0',
              'npm list eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin',
            ],
          },
          pre_build: {
            commands: [
              'echo "Preparing for lint..."',
              'pwd',
              'ls -la',
            ],
          },
          build: {
            commands: [
              'echo "Running lint..."',
              'npx eslint --config .eslintrc.js "lib/**/*.ts" "bin/**/*.ts" "test/**/*.ts"'
            ],
          },
        },
      }),
    });
  }
}
