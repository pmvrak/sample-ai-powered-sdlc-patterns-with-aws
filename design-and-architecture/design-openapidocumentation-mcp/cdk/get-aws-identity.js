#!/usr/bin/env node

/**
 * Get current AWS identity for OpenSearch access policy
 */

const { STSClient, GetCallerIdentityCommand } = require('@aws-sdk/client-sts');

async function getCurrentAwsIdentity(silent = false) {
  try {
    const stsClient = new STSClient({ region: process.env.AWS_REGION || 'eu-west-1' });
    const command = new GetCallerIdentityCommand({});
    const response = await stsClient.send(command);
    
    const { Account, Arn, UserId } = response;
    
    if (!silent) {
      console.log('Current AWS Identity:');
      console.log(`Account: ${Account}`);
      console.log(`ARN: ${Arn}`);
      console.log(`User ID: ${UserId}`);
    }
    
    // Determine the appropriate ARN for OpenSearch access
    let accessArn;
    
    if (Arn.includes(':user/')) {
      // IAM User
      accessArn = Arn;
    } else if (Arn.includes(':role/')) {
      // IAM Role (e.g., from AWS CLI profiles or EC2 instance roles)
      accessArn = Arn;
    } else if (Arn.includes(':assumed-role/')) {
      // Assumed role - extract the role ARN
      const roleMatch = Arn.match(/arn:aws:sts::[0-9]+:assumed-role\/([^\/]+)\//);
      if (roleMatch) {
        accessArn = `arn:aws:iam::${Account}:role/${roleMatch[1]}`;
      } else {
        accessArn = Arn;
      }
    } else {
      // Fallback to account root
      accessArn = `arn:aws:iam::${Account}:root`;
    }
    
    if (!silent) {
      console.log(`\nRecommended OpenSearch Access ARN: ${accessArn}`);
    }
    
    return {
      account: Account,
      arn: Arn,
      userId: UserId,
      accessArn: accessArn
    };
    
  } catch (error) {
    if (!silent) {
      console.error('Error getting AWS identity:', error.message);
    }
    throw error;
  }
}

// Run if called directly
if (require.main === module) {
  // Check if --arn-only flag is provided
  const arnOnly = process.argv.includes('--arn-only');
  
  getCurrentAwsIdentity(arnOnly)
    .then(identity => {
      if (arnOnly) {
        // Just output the ARN for programmatic use
        console.log(identity.accessArn);
      } else {
        console.log('\n✅ AWS identity retrieved successfully');
        console.log('\n💡 To use this identity for OpenSearch access:');
        console.log('\n🔧 Option 1: Set environment variable (recommended):');
        console.log(`   export CDK_IAM_USER_ARN="${identity.accessArn}"`);
        console.log(`   cdk deploy OpenSearchStack`);
        console.log('\n🔧 Option 2: Use with deploy script:');
        console.log(`   CDK_IAM_USER_ARN="${identity.accessArn}" ./deploy.sh`);
        console.log('\n🔧 Option 3: Add to your shell profile:');
        console.log(`   echo 'export CDK_IAM_USER_ARN="${identity.accessArn}"' >> ~/.zshrc`);
        console.log(`   source ~/.zshrc`);
      }
    })
    .catch(error => {
      if (!arnOnly) {
        console.error('❌ Failed to get AWS identity');
      }
      process.exit(1);
    });
}

module.exports = { getCurrentAwsIdentity };