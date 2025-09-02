import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';
import { Construct } from 'constructs';
import { IntegrationTestProject } from '../projects/integration-test-project';
import { DeploytoTestProject } from '../projects/deploy-to-test-project';

interface DeployToTestStageProps {
  pipeline: codepipeline.Pipeline;
  buildArtifact: codepipeline.Artifact;
  sourceArtifact: codepipeline.Artifact;
  sourceArtifactAppCode: codepipeline.Artifact;
}

export class DeployToTestStage extends Construct {
  constructor(scope: Construct, id: string, props: DeployToTestStageProps) {
    super(scope, id);

    // Create deployment project
    const deployProject = new DeploytoTestProject(this, 'DeployToTest');

    // Create integration test project
    const integrationTestProject = new IntegrationTestProject(this, 'IntegrationTest');

    props.pipeline.addStage({
      stageName: 'DeploytoTest',
      actions: [
        new codepipeline_actions.CodeBuildAction({
          actionName: 'Deploy',
          project: deployProject.project,
          input: props.sourceArtifactAppCode,
          outputs: [new codepipeline.Artifact('DeployToTestOutput')],
          runOrder: 1
        }),
        // Integration test action
        new codepipeline_actions.CodeBuildAction({
          actionName: 'IntegrationTest',
          project: integrationTestProject.project,
          input: props.sourceArtifact,
          extraInputs: [props.sourceArtifactAppCode],
          outputs: [new codepipeline.Artifact('IntegrationTestOutput')],
          runOrder: 2  // This ensures it runs after the deployment
        })
      ],
    });
  }
}
