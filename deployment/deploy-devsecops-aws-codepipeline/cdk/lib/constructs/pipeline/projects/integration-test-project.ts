import * as cdk from 'aws-cdk-lib';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export class IntegrationTestProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'IntegrationTestProject', {
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
              'npm install --prefix ./cdk-pipeline',
              'npm install -g aws-cdk',
              'npm install json-stable-stringify',
              'npm install -g typescript ts-node',
              'npm install axios',
              'npm install @aws-sdk/client-bedrock-runtime @aws-sdk/client-cloudformation',
              'npm install --save-dev @types/node jest @types/jest ts-jest @aws-sdk/client-bedrock-runtime',
              // Copy tsconfig.json if it doesn't exist in the root
              'if [ ! -f tsconfig.json ]; then cp cdk-pipeline/tsconfig.json ./tsconfig.json || echo "{}" > tsconfig.json; fi',
            ],
          },
          pre_build: {
            commands: [
              'echo "Generating integration tests..."',
              'npx ts-node ./cdk-pipeline/scripts/generate-integration-tests.ts',
              'echo "Generated test files:"',
              'ls -la ./cdk-pipeline/test/',

              'echo "Preparing for integration tests..."',
              'npm list -g typescript ts-node || npm install -g typescript ts-node', // Verify global installation
              'echo "TypeScript version:" && npx tsc --version',
              'echo "ts-node version:" && npx ts-node --version',
              'echo "Node version:" && node --version',
              'echo "Current directory:"',
              'pwd',
              'echo "Directory contents:"',
              'ls -la',
            ]
          },
          build: {
            commands: [
              'echo "Installing required AWS SDK clients..."',
              'REQUIRED_CLIENTS=$(grep -oP "(?<=@aws-sdk/client-)[a-z-]+" ./cdk-pipeline/test/stack.integration.test.ts | sort -u)',
              'for CLIENT in $REQUIRED_CLIENTS; do npm install @aws-sdk/client-$CLIENT; done',

              'echo "Running integration tests..."',
              'npx jest --config=./cdk-pipeline/jest.integration.config.js --json --outputFile=test-results.json || true',
              'npx ts-node ./cdk-pipeline/scripts/analyze-test-results.ts',
              'echo "Verifying test analysis..."',
              'if [ ! -f integration_test_report.md ]; then \
                echo "Error: Test analysis report not generated"; \
                exit 1; \
              fi',
              'echo "Analysis completed. Test report:"',
              'cat integration_test_report.md'
            ],
          },
        },
        artifacts: {
          files: [
            'integration_test_report.md',
            'test-results.json',
            './cdk-pipeline/test/*.ts'
          ]
        },
        reports: {
          IntegrationTestReports: {
            files: [
              'integration_test_report.md'
            ],
            'base-directory': '.'
          }
        }
      }),
    });

    // Add Bedrock permissions
    this.project.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'bedrock:InvokeModel',
        'bedrock-runtime:InvokeModel',
        'cloudformation:DescribeStacks',
        'cloudformation:List*'
      ],
      resources: ['*'],
    }));
  }
}
