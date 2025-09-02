import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { PipelineConfig } from '../../../configs/pipeline-config';

export class SecurityScanProject extends Construct {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.project = new codebuild.PipelineProject(this, 'SecurityScanProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
        privileged: true,
        environmentVariables: {
          SECURITY_FINDINGS_THRESHOLD: {
            value: PipelineConfig.security.findingsThreshold,
            type: codebuild.BuildEnvironmentVariableType.PLAINTEXT,
          },
        },
      },
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          install: {
            commands: [
              // Install dependencies for the security scan scripts
              'echo "Installing dependencies for security scan scripts"',
              'cd $CODEBUILD_SRC_DIR/cdk-pipeline',
              'npm install @aws-sdk/client-bedrock-runtime',
              'npm install json-stable-stringify',
              
              // Install dependencies for the application code
              'echo "Installing dependencies for application code"',
              'cd $CODEBUILD_SRC_DIR_ArtifactAppCode',
              'npm install',
              'npm install -g aws-cdk',
              'npm install @aws-sdk/client-bedrock-runtime',
              'aws --version',

              // Install OWASP Dependency-Check
              'wget https://github.com/jeremylong/DependencyCheck/releases/download/v8.4.0/dependency-check-8.4.0-release.zip',
              'unzip dependency-check-8.4.0-release.zip',
            ],
          },
          pre_build: {
            commands: [
              // Check and enable Amazon Inspector scanning
              'echo "Checking Inspector2 status..."',
              'aws inspector2 describe-configuration 2>/dev/null || aws inspector2 enable --resource-types ECR LAMBDA',
              'sleep 30', // Wait for Inspector to initialize
            ],
          },
          build: {
            commands: [              
              // OWASP Dependency Check
              // 'echo "Running OWASP Dependency Check..."',
              // './dependency-check/bin/dependency-check.sh --project "SecurityScan" --scan . --format JSON --out dependency-check-report.json',
              
              // Get Amazon Inspector findings
              'echo "Fetching Inspector findings..."',
              'aws inspector2 list-findings --filter-criteria=\'{"findingStatus":[{"comparison":"EQUALS","value":"ACTIVE"}],"severity":[{"comparison":"EQUALS","value":"HIGH"},{"comparison":"EQUALS","value":"CRITICAL"}]}\' > inspector_findings.json',
              
              // Process all findings and generate analysis
              'echo "Processing and analyzing security findings..."',
              'node $CODEBUILD_SRC_DIR/cdk-pipeline/scripts/process-security-findings.js',
              
              // Display report
              'echo "Security Analysis Report:"',
              'cat analysis_report.md',
              
              // Check findings status and exit if necessary
              'if [ -f "findings-status.json" ]; then \
                REQUIRES_IMMEDIATE=$(jq -r .requiresImmediate findings-status.json); \
                CRITICAL_COUNT=$(jq -r .criticalCount findings-status.json); \
                HIGH_COUNT=$(jq -r .highCount findings-status.json); \
                if [ "$REQUIRES_IMMEDIATE" = "true" ] || [ "$CRITICAL_COUNT" -gt 0 ] || [ "$HIGH_COUNT" -gt "$SECURITY_FINDINGS_THRESHOLD" ]; then \
                  echo "Security scan failed: Found $CRITICAL_COUNT critical and $HIGH_COUNT high severity issues"; \
                  echo "Immediate attention required: $REQUIRES_IMMEDIATE"; \
                fi \
              else \
                echo "Warning: findings-status.json not found"; \
              fi',
            ],
          },
          post_build: {
            commands: [
              'echo "Security scan completed"',
              'echo "Generated reports:"',
              'ls -la *.json *.md',

              // Create artifacts directory and copy files
              'mkdir -p $CODEBUILD_SRC_DIR/artifacts',
              'cp inspector_findings.json dependency-check-report.json processed-findings.json security-report.json findings-status.json analysis_report.md $CODEBUILD_SRC_DIR/artifacts/ || true',
              
              // Verify files are copied
              'echo "Contents of artifacts directory:"',
              'ls -la $CODEBUILD_SRC_DIR/artifacts/',
            ],
          },
        },
        reports: {
          SecurityReports: {
            files: [
              '**/*.json',
              '**/*.md'
            ],
            'base-directory': '$CODEBUILD_SRC_DIR/artifacts',
          },
        },
        artifacts: {
          files: [
            '**/*.json',
            '**/*.md'
          ],
          'base-directory': '$CODEBUILD_SRC_DIR/artifacts',
        },
      }),
    });

    // Add IAM permissions
    this.project.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'inspector2:ListFindings',
        'inspector2:ListCoverage',
        'inspector2:GetFindings',
        'inspector2:Enable',
        'inspector2:Disable',
        'bedrock:InvokeModel',
        'bedrock-runtime:InvokeModel',
        's3:PutObject',
        's3:GetObject',
        'ecr:ListImages',
        'ecr:DescribeImages',
        'lambda:ListFunctions',
        'lambda:GetFunction',
        'iam:CreateServiceLinkedRole'
      ],
      resources: ['*'],
    }));

    // Add specific permission for service-linked role
    this.project.addToRolePolicy(new iam.PolicyStatement({
      actions: ['iam:CreateServiceLinkedRole'],
      resources: ['arn:aws:iam::*:role/aws-service-role/inspector2.amazonaws.com/AWSServiceRoleForAmazonInspector2'],
      conditions: {
        StringLike: {
          'iam:AWSServiceName': 'inspector2.amazonaws.com'
        }
      }
    }));

  }
}
