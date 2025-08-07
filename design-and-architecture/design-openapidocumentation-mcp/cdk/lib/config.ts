export const CONFIG = {
    collectionName: process.env.OPENSEARCH_COLLECTION_NAME || 'openapi-kb',
    indexName: process.env.OPENSEARCH_INDEX_NAME || 'openapi-index',
    // Allow users to specify their IAM ARN via environment variable
    // If not provided, defaults to account root (less secure but works)
    iamUserArn: process.env.CDK_IAM_USER_ARN || 
                (process.env.CDK_DEFAULT_ACCOUNT ? `arn:aws:iam::${process.env.CDK_DEFAULT_ACCOUNT}:root` : 'arn:aws:iam::ACCOUNT_ID:root'),
    accountId: process.env.CDK_DEFAULT_ACCOUNT || 'ACCOUNT_ID'
};