import * as cdk from 'aws-cdk-lib';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export interface SbomAnalysisProjectProps {
  notificationTopic: cdk.aws_sns.Topic;
}
// lib/constructs/pipeline/projects/sbom-project.ts

export class SbomProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string, props: SbomAnalysisProjectProps) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'SBOMProject', {
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          install: {
            commands: [
              // Install Syft (universal SBOM generator)
              'curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin',
              'syft --version',

              'npm install -g aws-cdk',
              'npm install @aws-sdk/client-bedrock-runtime @aws-sdk/client-sns',
              'npm install json-stable-stringify',
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

              // Generate SBOM in both JSON and SPDX formats
              'echo "Generating SBOM..."',
              'syft . -o json=sbom.json -o spdx-json=sbom-spdx.json',
              
              'echo "SBOM generated, running analysis..."',
              'node ./cdk-pipeline/scripts/analyze-sbom.js',
              
              'echo "SBOM Analysis completed"',
              'cat sbom-analysis-report.md'
            ],
          },
        },
        artifacts: {
          files: [
            'sbom.json',
            'sbom-spdx.json',
            'sbom-analysis.json',
            'sbom-analysis-report.md',
          ],
        },
        reports: {
          SBOMReports: {
            files: [
              'sbom-analysis-report.md',
              'sbom.json'
            ],
          },
        },
      }),
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
        privileged: true,  // Needed for some Syft features
        environmentVariables: {
          SNS_TOPIC_ARN: { 
            value: props.notificationTopic.topicArn,
            type: codebuild.BuildEnvironmentVariableType.PLAINTEXT
          },
        },
      },
    });

    // Add permissions
    this.project.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'bedrock:InvokeModel',
        'bedrock-runtime:InvokeModel',
        'sns:Publish',
        'cloudformation:DescribeStacks',
        'cloudformation:ListStackResources'
      ],
      resources: ['*'],
    }));

    props.notificationTopic.grantPublish(this.project);
  }
}

