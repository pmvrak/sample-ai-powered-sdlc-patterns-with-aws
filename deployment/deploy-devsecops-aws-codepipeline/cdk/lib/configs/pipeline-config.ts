export const PipelineConfig = {
    source: {
      connectionArn: 'arn:aws:codeconnections:us-east-1:xxxxxxxxxxx:connection/xxxxxxxxxxx',
      repositoryOwner: 'xxxxxxxxxxx',    // Organization/owner name
      repositoryName: 'xxxxxxxxxxx',      // Repository name
      branchName: 'main',
      type: 'GITLAB'  // Optional: to identify source type
    },
    source_app_code: {
      connectionArn: 'arn:aws:codeconnections:us-east-1:xxxxxxxxxxxx:connection/xxxxxxxxxxx',
      repositoryOwner: 'xxxxxxxxxxx',    // Organization/owner name
      repositoryName: 'xxxxxxxxxxx',      // Repository name
      branchName: 'main',
      type: 'GITLAB'  // Optional: to identify source type
    },
    pipeline: {
      name: 'iCodePipeline_Gitlab',
    },
    notification: {
      email: 'xxxx@amazon.com', // Replace with your email
    },
    security: {
      findingsThreshold: '80',
    },
    monitoring: {
      logRetentionDays: 7,
      alarms: {
        failureThreshold: 1,
        successRateThreshold: 0,
        stageDurationThreshold: 3600, // 1 hour in seconds
        criticalFindingsThreshold: 1
      },
      dashboard: {
        refreshRate: 300, // 5 minutes in seconds
        widgets: {
          graphWidth: 12
        }
      }
    }
  };
  