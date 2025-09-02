import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';
import { Construct } from 'constructs';

interface DeployStageProps {
  pipeline: codepipeline.Pipeline;
  buildArtifact: codepipeline.Artifact;
}

export class DeployStage extends Construct {
  constructor(scope: Construct, id: string, props: DeployStageProps) {
    super(scope, id);

    props.pipeline.addStage({
      stageName: 'Deploy',
      actions: [
        new codepipeline_actions.CloudFormationCreateUpdateStackAction({
          actionName: 'Deploy',
          templatePath: props.buildArtifact.atPath('MyApplicationStack.template.json'),
          stackName: 'MyApplicationStack',
          adminPermissions: true,
        })
      ],
    });
  }
}
