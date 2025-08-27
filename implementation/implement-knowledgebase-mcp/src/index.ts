#!/usr/bin/env node

import { config as dotenvConfig } from 'dotenv';
import { loadConfig, validateConfig } from './config/index.js';
import { MCPServer } from './mcp-server.js';
import { ServerConfig } from './types.js';
import { log } from './secure-logger.js';
import { logger, logAuditEvent, measurePerformance } from './logger.js';

// Load environment variables from .env files
// Try multiple environment files in order of preference
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const projectRoot = join(__dirname, '..');

const envFiles = [
  '.env.development',
  '.env.local',
  '.env'
];

let envLoaded = false;
for (const envFile of envFiles) {
  // Try relative to current working directory first
  let result = dotenvConfig({ path: envFile });
  if (!result.error) {
    console.log(`🔧 Loaded environment variables from ${envFile}`);
    envLoaded = true;
    break;
  }

  // Try relative to project root
  const projectEnvPath = join(projectRoot, envFile);
  result = dotenvConfig({ path: projectEnvPath });
  if (!result.error) {
    console.log(`🔧 Loaded environment variables from ${projectEnvPath}`);
    envLoaded = true;
    break;
  }
}

if (!envLoaded) {
  console.log('⚠️  No .env file found, using system environment variables only');
}

/**
 * Server lifecycle manager with proper initialization, health checks, and shutdown handling
 */
class ServerLifecycleManager {
  private mcpServer: MCPServer | null = null;
  private isShuttingDown = false;
  private startupTime: Date | null = null;
  private healthCheckInterval: NodeJS.Timeout | null = null;

  /**
   * Initialize and start the server with comprehensive startup sequence
   */
  async start(): Promise<void> {
    return await measurePerformance('server.startup', async () => {
      try {
        logger.info('Starting Project KB MCP Server');
        console.log('🚀 Starting Project KB MCP Server...');
        this.startupTime = new Date();

        // Phase 1: Configuration validation
        logger.debug('Phase 1: Loading and validating configuration');
        console.log('📋 Phase 1: Loading and validating configuration...');
        const config = await this.loadAndValidateConfig();

        // Phase 2: Server initialization
        logger.debug('Phase 2: Initializing MCP Server');
        console.log('🔧 Phase 2: Initializing MCP Server...');
        this.mcpServer = new MCPServer(config);

        // Phase 3: Service initialization with connectivity checks
        logger.debug('Phase 3: Initializing services and connectivity');
        console.log('🔌 Phase 3: Initializing services and connectivity...');
        await this.mcpServer.initialize();

        // Phase 4: Health check setup
        logger.debug('Phase 4: Setting up health monitoring');
        console.log('❤️  Phase 4: Setting up health monitoring...');
        this.setupHealthChecks();

        // Phase 5: Signal handlers for graceful shutdown
        logger.debug('Phase 5: Setting up graceful shutdown handlers');
        console.log('🛡️  Phase 5: Setting up graceful shutdown handlers...');
        this.setupGracefulShutdown();

        // Phase 6: Start the server
        logger.debug('Phase 6: Starting MCP server');
        console.log('🌐 Phase 6: Starting MCP server...');
        await this.mcpServer.start();

        const startupDuration = Date.now() - this.startupTime.getTime();

        logger.info('Server started successfully', {
          startupDuration,
          status: this.mcpServer.getStatus()
        });

        logAuditEvent('server', 'startup', true, {
          details: {
            startupDuration,
            version: config.server.version,
            environment: process.env.NODE_ENV || 'development'
          }
        });

        console.log(`✅ Server started successfully in ${startupDuration}ms`);
        console.log(`📊 Server Status: ${JSON.stringify(this.mcpServer.getStatus(), null, 2)}`);

        // Keep the process alive to handle MCP requests
        console.log('🔄 Server is now ready to handle MCP requests...');
        console.log('🔄 Main startup sequence completed, entering wait state...');

      } catch (error) {
        logger.error('Server startup failed', {
          error: error instanceof Error ? error.message : String(error),
          stack: error instanceof Error ? error.stack : undefined
        });

        logAuditEvent('server', 'startup', false, {
          details: {
            error: error instanceof Error ? error.message : String(error)
          }
        });

        console.error('❌ Server startup failed:', error);
        await this.shutdown(1);
      }
    });
  }

  /**
   * Load and validate configuration with detailed error reporting
   */
  private async loadAndValidateConfig(): Promise<ServerConfig> {
    try {
      const config: ServerConfig = loadConfig();

      console.log('🔍 Validating configuration...');
      validateConfig(config);

      console.log('📝 Configuration summary:');
      console.log(`  Server: ${config.server.name} v${config.server.version}`);
      if (config.openSearch) {
        console.log(`  OpenSearch: ${config.openSearch.endpoint}`);
        console.log(`  Index Prefix: ${config.openSearch.indexPrefix}`);
      }
      if (config.bedrock) {
        console.log(`  Bedrock KB: ${config.bedrock.knowledgeBaseId}`);
        console.log(`  Bedrock Region: ${config.bedrock.region}`);
      }
      console.log(`  Cognito Region: ${config.cognito.region}`);

      return config;

    } catch (error) {
      console.error('❌ Configuration validation failed:', error);
      throw new Error(`Configuration error: ${error instanceof Error ? error.message : error}`);
    }
  }

