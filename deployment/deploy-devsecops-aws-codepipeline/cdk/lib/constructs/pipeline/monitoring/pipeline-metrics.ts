import * as cdk from 'aws-cdk-lib';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import { Construct } from 'constructs';

export interface PipelineMetricSet {
  successRate: cloudwatch.Metric;
  failureRate: cloudwatch.Metric;
  stageDuration: cloudwatch.Metric;
}

interface PipelineMetricsProps {
  pipeline: codepipeline.Pipeline;
}

export class PipelineMetrics extends Construct {
  public readonly metrics: PipelineMetricSet;

  constructor(scope: Construct, id: string, props: PipelineMetricsProps) {
    super(scope, id);

    this.metrics = {
      successRate: new cloudwatch.Metric({
        namespace: 'AWS/CodePipeline',
        metricName: 'SuccessCount',
        dimensionsMap: {
          PipelineName: props.pipeline.pipelineName
        },
        statistic: 'Sum',
        period: cdk.Duration.minutes(5)
      }),

      failureRate: new cloudwatch.Metric({
        namespace: 'AWS/CodePipeline',
        metricName: 'FailedPipeline',
        dimensionsMap: {
          PipelineName: props.pipeline.pipelineName
        },
        statistic: 'Sum',
        period: cdk.Duration.minutes(5)
      }),

      stageDuration: new cloudwatch.Metric({
        namespace: 'AWS/CodePipeline',
        metricName: 'StageDuration',
        dimensionsMap: {
          PipelineName: props.pipeline.pipelineName
        },
        statistic: 'Average',
        period: cdk.Duration.minutes(5)
      })
    };
  }
}
