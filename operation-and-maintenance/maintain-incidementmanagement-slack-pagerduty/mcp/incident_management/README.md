# Incident Management System - Detailed Guide

This is the core incident management system that provides AI-powered detection, analysis, and automated remediation capabilities.

## System Capabilities

- **🔍 Real-Time Monitoring** - Continuous Splunk data analysis with AI pattern recognition
- **🧠 AI-Powered Analysis** - Root cause analysis using AWS Bedrock
- **📱 Rich Notifications** - Interactive Slack/Teams alerts with action buttons
- **🛠️ Smart Remediation** - Automated fix suggestions with safety checks
- **🔄 Integration Hub** - PagerDuty, monitoring tools, and ITSM systems

## 🔧 Configuration Guide

### Environment Files
- **`.env`** - Single configuration file for all components (created by you)
- **`.env.template`** - Template with all available options
- **`.env.local`** - Deprecated (use `.env` instead)
- **`.env.production`** - Deprecated (use `.env` instead)

### Splunk Setup
1. **Get Splunk Token**:
   - Log into your Splunk instance
   - Go to Settings → Tokens
   - Create a new token with search permissions
   - Copy the token to your `.env` file

2. **Verify Connection**:
   ```bash
   # Test Splunk connection
   curl -k -H "Authorization: Bearer YOUR_TOKEN" \
     "https://your-splunk-host:8089/services/search/jobs" \
     -d "search=search index=main | head 1"
   ```

### Slack Setup (Optional)
1. **Create Slack App**:
   - Go to https://api.slack.com/apps
   - Create new app for your workspace
   - Get Bot Token and Signing Secret

2. **Configure Permissions**:
   - Add `chat:write` scope
   - Add `channels:read` scope
   - Install app to workspace

3. **Test Integration**:
   ```bash
   # Test Slack notification
   curl -X POST http://localhost:8002/test-slack
   ```

### AWS Setup (For AI Features)
1. **Configure AWS CLI**:
   ```bash
   aws configure
   # Enter your Access Key ID, Secret Key, and Region
   ```

2. **Enable Bedrock**:
   - Go to AWS Bedrock console
   - Request access to Claude models
   - Wait for approval (usually instant)

## 🚀 Deployment Options

### Local Development
Perfect for testing and development:
```bash
cd operation-and-maintenance/maintain-incidentmanagement/mcp/incident_management
python run_api.py
```

### AWS ECS Production
For production deployment with auto-scaling:
```bash
cd operation-and-maintenance/maintain-incidentmanagement/mcp/incident_management/infrastructure
./deploy.sh -e prod -a YOUR_ACCOUNT_ID -r us-east-1
```

See the [Infrastructure README](infrastructure/README.md) for detailed deployment instructions.

## 📊 Key Features

### Incident Detection Rules
The system includes pre-configured detection rules:

```python
# High Error Rate Detection
{
    'name': 'High Error Rate',
    'query': 'search index=main error OR failed OR exception | head 20',
    'severity': 'HIGH',
    'threshold': 5,
    'check_interval': 300  # 5 minutes
}

# AWS CloudTrail Errors
{
    'name': 'AWS CloudTrail Errors', 
    'query': 'search index=main sourcetype=aws:cloudtrail errorCode!=success | head 10',
    'severity': 'MEDIUM',
    'threshold': 3,
    'check_interval': 600  # 10 minutes
}
```

### Customizing Detection
Edit `run_api.py` to add custom rules:
```python
# Add to detection_queries list
{
    'name': 'Custom Application Errors',
    'query': 'search index=main sourcetype=myapp:logs level=ERROR',
    'severity': 'HIGH',
    'threshold': 10,
    'check_interval': 180
}
```

## 🧪 Testing & Verification

### Health Checks
```bash
# System health
curl http://localhost:8002/health

# Detailed status
curl http://localhost:8002/system/info

# Current incidents
curl http://localhost:8002/incidents
```

### Generate Test Incident
```bash
# Simulate an incident
curl -X POST http://localhost:8002/simulate-incident \
  -H "Content-Type: application/json" \
  -d '{"type": "high_error_rate", "severity": "HIGH"}'
```

### Test Integrations
```bash
# Test Slack
curl -X POST http://localhost:8002/test-slack

# Test Splunk connection
curl http://localhost:8002/test-splunk

# Test AI analysis
curl -X POST http://localhost:8002/test-ai
```

## 🔍 Monitoring & Troubleshooting

### Common Issues

**1. Splunk Connection Failed**
```bash
# Check credentials
curl -k -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-splunk-host:8089/services/auth/login"

# Verify network access
telnet your-splunk-host 8089
```

