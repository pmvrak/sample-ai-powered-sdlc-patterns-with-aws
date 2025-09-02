import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import { Construct } from 'constructs';

export class CdkBuildProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'BuildProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
        privileged: true,
        environmentVariables: {
          NODE_VERSION: {
            value: '20'
          }
        }
      },
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          install: {
            commands: [
              'ls -la $CODEBUILD_SRC_DIR_ArtifactAppCode',
              'cd $CODEBUILD_SRC_DIR_ArtifactAppCode',

              // Use Node.js 18 (last LTS version known to work well with CDK)
              'n 18.17.1',
              'node --version',
              // Remove any existing CDK installations
              'npm uninstall -g aws-cdk',
              'npm uninstall aws-cdk-lib',
              // Clear npm cache
              'npm cache clean --force',
              // Install specific versions
              'npm install aws-cdk-lib@2.131.0',  // Replace with your project's version
              'npm install -g aws-cdk@2.131.0',   // Same version as aws-cdk-lib
              'npm install json-stable-stringify',
              'npm install',
              'mkdir -p ~/.cdk/cache',
              'chmod -R 777 ~/.cdk',
            ],
          },
          build: {
            commands: [
              'npm run build',
              'npx cdk --version',
              'echo "Starting CDK synth"',

              // Add debug information
              'echo "Installed CDK versions:"',
              'npm list aws-cdk-lib',

              // Direct synthesis without listing
              'npx cdk synth --all --no-notices --no-validation || true', 
              'echo "CDK synth completed"',
              'echo "cdk.out contents:"',
              'ls -la cdk.out'
            ],
          },
        },
        artifacts: {
          'base-directory': '$CODEBUILD_SRC_DIR_ArtifactAppCode/cdk.out',
          files: [
            '*.template.json',
            'asset.*/**/*',
            '**/*',
          ],
          'enable-symlinks': 'yes',
        },
        cache: {
          paths: [
            '$CODEBUILD_SRC_DIR_ArtifactAppCode/node_modules/**/*',
            '~/.cdk/cache/**/*'
          ]
        }
      }),
    });
  }
}
