# Intelligent Incident Management System Documentation

Welcome to the comprehensive documentation for the Intelligent Incident Management System. This system extends the existing Splunk MCP server with AI-powered incident detection, routing, and automated remediation capabilities.

## 📚 Available Documentation

### Core Documentation
- **[Main README](../README.md)** - System overview and setup guide
- **[API Documentation](../api/README.md)** - REST API reference
- **[Deployment Guide](../infrastructure/DEPLOYMENT_README.md)** - AWS deployment instructions
- **[Slack Setup Guide](../SLACK_SETUP_GUIDE.md)** - Chat integration setup

### Detailed Guides
- **[Administrator Guide](admin-guide.md)** - System configuration and maintenance
- **[API Documentation](api-documentation.md)** - Comprehensive REST API reference
- **[Chat Commands](chat-commands.md)** - Slack/Teams command reference
- **[Dashboard Guide](dashboard-guide.md)** - Web dashboard usage guide

### Specifications
- **[Requirements](../../../.kiro/specs/intelligent-incident-management/requirements.md)** - System requirements
- **[Design Document](../../../.kiro/specs/intelligent-incident-management/design.md)** - Architecture and design

## 🚀 Quick Links

- **[Getting Started](../README.md)** - New to the system? Start here!
- **[Chat Commands](chat-commands.md)** - `/incident help` in Slack/Teams
- **[API Examples](api-documentation.md#examples)** - Common API usage patterns
- **[Configuration](admin-guide.md#configuration-management)** - System setup and configuration

## System Overview

The Intelligent Incident Management System provides AI-powered incident detection, analysis, and automated remediation with comprehensive chat integration.

### Key Capabilities
- **🔍 Automated Detection** - AI-powered incident detection from Splunk logs
- **🧠 Smart Analysis** - Root cause analysis using AWS Bedrock
- **💬 Chat Integration** - Native Slack/Teams integration with interactive commands
- **🤖 Automated Remediation** - AI-suggested fixes with safety checks
- **📊 Real-time Monitoring** - Live incident tracking and team metrics

## Quick Configuration

```bash
# Required Environment Variables
SPLUNK_HOST=your-splunk-host
SPLUNK_TOKEN=your-splunk-token
AWS_REGION=us-west-2

# Optional Integrations
SLACK_BOT_TOKEN=xoxb-your-slack-token
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
PAGERDUTY_API_KEY=your-pagerduty-token
```

## Documentation Status

📝 **Note**: Some documentation describes planned features that may not be fully implemented yet. For current functionality:

- ✅ **Core System**: Basic incident detection and management (see main README)
- ✅ **API**: REST API endpoints (see API README)  
- ✅ **Slack Integration**: Basic notifications and commands (see Slack setup guide)
- 🚧 **Advanced Features**: Chat commands, dashboard, and automation (in development)

## Support

For help with the system:
1. **System Issues**: Check the main [README](../README.md) troubleshooting section
2. **API Questions**: Visit http://localhost:8002/docs for interactive documentation
3. **Configuration Help**: Review the setup guides in the main documentation

---

*Documentation for the Intelligent Incident Management System*