  /**
   * Set up periodic health checks with proactive authentication refresh
   */
  private setupHealthChecks(): void {
    if (!this.mcpServer) return;

    // Perform health check every 30 seconds
    this.healthCheckInterval = setInterval(async () => {
      try {
        const status = this.mcpServer!.getStatus();

        // Log health status periodically (every 5 minutes)
        const now = Date.now();
        if (now % (5 * 60 * 1000) < 30000) { // Within 30s of 5-minute mark
          const authService = this.mcpServer!.getAuthService();
          const authStatus = authService.getAuthenticationStatus();

          console.log(`💓 Health Check - Uptime: ${Math.floor(status.uptime)}s, Active Project: ${status.activeProject || 'none'}`);
          console.log(`   User: ${authStatus.username || 'unknown'}`);
          console.log(`   Token: ${authStatus.authenticated ? '✅' : '❌'} (expires: ${authStatus.tokenExpiry?.toISOString() || 'unknown'})`);
          console.log(`   Refresh Token: ${authStatus.refreshTokenValid ? '✅' : '❌'} (expires: ${authStatus.refreshTokenExpiry?.toISOString() || 'unknown'})`);
          console.log(`   AWS Creds: ${authStatus.awsCredentialsValid ? '✅' : '❌'} (expires: ${authStatus.awsCredentialsExpiry?.toISOString() || 'unknown'})`);

          if (authStatus.tokenNearExpiry || authStatus.awsCredentialsNearExpiry || authStatus.refreshTokenNearExpiry) {
            const warnings = [];
            if (authStatus.tokenNearExpiry) warnings.push('access token');
            if (authStatus.refreshTokenNearExpiry) warnings.push('refresh token');
            if (authStatus.awsCredentialsNearExpiry) warnings.push('AWS credentials');
            console.log(`   ⚠️  ${warnings.join(', ')} near expiry - will refresh proactively`);
          }
        }

        // Check for critical issues
        if (!status.initialized) {
          console.warn('⚠️  Health Check Warning: Server not properly initialized');
        }

        // Proactively refresh authentication if lost or near expiry
        const authService = this.mcpServer!.getAuthService();
        const authStatus = authService.getAuthenticationStatus();

        if (!status.authenticated) {
          console.warn('⚠️  Health Check Warning: Authentication lost, attempting refresh...');
          try {
            await this.refreshAuthentication();
            console.log('✅ Authentication successfully refreshed');
          } catch (error) {
            // Check if this is a network error
            if (error instanceof Error && (
              error.message.includes('ENOTFOUND') ||
              error.message.includes('DNS_RESOLUTION_FAILED') ||
              error.message.includes('getaddrinfo')
            )) {
              console.warn('⚠️  Network connectivity issue during authentication refresh, will retry later');
            } else {
              console.error('❌ Failed to refresh authentication:', error);
            }
            // Continue running - auth will be retried on next tool call or health check
          }
        } else if (authStatus.tokenNearExpiry || authStatus.awsCredentialsNearExpiry || authStatus.refreshTokenNearExpiry) {
          const warnings = [];
          if (authStatus.tokenNearExpiry) warnings.push('access token');
          if (authStatus.refreshTokenNearExpiry) warnings.push('refresh token');
          if (authStatus.awsCredentialsNearExpiry) warnings.push('AWS credentials');

          console.log(`🔄 ${warnings.join(', ')} near expiry, proactively refreshing...`);

          try {
            await this.refreshAuthentication();
            console.log('✅ Authentication proactively refreshed');
          } catch (error) {
            // Check if this is a network error
            if (error instanceof Error && (
              error.message.includes('ENOTFOUND') ||
              error.message.includes('DNS_RESOLUTION_FAILED') ||
              error.message.includes('getaddrinfo')
            )) {
              console.warn('⚠️  Network connectivity issue during proactive refresh, will retry later');
            } else {
              console.warn('⚠️  Proactive authentication refresh failed:', error);
            }
            // Continue running - credentials may still be valid for now
          }
        } else if (!authStatus.refreshTokenValid) {
          console.warn('⚠️  Refresh token is invalid or expired, will re-authenticate on next tool call');
          // Don't attempt refresh here as it will fail - let it happen on next tool call
        }

      } catch (error) {
        console.error('❌ Health check failed:', error);
      }
    }, 30000); // 30 seconds
  }