**2. No Incidents Detected**
- Check if Splunk index has recent data
- Lower detection thresholds for testing
- Verify detection queries match your data format

**3. Slack Notifications Not Working**
- Verify bot token and signing secret
- Check Slack app permissions
- Test webhook URL manually

**4. AI Analysis Failing**
- Verify AWS credentials
- Check Bedrock model access
- Ensure proper IAM permissions

### Logs and Debugging
```bash
# View service logs
tail -f logs/incident_management.log

# Enable debug logging
export LOG_LEVEL=DEBUG
python run_api.py

# Check specific component logs
tail -f logs/splunk_mcp.log
tail -f logs/ai_analyzer.log
```

## 📚 API Reference

### Key Endpoints

```bash
# System Status
GET /health                    # Health check
GET /system/info              # Detailed system information

# Incident Management
GET /incidents                # List incidents
POST /incidents               # Create incident
GET /incidents/{id}           # Get specific incident
PUT /incidents/{id}           # Update incident

# Testing & Simulation
POST /test-slack              # Test Slack integration
POST /test-splunk             # Test Splunk connection
POST /simulate-incident       # Create test incident

# Integration
POST /webhooks/slack          # Slack webhook endpoint
GET /metrics                  # System metrics
```

### Example API Usage

**Create Incident:**
```bash
curl -X POST http://localhost:8002/incidents \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Database Connection Issues",
    "description": "Connection pool exhausted",
    "severity": "HIGH",
    "affected_systems": ["database", "api"]
  }'
```

**Get System Health:**
```bash
curl http://localhost:8002/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "splunk_connected": true,
  "incidents_detected": 5,
  "uptime_seconds": 3600
}
```

## 🔐 Security & Best Practices

### Security Checklist
- [ ] Use environment variables for secrets (never hardcode)
- [ ] Enable HTTPS in production
- [ ] Rotate tokens regularly
- [ ] Use least-privilege AWS IAM roles
- [ ] Enable audit logging
- [ ] Secure Slack webhook endpoints

### Production Considerations
- Use AWS Secrets Manager for production secrets
- Enable CloudWatch logging and monitoring
- Set up proper backup procedures
- Configure auto-scaling policies
- Implement proper error handling

## 📁 Project Structure

```
incident_management/
├── 🚀 run_api.py                     # Main entry point (START HERE)
├── 📋 requirements.txt               # Python dependencies
├── ⚙️ .env.template                  # Environment template
├── 🔧 core/                          # Core detection and analysis
│   ├── incident_detector.py          # AI-powered detection
│   ├── ai_analyzer.py                # Root cause analysis
│   └── automation_engine.py          # Automated remediation
├── 🔗 integrations/                  # External integrations
│   ├── real_splunk_mcp_client.py     # Splunk data access
│   ├── enhanced_slack_integration.py # Slack notifications
│   └── pagerduty_client.py           # PagerDuty integration
├── 🌐 api/                           # REST API components
├── 🏗️ infrastructure/               # AWS deployment (ECS)
│   ├── deploy.sh                     # Deployment script
│   └── README.md                     # Deployment guide
├── 📚 docs/                          # Documentation
├── 🧪 test/                          # Test suites
└── 📊 logs/                          # Application logs
```

## 🤝 Contributing

### Development Setup
```bash
# Set up development environment
git clone <repository>
cd operation-and-maintenance/maintain-incidentmanagement/mcp/incident_management
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run tests
python -m pytest test/

# Start development server
python run_api.py
```

### Adding Features
1. Create feature branch
2. Add tests for new functionality
3. Update documentation
4. Submit pull request

## 📞 Support & Help

### Getting Help
- **Quick Issues**: Check the [Troubleshooting](#-monitoring--troubleshooting) section
- **API Questions**: Visit http://localhost:8002/docs
- **Deployment Issues**: See [Infrastructure README](infrastructure/README.md)
- **Configuration Help**: Review the [Configuration Guide](#-configuration-guide)

### Useful Commands
```bash
# Start the system
python run_api.py

# Check system health
curl http://localhost:8002/health

# View logs
tail -f logs/incident_management.log

# Test integrations
curl -X POST http://localhost:8002/test-slack

# Stop the system
Ctrl+C (in terminal where system is running)
```

## 🎉 Next Steps

Once you have the system running:

1. **Configure Detection Rules** - Customize for your environment
2. **Set Up Slack Integration** - Enable rich notifications
3. **Deploy to AWS** - For production use
4. **Train Your Team** - On incident response workflows
5. **Monitor Performance** - Use built-in metrics and dashboards

---

**🚀 Ready to get started?** Run `python run_api.py` and visit http://localhost:8002/docs to explore the API!

For production deployment, see the [Infrastructure README](infrastructure/README.md).