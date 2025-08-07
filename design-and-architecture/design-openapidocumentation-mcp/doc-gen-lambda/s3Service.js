const { S3Client, PutObjectCommand, GetObjectCommand } = require('@aws-sdk/client-s3');

class DocGeneratorS3Service {
  constructor() {
    this.s3Client = new S3Client({ 
      region: process.env.AWS_REGION || process.env.BEDROCK_REGION || 'us-east-1' 
    });
    this.bucketName = process.env.BUCKET_NAME;
  }

  /**
   * Generate S3 key for documentation storage
   * @param {string} userId - User identifier
   * @param {string} sessionId - Session identifier
   * @param {string} specId - Specification identifier
   * @param {string} type - Type of documentation
   * @returns {string} S3 key
   */
  generateDocKey(userId, sessionId, specId, type = 'docs') {
    return `sessions/${userId}/${sessionId}/openapi-specs/${specId}-${type}.json`;
  }

  /**
   * Store generated documentation in S3
   * @param {string} userId - User identifier
   * @param {string} sessionId - Session identifier
   * @param {string} specId - Specification identifier
   * @param {Object} documentation - Generated documentation
   * @param {string} docType - Type of documentation ('comprehensive', 'basic', etc.)
   * @returns {Promise<Object>} Result with S3 key and success status
   */
  async storeDocumentation(userId, sessionId, specId, documentation, docType = 'comprehensive') {
    try {
      const key = this.generateDocKey(userId, sessionId, specId, 'docs');
      
      const docData = {
        type: docType,
        documentation: documentation,
        specId: specId,
        generatedAt: new Date().toISOString(),
        userId: userId,
        sessionId: sessionId
      };
      
      const command = new PutObjectCommand({
        Bucket: this.bucketName,
        Key: key,
        Body: JSON.stringify(docData, null, 2),
        ContentType: 'application/json',
        Metadata: {
          userId: userId,
          sessionId: sessionId,
          specId: specId,
          docType: docType,
          createdAt: new Date().toISOString()
        }
      });

      await this.s3Client.send(command);
      
      console.log(`Documentation stored in S3: ${key}`);
      return { success: true, s3Key: key };
    } catch (error) {
      console.error('Error storing documentation in S3:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Retrieve documentation from S3
   * @param {string} userId - User identifier
   * @param {string} sessionId - Session identifier
   * @param {string} specId - Specification identifier
   * @returns {Promise<Object>} Documentation data or null if not found
   */
  async getDocumentation(userId, sessionId, specId) {
    try {
      const key = this.generateDocKey(userId, sessionId, specId, 'docs');
      
      const command = new GetObjectCommand({
        Bucket: this.bucketName,
        Key: key
      });

      const response = await this.s3Client.send(command);
      const docData = await response.Body.transformToString();
      
      return JSON.parse(docData);
    } catch (error) {
      if (error.name === 'NoSuchKey') {
        console.log(`Documentation not found in S3: ${specId}`);
        return null;
      }
      console.error('Error retrieving documentation from S3:', error);
      throw error;
    }
  }
}

module.exports = new DocGeneratorS3Service();