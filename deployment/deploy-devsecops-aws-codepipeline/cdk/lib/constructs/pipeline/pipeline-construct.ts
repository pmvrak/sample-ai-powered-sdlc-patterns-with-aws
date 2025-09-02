import * as cdk from 'aws-cdk-lib';
import * as codecommit from 'aws-cdk-lib/aws-codecommit';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';
import { Construct } from 'constructs';
import { PipelineConfig } from '../../configs/pipeline-config';
import {
  StaticAnalysisStage,
  SecurityAnalysisStage,
  TestStage,
  BuildStage,
  PreDeploymentStage,
  DeployToTestStage
} from './stages';
import { FailureHandling } from './failure-handling';

export class PipelineConstruct extends Construct {
  public readonly pipeline: codepipeline.Pipeline;
  public readonly repository: codecommit.Repository;
  public readonly failureHandling: FailureHandling

  constructor(scope: Construct, id: string) {
    super(scope, id);

    // Create Pipeline
    this.pipeline = new codepipeline.Pipeline(this, 'Pipeline', {
      pipelineName: PipelineConfig.pipeline.name,
      crossAccountKeys: false,
      artifactBucket: new cdk.aws_s3.Bucket(this, 'ArtifactBucket', {
        removalPolicy: cdk.RemovalPolicy.DESTROY,
        autoDeleteObjects: true,
      }),
    });

    // Create source output
    const sourceOutput = new codepipeline.Artifact();
    const sourceOutputAppCode = new codepipeline.Artifact("ArtifactAppCode");

    // Add GitLab source stage
    this.pipeline.addStage({
      stageName: 'sourceStage',
      actions: [
        new codepipeline_actions.CodeStarConnectionsSourceAction({
          actionName: 'GitLab_Source',
          owner: PipelineConfig.source.repositoryOwner,
          repo: PipelineConfig.source.repositoryName,
          branch: PipelineConfig.source.branchName,
          connectionArn: PipelineConfig.source.connectionArn,
          output: sourceOutput,
        }),
        new codepipeline_actions.CodeStarConnectionsSourceAction({
          actionName: 'GitLab_Source_App',
          owner: PipelineConfig.source_app_code.repositoryOwner,
          repo: PipelineConfig.source_app_code.repositoryName,
          branch: PipelineConfig.source_app_code.branchName,
          connectionArn: PipelineConfig.source_app_code.connectionArn,
          output: sourceOutputAppCode,
        })
      ],
    });

    // Create failure handling first
    this.failureHandling = new FailureHandling(this, 'FailureHandling', {
      pipeline: this.pipeline
    });

    const buildStage = new BuildStage(this, 'Build', {
      pipeline: this.pipeline,
      sourceArtifact: sourceOutput,
      sourceArtifactAppCode: sourceOutputAppCode
    });
    
    new StaticAnalysisStage(this, 'StaticAnalysis', {
      pipeline: this.pipeline,
      sourceArtifact: sourceOutput,
      sourceArtifactAppCode: sourceOutputAppCode,
      buildArtifact: buildStage.buildOutput
    });

    new SecurityAnalysisStage(this, 'SecurityAnalysis', {
      pipeline: this.pipeline,
      sourceArtifact: sourceOutput,
      sourceArtifactAppCode: sourceOutputAppCode,
      notificationTopic: this.failureHandling.failureNotificationTopic,
      buildArtifact: buildStage.buildOutput
    });

    new TestStage(this, 'Test', {
      pipeline: this.pipeline,
      sourceArtifact: sourceOutput,
      sourceArtifactAppCode: sourceOutputAppCode,
    });

    new PreDeploymentStage(this, 'PreDeployment', {
      pipeline: this.pipeline,
      sourceArtifact: sourceOutput,
      sourceArtifactAppCode: sourceOutputAppCode,
      buildArtifact: buildStage.buildOutput,
      notificationTopic: this.failureHandling.failureNotificationTopic  // Pass the existing topic
    });

    new DeployToTestStage(this, 'DeployToTest', {
      pipeline: this.pipeline,
      sourceArtifact: sourceOutput,
      sourceArtifactAppCode: sourceOutputAppCode,
      buildArtifact: buildStage.buildOutput
    });
  }
}
