import * as cdk from 'aws-cdk-lib';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';
import * as sns from 'aws-cdk-lib/aws-sns';
import { Construct } from 'constructs';
import { DeploymentAnalysisProject } from '../projects';
import { PipelineConfig } from '../../../configs/pipeline-config';

interface PreDeploymentStageProps {
  pipeline: codepipeline.Pipeline;
  sourceArtifact: codepipeline.Artifact;
  sourceArtifactAppCode: codepipeline.Artifact;
  buildArtifact: codepipeline.Artifact;
  notificationTopic: sns.Topic; 
}

export class PreDeploymentStage extends Construct {
  constructor(scope: Construct, id: string, props: PreDeploymentStageProps) {
    super(scope, id);

    // Get stack reference for region
    const stack = cdk.Stack.of(this);

    const deploymentAnalysisProject = new DeploymentAnalysisProject(this, 'DeploymentAnalysis', {
      notificationTopic: props.notificationTopic
    });

    props.pipeline.addStage({
      stageName: 'PreDeployment',
      actions: [
        new codepipeline_actions.CodeBuildAction({
          actionName: 'DeploymentAnalysis',
          project: deploymentAnalysisProject.project,
          input: props.sourceArtifact,
          extraInputs: [props.buildArtifact, props.sourceArtifactAppCode],
          outputs: [new codepipeline.Artifact('DeployAnalysisOutput')],
          runOrder: 1,
          environmentVariables: {
            BUILD_ARTIFACT_NAME: { value: props.buildArtifact.artifactName }
          }
        }),
        new codepipeline_actions.ManualApprovalAction({
          actionName: 'ManualApproval',
          additionalInformation: `Review Pipeline: https://${stack.region}.console.aws.amazon.com/codepipeline/home?region=${stack.region}

Key Review Points:
- Review the Deployment Analysis Report in previous stage
- Check source code changes in repository
- Verify all security checks have passed
- Confirm deployment compliance

Environment Info:
- Region: ${stack.region}
- Repository: ${PipelineConfig.source.repositoryOwner}/${PipelineConfig.source.repositoryName}
- Branch: ${PipelineConfig.source.branchName}

Contact development team for any concerns.`,
          runOrder: 3
        })
      ],
    });
  }
}
