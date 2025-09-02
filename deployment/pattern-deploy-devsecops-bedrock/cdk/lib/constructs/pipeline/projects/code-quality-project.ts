import * as cdk from 'aws-cdk-lib';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export class CodeQualityProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'CodeQualityProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
        privileged: true,
        environmentVariables: {
          AWS_REGION: {
            value: cdk.Stack.of(this).region,
            type: codebuild.BuildEnvironmentVariableType.PLAINTEXT
          },
          // APPLICATION_STACK_NAME: {
          //   value: 'MyApplicationStack',
          //   type: codebuild.BuildEnvironmentVariableType.PLAINTEXT
          // }
        }
      },
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          install: {
            commands: [
              'npm install -g aws-cdk',
              'npm install @aws-sdk/client-bedrock-runtime',
              'npm install json-stable-stringify',
              'aws --version',
            ],
          },
          pre_build: {
            commands: [
              'echo "Preparing for analysis..."',
              'echo "Current directory:"',
              'pwd',
              'echo "Directory contents:"',
              'ls -la',

              'echo "Looking for application stack template..."',
              'find . -name "*.template.json"'
            ]
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

              'echo "Starting code quality using Bedrock..."',
              'node ./cdk-pipeline/scripts/analyze-code-quality.js',

              'echo "Verifying analysis results..."',
              'if [ ! -f code_quality_report.md ]; then \
                echo "Error: Analysis report not generated"; \
                exit 1; \
              fi',

              'echo "Analysis completed. Generated report:"',
              'cat code_quality_report.md'
            ],
          },
          post_build: {
            commands: [
              'echo "Checking generated files:"',
              'ls -la *.json *.md || true',
              'echo "Code quality analysis stage completed"'
            ],
          },
        },
        artifacts: {
          files: [
            'code_quality_report.md'
          ],
        },
        reports: {
          CodeQualityReports: {
            files: [
              'code_quality_report.md',
            ],
            'base-directory': '.',
          },
        },
      }),
    });

    this.project.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'bedrock-runtime:InvokeModel',
        'bedrock:InvokeModel',
      ],
      resources: ['*'],
    }));
  }
}
