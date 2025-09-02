import * as cdk from 'aws-cdk-lib';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import { Construct } from 'constructs';
import { PipelineConfig } from '../../../configs/pipeline-config';

interface PipelineLogsProps {
  pipeline: codepipeline.Pipeline;
}

export class PipelineLogs extends Construct {
  public readonly logGroup: logs.LogGroup;

  constructor(scope: Construct, id: string, props: PipelineLogsProps) {
    super(scope, id);

    // Create log group for pipeline
    this.logGroup = new logs.LogGroup(this, 'PipelineLogGroup', {
      logGroupName: `/aws/codepipeline/${props.pipeline.pipelineName}`,
      retention: PipelineConfig.monitoring.logRetentionDays,
      removalPolicy: cdk.RemovalPolicy.DESTROY
    });

    // Create log metric filter for failures
    new logs.MetricFilter(this, 'FailureMetricFilter', {
      logGroup: this.logGroup,
      filterPattern: logs.FilterPattern.literal('ERROR'),
      metricNamespace: 'PipelineMetrics',
      metricName: 'ErrorCount',
      defaultValue: 0,
      metricValue: '1'
    });

    // Create insights query
    new cdk.CfnOutput(this, 'LogInsightsQuery', {
      value: `
        fields @timestamp, @message
        | filter @message like /ERROR/
        | sort @timestamp desc
        | limit 20
      `,
      description: 'CloudWatch Logs Insights query for pipeline errors',
    });
  }
}
