import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';
import { Construct } from 'constructs';
import * as sns from 'aws-cdk-lib/aws-sns';
import { 
  SecurityScanProject,
  SecretsDetectionProject,
  SbomProject 
} from '../projects';

interface SecurityAnalysisStageProps {
  pipeline: codepipeline.Pipeline;
  sourceArtifact: codepipeline.Artifact;
  sourceArtifactAppCode: codepipeline.Artifact;
  buildArtifact: codepipeline.Artifact
  notificationTopic: sns.Topic; 
}

export class SecurityAnalysisStage extends Construct {
  constructor(scope: Construct, id: string, props: SecurityAnalysisStageProps) {
    super(scope, id);

    const securityScanProject = new SecurityScanProject(this, 'SecurityScan');
    const secretsDetectionProject = new SecretsDetectionProject(this, 'SecretsDetection');
    const sbomProject = new SbomProject(this, 'SBOM', {
      notificationTopic: props.notificationTopic
    });

    props.pipeline.addStage({
      stageName: 'SecurityAnalysis',
      actions: [
        new codepipeline_actions.CodeBuildAction({
          actionName: 'SecurityScan',
          project: securityScanProject.project,
          input: props.sourceArtifact,
          extraInputs: [props.sourceArtifactAppCode],
          outputs: [new codepipeline.Artifact('SecurityOutput')],
          runOrder: 1
        }),
        new codepipeline_actions.CodeBuildAction({
          actionName: 'SecretsDetection',
          project: secretsDetectionProject.project,
          input: props.sourceArtifact,
          extraInputs: [props.sourceArtifactAppCode],
          outputs: [new codepipeline.Artifact('SecretsOutput')],
          runOrder: 1
        }),
        new codepipeline_actions.CodeBuildAction({
          actionName: 'SBOMAnalysis',
          project: sbomProject.project,
          input: props.sourceArtifact,
          extraInputs: [props.sourceArtifactAppCode, props.buildArtifact],
          outputs: [new codepipeline.Artifact('SBOMOutput')],
          runOrder: 2
        })
      ],
    });
  }
}
