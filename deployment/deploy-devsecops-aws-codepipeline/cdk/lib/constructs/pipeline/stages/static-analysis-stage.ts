import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';
import { Construct } from 'constructs';
import { CodeQualityProject } from '../projects';
import { SastProject } from '../projects';

interface StaticAnalysisStageProps {
  pipeline: codepipeline.Pipeline;
  sourceArtifact: codepipeline.Artifact;
  sourceArtifactAppCode: codepipeline.Artifact;
  buildArtifact: codepipeline.Artifact
}

export class StaticAnalysisStage extends Construct {
  constructor(scope: Construct, id: string, props: StaticAnalysisStageProps) {
    super(scope, id);

    const codeQualityProject = new CodeQualityProject(this, 'CodeQuality');
    const sastProject = new SastProject(this, 'SAST');

    props.pipeline.addStage({
      stageName: 'StaticAnalysis',
      actions: [
        new codepipeline_actions.CodeBuildAction({
          actionName: 'CodeQuality',
          project: codeQualityProject.project,
          input: props.sourceArtifact,
          extraInputs: [props.buildArtifact, props.sourceArtifactAppCode],
          outputs: [new codepipeline.Artifact('CodeQualityOutput')],
          environmentVariables: {
            APPLICATION_STACK_NAME: { value: 'ApplicationStack' }
          },
          runOrder: 1
        }),
        new codepipeline_actions.CodeBuildAction({
          actionName: 'SAST',
          project: sastProject.project,
          input: props.sourceArtifact,
          extraInputs: [props.sourceArtifactAppCode],
          outputs: [new codepipeline.Artifact('SASTOutput')],
          runOrder: 1
        })
      ],
    });
  }
}
