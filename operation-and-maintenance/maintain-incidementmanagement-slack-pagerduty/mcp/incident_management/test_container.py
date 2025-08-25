#!/usr/bin/env python3
"""
Container startup test to verify the environment is ready
"""

import os
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_python_environment():
    """Test Python environment and imports"""
    logger.info("🐍 Testing Python environment...")
    
    # Test Python version
    if sys.version_info < (3, 8):
        logger.error("❌ Python 3.8+ required")
        return False
    
    logger.info(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    
    # Test critical imports
    try:
        import fastapi
        import uvicorn
        import boto3
        import slack_sdk
        logger.info("✅ Critical imports successful")
        return True
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return False

def test_file_structure():
    """Test that required files exist"""
    logger.info("📁 Testing file structure...")
    
    # Core required files (always needed)
    core_files = [
        "run_api.py",
        "start_services.sh",
        "requirements.txt"
    ]
    
    missing_files = []
    for file_path in core_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        logger.error(f"❌ Missing core files: {missing_files}")
        return False
    
    # Check for environment configuration (either .env.production or AWS environment)
    has_env_file = Path('.env.production').exists()
    has_aws_env = os.getenv('AWS_REGION') is not None
    
    if not has_env_file and not has_aws_env:
        logger.error("❌ No environment configuration found (.env.production or AWS environment)")
        return False
    
    if has_env_file:
        logger.info("✅ All required files present (with .env.production)")
    else:
        logger.info("✅ All required files present (using AWS Secrets Manager)")
    
    return True

def test_environment_variables():
    """Test that critical environment variables are available"""
    logger.info("🔧 Testing environment variables...")
    
    # Check if we're in ECS (secrets will be loaded from AWS Secrets Manager)
    aws_region = os.getenv('AWS_REGION')
    if aws_region:
        logger.info(f"✅ Running in AWS environment (region: {aws_region})")
        
        # In ECS, these should be available as secrets
        expected_secrets = ['SLACK_BOT_TOKEN', 'SLACK_SIGNING_SECRET', 'JWT_SECRET']
        available_secrets = []
        
        for secret in expected_secrets:
            if os.getenv(secret):
                available_secrets.append(secret)
        
        if available_secrets:
            logger.info(f"✅ AWS secrets available: {len(available_secrets)}/{len(expected_secrets)}")
        else:
            logger.info("ℹ️ AWS secrets will be loaded at runtime")
        
        return True
    
    # For local testing, check if .env.production exists
    if Path('.env.production').exists():
        logger.info("✅ Local environment file found")
        return True
    
    logger.warning("⚠️ No environment configuration found, but continuing...")
    return True

def test_permissions():
    """Test file permissions"""
    logger.info("🔐 Testing file permissions...")
    
    # Check if start_services.sh is executable
    start_script = Path("start_services.sh")
    if start_script.exists() and os.access(start_script, os.X_OK):
        logger.info("✅ Start script is executable")
        return True
    else:
        logger.error("❌ Start script is not executable")
        return False

def main():
    """Run all container tests"""
    logger.info("🚀 Starting container environment tests...")
    
    tests = [
        ("Python Environment", test_python_environment),
        ("File Structure", test_file_structure),
        ("Environment Variables", test_environment_variables),
        ("File Permissions", test_permissions)
    ]
    
    failed_tests = []
    
    for test_name, test_func in tests:
        try:
            if not test_func():
                failed_tests.append(test_name)
        except Exception as e:
            logger.error(f"❌ {test_name} test failed with exception: {e}")
            failed_tests.append(test_name)
    
    if failed_tests:
        logger.error(f"💥 Container tests failed: {', '.join(failed_tests)}")
        sys.exit(1)
    else:
        logger.info("🎉 All container tests passed! Starting services...")
        sys.exit(0)

if __name__ == "__main__":
    main()