  /**
   * Proactively refresh authentication and update backend credentials
   */
  private async refreshAuthentication(): Promise<void> {
    if (!this.mcpServer) {
      throw new Error('MCP Server not initialized');
    }

    try {
      // Ensure we have valid tokens and AWS credentials (this will refresh if needed)
      const authService = this.mcpServer.getAuthService();
      await authService.ensureValidToken();
      const awsCredentials = await authService.ensureValidAWSCredentials();

      // Update backend credentials
      await this.mcpServer.updateBackendCredentials(awsCredentials);

      console.log('🔄 Backend credentials updated with fresh authentication');

    } catch (error) {
      throw new Error(`Authentication refresh failed: ${error instanceof Error ? error.message : error}`);
    }
  }

  /**
   * Set up graceful shutdown handlers for various signals
   */
  private setupGracefulShutdown(): void {
    // Handle SIGINT (Ctrl+C)
    process.on('SIGINT', async () => {
      console.log('\n🛑 Received SIGINT (Ctrl+C), initiating graceful shutdown...');
      await this.shutdown(0);
    });

    // Handle SIGTERM (process termination)
    process.on('SIGTERM', async () => {
      console.log('🛑 Received SIGTERM, initiating graceful shutdown...');
      await this.shutdown(0);
    });

    // Handle uncaught exceptions
    process.on('uncaughtException', async (error) => {
      console.error('💥 Uncaught Exception:', error);
      await this.shutdown(1);
    });

    // Handle unhandled promise rejections
    process.on('unhandledRejection', async (reason, promise) => {
      console.error('💥 Unhandled Rejection at:', promise, 'reason:', reason);
      await this.shutdown(1);
    });
  }

  /**
   * Perform graceful shutdown with cleanup
   */
  private async shutdown(exitCode: number = 0): Promise<void> {
    if (this.isShuttingDown) {
      logger.debug('Shutdown already in progress');
      console.log('⏳ Shutdown already in progress...');
      return;
    }

    this.isShuttingDown = true;
    logger.info('Initiating graceful shutdown sequence', { exitCode });
    console.log('🔄 Initiating graceful shutdown sequence...');

    try {
      // Stop health checks
      if (this.healthCheckInterval) {
        clearInterval(this.healthCheckInterval);
        this.healthCheckInterval = null;
        logger.debug('Health monitoring stopped');
        console.log('✅ Health monitoring stopped');
      }

      // Shutdown MCP server
      if (this.mcpServer) {
        logger.debug('Shutting down MCP server');
        console.log('🛑 Shutting down MCP server...');
        await this.mcpServer.shutdown();
        logger.debug('MCP server shutdown complete');
        console.log('✅ MCP server shutdown complete');
      }

      // Calculate uptime
      let uptime = 0;
      if (this.startupTime) {
        uptime = Date.now() - this.startupTime.getTime();
        console.log(`📊 Server uptime: ${Math.floor(uptime / 1000)}s`);
      }

      logger.info('Graceful shutdown completed', {
        exitCode,
        uptime: Math.floor(uptime / 1000)
      });

      logAuditEvent('server', 'shutdown', true, {
        details: {
          exitCode,
          uptime: Math.floor(uptime / 1000),
          graceful: true
        }
      });

      console.log('✅ Graceful shutdown completed');

    } catch (error) {
      logger.error('Error during shutdown', {
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
        exitCode
      });

      logAuditEvent('server', 'shutdown', false, {
        details: {
          error: error instanceof Error ? error.message : String(error),
          exitCode,
          graceful: false
        }
      });

      console.error('❌ Error during shutdown:', error);
      exitCode = 1;
    }

    process.exit(exitCode);
  }

  /**
   * Get current server health status
   */
  getHealthStatus(): {
    status: 'healthy' | 'unhealthy' | 'starting' | 'shutting_down';
    uptime: number;
    startupTime: string | null;
    serverStatus?: any;
  } {
    if (this.isShuttingDown) {
      return {
        status: 'shutting_down',
        uptime: 0,
        startupTime: this.startupTime?.toISOString() || null
      };
    }

    if (!this.mcpServer || !this.startupTime) {
      return {
        status: 'starting',
        uptime: 0,
        startupTime: null
      };
    }

    try {
      const serverStatus = this.mcpServer.getStatus();
      const uptime = Date.now() - this.startupTime.getTime();

      return {
        status: serverStatus.initialized && serverStatus.authenticated ? 'healthy' : 'unhealthy',
        uptime: Math.floor(uptime / 1000),
        startupTime: this.startupTime.toISOString(),
        serverStatus
      };
    } catch (error) {
      return {
        status: 'unhealthy',
        uptime: 0,
        startupTime: this.startupTime?.toISOString() || null
      };
    }
  }
}

/**
 * Main entry point
 */
async function main() {
  const lifecycleManager = new ServerLifecycleManager();
  await lifecycleManager.start();

  // Keep the process alive to handle MCP requests
  // The MCP server should handle this via stdio transport, but we'll ensure it stays alive
  console.log('🔄 Main function: Entering infinite wait to keep process alive...');
  await new Promise(() => { }); // Wait indefinitely
}

// Start the server if this file is run directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    // SECURITY: Use secure logging with sanitized error data
    log.error('Fatal error during server startup', {
      error: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined
    });
    process.exit(1);
  });
}