const { S3Client, PutObjectCommand, GetObjectCommand, ListObjectsV2Command } = require('@aws-sdk/client-s3');

class DomainAnalyzerS3Service {
  constructor() {
    this.s3Client = new S3Client({ 
      region: process.env.AWS_REGION || process.env.BEDROCK_REGION || 'us-east-1' 
    });
    this.bucketName = process.env.BUCKET_NAME;
  }

  /**
   * Generate S3 key for domain analysis storage
   * @param {string} userId - User identifier (preferably email)
   * @param {string} sessionId - Session identifier
   * @param {string} fileName - File name
   * @param {string} type - Type of file ('analysis', 'image', 'context', 'diagram')
   * @returns {string} S3 key
   */
  generateAnalysisKey(userId, sessionId, fileName, type = 'analysis') {
    // Use email-safe folder name (replace @ and . with underscores for S3 compatibility)
    const safeFolderName = userId.replace(/@/g, '_at_').replace(/\./g, '_');
    
    if (type === 'image') {
      // Use the same image storage location as the main backend
      return `sessions/${safeFolderName}/${sessionId}/images/${fileName}`;
    } else {
      // Store analysis results in the main analysis.json file location
      return `sessions/${safeFolderName}/${sessionId}/analysis/${fileName}`;
    }
  }

  /**
   * Store domain analysis result in consolidated analysis file
   * This method updates the main analysis.json file instead of creating separate files
   * @param {string} userId - User identifier (preferably email)
   * @param {string} sessionId - Session identifier
   * @param {string} analysisResult - Analysis result text
   * @param {string} analysisType - Type of analysis ('domain', 'business', 'diagram')
   * @returns {Promise<Object>} Result with S3 key and success status
   */
  async storeAnalysis(userId, sessionId, analysisResult, analysisType = 'domain') {
    try {
      // Get existing analysis data first
      let existingAnalysis = await this.getSessionAnalysis(userId, sessionId);
      
      if (!existingAnalysis) {
        // Create new analysis structure
        existingAnalysis = {
          userId: userId,
          sessionId: sessionId,
          createdAt: new Date().toISOString()
        };
      }
      
      // Update the specific analysis type
      if (analysisType === 'domain') {
        existingAnalysis.domainAnalysis = analysisResult;
      } else if (analysisType === 'business') {
        existingAnalysis.businessContextAnalysis = analysisResult;
        existingAnalysis.boundedContextAnalysis = analysisResult; // Alias for compatibility
      } else if (analysisType === 'diagram') {
        existingAnalysis.asciiDiagram = analysisResult;
      }
      
      // Store the consolidated analysis
      const result = await this.updateSessionAnalysis(userId, sessionId, existingAnalysis);
      
      console.log(`Domain analysis (${analysisType}) stored in consolidated file: ${result.s3Key}`);
      return result;
    } catch (error) {
      console.error('Error storing analysis in consolidated file:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Store uploaded image in S3
   * @param {string} userId - User identifier (preferably email)
   * @param {string} sessionId - Session identifier
   * @param {Buffer} imageBuffer - Image buffer
   * @param {string} contentType - Image content type
   * @returns {Promise<Object>} Result with S3 key and success status
   */
  async storeImage(userId, sessionId, imageBuffer, contentType = 'image/jpeg') {
    try {
      const timestamp = Date.now();
      const extension = contentType.includes('png') ? 'png' : 'jpg';
      const fileName = `domain-model-${timestamp}.${extension}`;
      const key = this.generateAnalysisKey(userId, sessionId, fileName, 'image');
      
      const command = new PutObjectCommand({
        Bucket: this.bucketName,
        Key: key,
        Body: imageBuffer,
        ContentType: contentType,
        Metadata: {
          userId: userId,
          sessionId: sessionId,
          uploadedAt: new Date().toISOString(),
          type: 'domain-model-image'
        }
      });

      await this.s3Client.send(command);
      
      console.log(`Image stored in S3: ${key}`);
      return { success: true, s3Key: key, fileName: fileName };
    } catch (error) {
      console.error('Error storing image in S3:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Update session metadata
   * @param {string} userId - User identifier (preferably email)
   * @param {string} sessionId - Session identifier
   * @param {Object} metadata - Session metadata
   * @returns {Promise<Object>} Result with success status
   */
  async updateSessionMetadata(userId, sessionId, metadata) {
    try {
      // Use email-safe folder name (replace @ and . with underscores for S3 compatibility)
      const safeFolderName = userId.replace(/@/g, '_at_').replace(/\./g, '_');
      const key = `sessions/${safeFolderName}/${sessionId}/metadata.json`;
      
      const command = new PutObjectCommand({
        Bucket: this.bucketName,
        Key: key,
        Body: JSON.stringify({
          ...metadata,
          userId: userId,
          sessionId: sessionId,
          updatedAt: new Date().toISOString()
        }, null, 2),
        ContentType: 'application/json'
      });

      await this.s3Client.send(command);
      
      console.log(`Session metadata updated in S3: ${key}`);
      return { success: true, s3Key: key };
    } catch (error) {
      console.error('Error updating session metadata in S3:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Get the main analysis data for a session (consolidated approach)
   * @param {string} userId - User identifier (preferably email)
   * @param {string} sessionId - Session identifier
   * @returns {Promise<Object>} Analysis data or null if not found
   */
  async getSessionAnalysis(userId, sessionId) {
    try {
      // Use email-safe folder name (replace @ and . with underscores for S3 compatibility)
      const safeFolderName = userId.replace(/@/g, '_at_').replace(/\./g, '_');
      const key = `sessions/${safeFolderName}/${sessionId}/analysis.json`;
      
      const command = new GetObjectCommand({
        Bucket: this.bucketName,
        Key: key
      });

      const response = await this.s3Client.send(command);
      const analysisData = await response.Body.transformToString();
      
      return JSON.parse(analysisData);
    } catch (error) {
      if (error.name === 'NoSuchKey') {
        console.log(`Analysis not found in S3 for session: ${sessionId}`);
        return null;
      }
      console.error('Error retrieving analysis from S3:', error);
      throw error;
    }
  }

  /**
   * Update the main analysis data for a session (consolidated approach)
   * @param {string} userId - User identifier (preferably email)
   * @param {string} sessionId - Session identifier
   * @param {Object} analysisData - Complete analysis data to store
   * @returns {Promise<Object>} Result with success status
   */
  async updateSessionAnalysis(userId, sessionId, analysisData) {
    try {
      // Use email-safe folder name (replace @ and . with underscores for S3 compatibility)
      const safeFolderName = userId.replace(/@/g, '_at_').replace(/\./g, '_');
      const key = `sessions/${safeFolderName}/${sessionId}/analysis.json`;
      
      const analysisPayload = {
        ...analysisData,
        userId: userId,
        sessionId: sessionId,
        updatedAt: new Date().toISOString()
      };
      
      const command = new PutObjectCommand({
        Bucket: this.bucketName,
        Key: key,
        Body: JSON.stringify(analysisPayload, null, 2),
        ContentType: 'application/json',
        Metadata: {
          userId: userId,
          sessionId: sessionId,
          updatedAt: new Date().toISOString(),
          type: 'consolidated-analysis'
        }
      });

      await this.s3Client.send(command);
      
      console.log(`Consolidated analysis updated in S3: ${key}`);
      return { success: true, s3Key: key };
    } catch (error) {
      console.error('Error updating consolidated analysis in S3:', error);
      return { success: false, error: error.message };
    }
  }
}

module.exports = new DomainAnalyzerS3Service();