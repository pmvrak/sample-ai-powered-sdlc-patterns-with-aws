// Jest setup file for global test configuration
import { logger } from '../utils/logger';

// Suppress logs during testing
logger.silent = true;

// Set test environment variables
process.env['NODE_ENV'] = 'test';
process.env['LOG_LEVEL'] = 'error';