#!/usr/bin/env node

const { Client } = require('@opensearch-project/opensearch');
const { AwsSigv4Signer } = require('@opensearch-project/opensearch/aws');
const { defaultProvider } = require('@aws-sdk/credential-provider-node');
const { CONFIG } = require('./lib/config');
const { execSync } = require('child_process');

async function createIndex() {
  try {
    console.log('Creating OpenSearch vector index...');
    
    // Get the collection endpoint from CloudFormation outputs
    const cfnOutput = execSync('aws cloudformation describe-stacks --stack-name OpenSearchStack --query "Stacks[0].Outputs[?OutputKey==\'CollectionArn\'].OutputValue" --output text').toString().trim();
    
    // Extract collection ID from ARN
    const collectionId = cfnOutput.split('/').pop();
    const region = process.env.AWS_REGION || process.env.CDK_DEFAULT_REGION || 'us-east-1';
    const endpoint = `https://${collectionId}.${region}.aoss.amazonaws.com`;
    
    console.log(`Collection ID: ${collectionId}`);
    console.log(`Endpoint: ${endpoint}`);
    
    // Create OpenSearch client with AWS Sigv4 authentication
    const client = new Client({
      node: endpoint,
      ...AwsSigv4Signer({
        region: region,
        service: 'aoss',
        getCredentials: () => {
          const credentialsProvider = defaultProvider();
          return credentialsProvider();
        },
      }),
    });
    
    // Define index mapping with vector field
    const indexName = CONFIG.indexName;
    console.log(`Creating index: ${indexName}`);
    
    // Create a raw HTTP request to create the index with FAISS engine
    // This is necessary because the OpenSearch client doesn't directly support all engine types
    const createIndexRequest = {
      method: 'PUT',
      path: `/${indexName}`,
      body: JSON.stringify({
        settings: {
          index: {
            knn: true,
            "knn.algo_param.ef_search": 512
          }
        },
        mappings: {
          properties: {
            vector: {
              type: "knn_vector",
              dimension: 1024,
              method: {
                name: "hnsw",
                engine: "faiss",
                space_type: "l2"
              }
            },
            text: {
              type: "text"
            },
            metadata: {
              type: "text"
            }
          }
        }
      })
    };
    
    // Check if index exists
    const indexExists = await client.indices.exists({ index: indexName });
    
    if (indexExists.body) {
      console.log(`Index ${indexName} already exists. Deleting and recreating with FAISS engine...`);
      
      // Delete the existing index
      await client.indices.delete({ index: indexName });
      console.log(`Index ${indexName} deleted.`);
      
      // Create the index with FAISS engine using raw request
      const response = await client.transport.request(createIndexRequest);
      console.log('Index creation response:', JSON.stringify(response.body, null, 2));
      console.log(`Index ${indexName} created successfully with FAISS engine!`);
    } else {
      // Create the index with FAISS engine using raw request
      const response = await client.transport.request(createIndexRequest);
      console.log('Index creation response:', JSON.stringify(response.body, null, 2));
      console.log(`Index ${indexName} created successfully with FAISS engine!`);
    }
    
    return true;
  } catch (error) {
    console.error('Error creating index:', error);
    return false;
  }
}

// Execute the function
createIndex()
  .then((success) => {
    if (success) {
      console.log('Vector index creation completed successfully.');
      process.exit(0);
    } else {
      console.error('Vector index creation failed.');
      process.exit(1);
    }
  })
  .catch((error) => {
    console.error('Unhandled error:', error);
    process.exit(1);
  });