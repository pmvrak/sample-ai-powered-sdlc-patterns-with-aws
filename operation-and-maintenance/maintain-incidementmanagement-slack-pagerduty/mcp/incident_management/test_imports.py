#!/usr/bin/env python3
"""
Test script to verify imports work correctly
"""

import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_enhanced_slack_imports():
    """Test if enhanced Slack integration imports work"""
    print("🧪 Testing enhanced Slack integration imports...")
    
    try:
        # Test basic imports first
        from integrations.slack_bot import SlackBot
        print("✅ SlackBot imported successfully")
        
        from integrations.interactive_slack_investigator import InteractiveSlackInvestigator
        print("✅ InteractiveSlackInvestigator imported successfully")
        
        from integrations.enhanced_slack_integration import EnhancedSlackIntegration
        print("✅ EnhancedSlackIntegration imported successfully")
        
        # Test initialization with mock credentials
        bot_token = "xoxb-test"
        signing_secret = "test-secret"
        
        enhanced_integration = EnhancedSlackIntegration(
            bot_token, signing_secret, None, None
        )
        print("✅ EnhancedSlackIntegration initialized successfully")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Initialization error: {e}")
        return False

if __name__ == "__main__":
    success = test_enhanced_slack_imports()
    if success:
        print("🎉 All imports working correctly!")
        sys.exit(0)
    else:
        print("💥 Import test failed!")
        sys.exit(1)