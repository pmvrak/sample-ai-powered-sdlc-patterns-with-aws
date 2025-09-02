import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';
import { Construct } from 'constructs';
import { CdkBuildProject } from '../projects';

interface BuildStageProps {
  pipeline: codepipeline.Pipeline;
  sourceArtifact: codepipeline.Artifact;
  sourceArtifactAppCode: codepipeline.Artifact
}

export class BuildStage extends Construct {
  public readonly buildOutput: codepipeline.Artifact;

  constructor(scope: Construct, id: string, props: BuildStageProps) {
    super(scope, id);

    const cdkBuildProject = new CdkBuildProject(this, 'CdkBuild');
    this.buildOutput = new codepipeline.Artifact('BuildOutput');

    props.pipeline.addStage({
      stageName: 'Build',
      actions: [
        new codepipeline_actions.CodeBuildAction({
          actionName: 'Build',
          project: cdkBuildProject.project,
          input: props.sourceArtifact,
          extraInputs: [props.sourceArtifactAppCode],
          outputs: [this.buildOutput],
        }),
      ],
    });
  }
}
