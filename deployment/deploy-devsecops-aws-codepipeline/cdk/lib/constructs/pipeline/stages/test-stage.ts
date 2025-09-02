import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';
import { Construct } from 'constructs';
import { UnitTestsProject } from '../projects';
import { LintProject } from '../projects';

interface TestStageProps {
  pipeline: codepipeline.Pipeline;
  sourceArtifact: codepipeline.Artifact;
  sourceArtifactAppCode: codepipeline.Artifact;
}

export class TestStage extends Construct {
  constructor(scope: Construct, id: string, props: TestStageProps) {
    super(scope, id);

    const unitTestsProject = new UnitTestsProject(this, 'UnitTests');
    const lintProject = new LintProject(this, 'Lint');

    props.pipeline.addStage({
      stageName: 'Test',
      actions: [
        new codepipeline_actions.CodeBuildAction({
          actionName: 'UnitTests',
          project: unitTestsProject.project,
          input: props.sourceArtifact,
          extraInputs: [props.sourceArtifactAppCode],
        }),
        new codepipeline_actions.CodeBuildAction({
          actionName: 'Lint',
          project: lintProject.project,
          input: props.sourceArtifact,
          extraInputs: [props.sourceArtifactAppCode],
        })
      ],
    });
  }
}
