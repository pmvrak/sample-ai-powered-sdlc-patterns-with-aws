import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import { Construct } from 'constructs';
import { PipelineAlarms } from './pipeline-alarms';
import { PipelineMetrics, PipelineMetricSet } from './pipeline-metrics';
import { PipelineLogs } from './pipeline-logs';

interface PipelineMonitoringProps {
  pipeline: codepipeline.Pipeline;
}

export class PipelineMonitoring extends Construct {
  constructor(scope: Construct, id: string, props: PipelineMonitoringProps) {
    super(scope, id);

    // Create pipeline metrics
    const metrics = new PipelineMetrics(this, 'Metrics', {
      pipeline: props.pipeline
    });

    // Create pipeline alarms
    new PipelineAlarms(this, 'Alarms', {
      pipeline: props.pipeline,
      metrics: metrics.metrics
    });

    // Create pipeline logs
    new PipelineLogs(this, 'Logs', {
      pipeline: props.pipeline
    });

    // Create dashboard
    this.createDashboard(props.pipeline, metrics.metrics);
  }

  private createDashboard(pipeline: codepipeline.Pipeline, metrics: PipelineMetricSet) {
    const dashboard = new cloudwatch.Dashboard(this, 'PipelineDashboard', {
      dashboardName: `${pipeline.pipelineName}-Dashboard`,
    });

    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Pipeline Executions',
        left: [metrics.successRate, metrics.failureRate],
        width: 12
      }),
      new cloudwatch.GraphWidget({
        title: 'Stage Durations',
        left: [metrics.stageDuration],
        width: 12
      })
    );
  }
}
