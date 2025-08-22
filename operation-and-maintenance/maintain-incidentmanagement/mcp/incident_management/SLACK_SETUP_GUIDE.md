# Slack Integration Setup Guide

## Quick Setup (5 minutes)

### Step 1: Create Slack App
1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. App Name: `Incident Management Bot`
4. Choose your workspace
5. Click **"Create App"**

### Step 2: Enable Incoming Webhooks
1. In your app settings, go to **"Incoming Webhooks"**
2. Toggle **"Activate Incoming Webhooks"** to **On**
3. Click **"Add New Webhook to Workspace"**
4. Choose the channel where you want incident notifications (e.g., `#incidents`)
5. Click **"Allow"**
6. **Copy the Webhook URL** (starts with `https://hooks.slack.com/services/...`)

### Step 3: Configure Environment
```bash
# Set the webhook URL as an environment variable
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

### Step 4: Test Integration
```bash
cd operation-and-maintenance/maintain-incidentmanagement/mcp/incident_management
source venv/bin/activate
python slack_integration.py
```

## Advanced Setup (Optional)

### Add Bot User (for interactive features)
1. Go to **"OAuth & Permissions"**
2. Add these Bot Token Scopes:
   - `chat:write`
   - `chat:write.public`
   - `channels:read`
   - `users:read`
3. Click **"Install to Workspace"**
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

### Add Slash Commands
1. Go to **"Slash Commands"**
2. Click **"Create New Command"**
3. Command: `/incident`
4. Request URL: `https://your-domain.com/slack/commands`
5. Description: `Manage incidents`
6. Usage Hint: `list | status | help`

### Add Interactive Components
1. Go to **"Interactivity & Shortcuts"**
2. Toggle **"Interactivity"** to **On**
3. Request URL: `https://your-domain.com/slack/interactive`

## Environment Variables

```bash
# Required for basic notifications
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."

# Optional for advanced features
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_SIGNING_SECRET="your-signing-secret"
export SLACK_CHANNEL="#incidents"
```

## Testing

### Test with Real Incidents
The integration will automatically send notifications for:
- ✅ **AWS CloudTrail Errors** (currently detecting 10 events)
- ✅ **High Error Rates** (currently detecting 20 events)
- ✅ **Performance Issues**
- ✅ **Security Events**

### Message Format
Each incident notification includes:
- 🚨 **Severity indicator** (High/Medium/Low)
- 📊 **Event count** and affected systems
- 📝 **Sample events** from Splunk
- 🔘 **Action buttons** (View, Acknowledge, Escalate)
- ⏰ **Timestamp** and detection query

### System Status Updates
Periodic status updates include:
- 💚 **System health** (Healthy/Warning/Critical)
- 📈 **Total events** processed
- 🚨 **Recent incident count**
- 📊 **Active indexes** and event counts

## Integration with Production API

The Slack integration works with your live production API:
- **Real incidents** from your Splunk data
- **Live system stats** (128,118+ events)
- **Continuous monitoring** (60-second cycles)
- **Rich formatting** with action buttons

## Troubleshooting

### Common Issues
1. **"Invalid webhook URL"**
   - Verify the webhook URL is correct
   - Check that the Slack app has webhook permissions

2. **"Channel not found"**
   - Ensure the bot is added to the target channel
   - Use channel ID instead of name if needed

3. **"No notifications received"**
   - Check that incidents are being detected: `curl http://localhost:8002/incidents`
   - Verify webhook URL environment variable is set

### Debug Mode
```bash
# Enable debug logging
export SLACK_DEBUG=true
python slack_integration.py
```

## Next Steps

Once basic integration is working:
1. **Add to Production API** - Integrate with the live incident detection
2. **Set up Alerts** - Configure for high-severity incidents only
3. **Add Automation** - Connect action buttons to remediation workflows
4. **Create Dashboards** - Link to Splunk dashboards and runbooks
5. **Team Routing** - Route incidents to specific teams/channels

Your incident management system is now ready for real-time Slack notifications! 🚀