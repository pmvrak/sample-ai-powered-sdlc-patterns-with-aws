import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import { Construct } from 'constructs';

export class UnitTestsProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'UnitTestsProject', {
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
              'npm install jest @types/jest ts-jest --save-dev'
            ],
          },
          build: {
            commands: [
              'echo "Running unit tests..."',
              'npm test'
            ],
          },
        },
        reports: {
          junit_reports: {
            files: [
              'junit.xml'
            ],
            'file-format': 'JUNITXML',
          },
        },
      }),
    });
  }
}
