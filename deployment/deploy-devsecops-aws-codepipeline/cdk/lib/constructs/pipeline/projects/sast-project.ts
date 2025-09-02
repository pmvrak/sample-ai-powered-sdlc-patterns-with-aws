import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export class SastProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'AISastProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
        privileged: true,
        environmentVariables: {
          SAST_SEVERITY_THRESHOLD: {
            value: 'HIGH',
            type: codebuild.BuildEnvironmentVariableType.PLAINTEXT,
          },
          SAST_MAX_HIGH_FINDINGS: {
            value: '3',
            type: codebuild.BuildEnvironmentVariableType.PLAINTEXT,
          },
          SAST_MAX_MEDIUM_FINDINGS: {
            value: '5',
            type: codebuild.BuildEnvironmentVariableType.PLAINTEXT,
          },
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
          build: {
            commands: [
              'ls -la $CODEBUILD_SRC_DIR_ArtifactAppCode',
              'cd $CODEBUILD_SRC_DIR_ArtifactAppCode',

              // Initialize empty files
              'echo "{}" > sast_analysis.json',
              'echo "# SAST Analysis Report\n\nAnalysis in progress..." > sast_report.md',
              
              // Run SAST analysis
              'echo "Starting SAST Analysis..."',
              'node $CODEBUILD_SRC_DIR/cdk-pipeline/scripts/analyze-sast.js',
              
              // Display report
              'echo "SAST Report Content:"',
              'cat sast_report.md',
              
              // Check findings
              'if [ -f "sast_findings.json" ]; then\n' +
              '  CRITICAL_COUNT=$(jq -r ".summary.critical" sast_findings.json)\n' +
              '  HIGH_COUNT=$(jq -r ".summary.high" sast_findings.json)\n' +
              '  MEDIUM_COUNT=$(jq -r ".summary.medium" sast_findings.json)\n' +
              '  if [ "$CRITICAL_COUNT" -gt 0 ] || ' +
              '     [ "$HIGH_COUNT" -gt "$SAST_MAX_HIGH_FINDINGS" ] || ' +
              '     [ "$MEDIUM_COUNT" -gt "$SAST_MAX_MEDIUM_FINDINGS" ]; then\n' +
              '    echo "SAST analysis failed: Threshold exceeded"\n' +
              '    exit 1\n' +
              '  fi\n' +
              'fi'
            ],
          },
          post_build: {
            commands: [
              'echo "SAST analysis completed"',
              'echo "Generated files:"',
              'ls -la *.json *.md || true'
            ],
          },
        },
        artifacts: {
          files: [
            'sast_analysis.json',
            'sast_report.json',
            'sast_report.md',
            'sast_findings.json',
            'sast_request.json'
          ],
          'base-directory': '$CODEBUILD_SRC_DIR_ArtifactAppCode',
        },
        reports: {
          SASTReports: {
            files: [
              'sast_report.md',
              'sast_report.json'
            ],
            'base-directory': '$CODEBUILD_SRC_DIR_ArtifactAppCode',
          },
        },
      }),
    });

    // Add Bedrock permissions
    this.project.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'bedrock:InvokeModel',
        'bedrock-runtime:InvokeModel',
      ],
      resources: ['*'],
    }));
  }
}
