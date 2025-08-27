#!/usr/bin/env node

/**
 * Utility script to clear invalid refresh tokens
 * Run this if you're experiencing persistent "Invalid Refresh Token" errors
 */

import { CognitoAuth } from './dist/auth.js';
import { loadConfig } from './dist/config/index.js';

async function clearInvalidTokens() {
  try {
    console.log('🔧 Loading configuration...');
    const config = loadConfig();
    
    console.log('🔐 Initializing authentication service...');
    const auth = new CognitoAuth(config.cognito);
    
    console.log('🧹 Clearing any invalid refresh tokens...');
    auth.clearInvalidRefreshToken();
    
    console.log('✅ Invalid tokens cleared successfully!');
    console.log('');
    console.log('The MCP server will now re-authenticate with fresh credentials on the next request.');
    console.log('You should no longer see "Invalid Refresh Token" errors.');
    
  } catch (error) {
    console.error('❌ Failed to clear invalid tokens:', error);
    process.exit(1);
  }
}

// Run if this file is executed directly
if (import.meta.url === `file://${process.argv[1]}`) {
  clearInvalidTokens().catch(error => {
    console.error('💥 Script execution failed:', error);
    process.exit(1);
  });
}