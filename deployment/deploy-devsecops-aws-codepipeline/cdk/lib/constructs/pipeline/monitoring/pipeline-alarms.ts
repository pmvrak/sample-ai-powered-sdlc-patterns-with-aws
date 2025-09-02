import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import { Construct } from 'constructs';
import { PipelineMetricSet } from './pipeline-metrics';

interface PipelineAlarmsProps {
  pipeline: codepipeline.Pipeline;
  metrics: PipelineMetricSet;
}

export class PipelineAlarms extends Construct {
  constructor(scope: Construct, id: string, props: PipelineAlarmsProps) {
    super(scope, id);

    // Pipeline failure alarm
    new cloudwatch.Alarm(this, 'PipelineFailureAlarm', {
      metric: props.metrics.failureRate,
      threshold: 1,
      evaluationPeriods: 1,
      alarmDescription: 'Alert on pipeline failure',
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING
    });

    // Pipeline success rate alarm
    new cloudwatch.Alarm(this, 'PipelineSuccessRateAlarm', {
      metric: props.metrics.successRate,
      threshold: 0,
      evaluationPeriods: 3,
      comparisonOperator: cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
      alarmDescription: 'Alert when no successful pipeline executions',
      treatMissingData: cloudwatch.TreatMissingData.BREACHING
    });

    // Stage duration alarm
    new cloudwatch.Alarm(this, 'StageDurationAlarm', {
      metric: props.metrics.stageDuration,
      threshold: 3600, // 1 hour in seconds
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      alarmDescription: 'Alert when stage duration exceeds 1 hour',
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING
    });

    // Security findings alarm
    new cloudwatch.Alarm(this, 'SecurityFindingsAlarm', {
      metric: new cloudwatch.Metric({
        namespace: 'SecurityPipeline',
        metricName: 'CriticalFindings',
        dimensionsMap: {
          Pipeline: props.pipeline.pipelineName,
          Stage: 'SecurityScan',
        },
      }),
      threshold: 1,
      evaluationPeriods: 1,
      alarmDescription: 'Alert on critical security findings',
    });
  }
}
