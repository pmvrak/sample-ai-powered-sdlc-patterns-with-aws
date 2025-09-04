# Slack Integration Setup Guide

## Complete Setup (10 minutes)

### Step 1: Create Slack App
1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. App Name: `Incident Management Bot`
4. Choose your workspace
5. Click **"Create App"**

### Step 2: Configure Bot User and Permissions

1. Go to **"OAuth & Permissions"**
2. Add these **Bot Token Scopes** (all required):
   - `app_mentions:read` - Read mentions of the bot
   - `channels:read` - Read channel information
   - `chat:write` - Send messages
   - `chat:write.public` - Send messages to channels bot isn't in
   - `commands` - Handle slash commands
   - `im:read` - Read direct messages
   - `users:read` - Read user information
3. Click **"Install to Workspace"**
4. **Copy the Bot User OAuth Token** (starts with `xoxb-`)
5. **Copy the Signing Secret** from **"Basic Information"** → **"App Credentials"**

### Step 3: Enable Incoming Webhooks
1. Go to **"Incoming Webhooks"**
2. Toggle **"Activate Incoming Webhooks"** to **On**
3. Click **"Add New Webhook to Workspace"**
4. Choose the channel for incident notifications (e.g., `#incidents`)
5. Click **"Allow"**
6. **Copy the Webhook URL** (starts with `https://hooks.slack.com/services/...`)

### Step 4: Configure Event Subscriptions
1. Go to **"Event Subscriptions"**
2. Toggle **"Enable Events"** to **On**
3. **Request URL**: `https://your-domain.com/slack/events`
   - ⚠️ **Important**: Slack will send a challenge request to verify this URL
   - The system will automatically respond with the challenge token
   - You'll see a green checkmark when verification succeeds
4. Under **"Subscribe to bot events"**, add:
   - `app_mention` - When the bot is mentioned
   - `message.im` - Direct messages to the bot
5. Click **"Save Changes"**

### Step 5: Add Slash Commands
1. Go to **"Slash Commands"**
2. Click **"Create New Command"** for each:

**Command 1: /investigate**
- Command: `/investigate`
- Request URL: `https://your-domain.com/slack/commands`
- Description: `AI-powered incident investigation`
- Usage Hint: `<incident_id> | help`

**Command 2: /incident**
- Command: `/incident`
- Request URL: `https://your-domain.com/slack/commands`
- Description: `Manage incidents`
- Usage Hint: `list | status | help`

### Step 6: Add Interactive Components
1. Go to **"Interactivity & Shortcuts"**
2. Toggle **"Interactivity"** to **On**
3. **Request URL**: `https://your-domain.com/slack/interactions`
4. Click **"Save Changes"**

### Step 7: Configure Environment Variables

Add these to your `.env` file or environment:

```bash
# Required - All of these are needed for full functionality
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
SLACK_BOT_TOKEN="xoxb-your-bot-token"
SLACK_SIGNING_SECRET="your-signing-secret"
SLACK_CHANNEL="#incidents"

# Optional
SLACK_DEBUG=false
```

### Step 8: Test the Integration

## Testing Your Setup

### 1. Verify Event Subscription
After setting up event subscriptions, Slack will send a challenge request to verify your endpoint:
- ✅ **Challenge Response**: The system automatically handles URL verification
- ✅ **Green Checkmark**: You should see this in the Slack app settings
- ❌ **Red X**: Check your endpoint URL and ensure the service is running

### 2. Test Bot Mentions
1. Add the bot to your `#incidents` channel: `/invite @Incident Management Bot`
2. Mention the bot: `@Incident Management Bot help`
3. You should receive a response with available commands

### 3. Test Slash Commands
Try these commands in Slack:
- `/investigate help` - Show investigation options
- `/incident list` - List recent incidents
- `/incident status` - Show system status

### 4. Test Interactive Features
The integration provides rich interactive notifications with:
- 🚨 **Severity indicators** (High/Medium/Low)
- 📊 **Event counts** and affected systems
- 📝 **Sample events** from Splunk/PagerDuty
- 🔘 **Action buttons** (Investigate, Acknowledge, Escalate)
- 🤖 **AI Investigation** buttons for automated analysis
- ⏰ **Timestamps** and detection queries

### 5. Test Real Incidents
The integration automatically detects and notifies for:
- ✅ **AWS CloudTrail Errors**
- ✅ **High Error Rates**
- ✅ **Performance Issues**
- ✅ **Security Events**
- ✅ **PagerDuty Incidents**

## Integration with Production API

The Slack integration works with your live production API:
- **Real incidents** from your Splunk data
- **Live system stats** (128,118+ events)
- **Continuous monitoring** (60-second cycles)
- **Rich formatting** with action buttons

## Troubleshooting

### Event Subscription Issues
1. **"Challenge failed" or Red X in Slack settings**
   - Ensure your service is running: `python run_api.py`
   - Check the endpoint URL is publicly accessible
   - Verify the `/slack/events` endpoint responds to POST requests
   - Check logs for challenge handling: `🔐 Handling Slack URL verification challenge`

2. **"Invalid signature" errors**
   - Verify `SLACK_SIGNING_SECRET` is correct
   - Check that the signing secret matches your Slack app
   - Ensure timestamps aren't too old (5-minute window)

### Bot and Command Issues
3. **Bot doesn't respond to mentions**
   - Add bot to the channel: `/invite @Incident Management Bot`
   - Check bot has `app_mentions:read` permission
   - Verify event subscription includes `app_mention`

4. **Slash commands don't work**
   - Verify command URLs point to your service
   - Check `SLACK_BOT_TOKEN` is set correctly
   - Ensure service is running on the correct port

5. **Interactive buttons don't work**
   - Verify interactive components URL is set
   - Check `SLACK_SIGNING_SECRET` for signature verification
   - Look for interaction handling in logs

### General Issues
6. **"No notifications received"**
   - Test incident detection: `curl http://localhost:8002/incidents`
   - Verify all environment variables are set
   - Check webhook URL is correct

### Debug Mode
```bash
# Enable debug logging
export SLACK_DEBUG=true
python run_api.py

# Test specific endpoints
curl -X POST http://localhost:8002/slack/events \
  -H "Content-Type: application/json" \
  -d '{"type":"url_verification","challenge":"test123"}'
```

### Logs to Watch For
- ✅ `🔐 Handling Slack URL verification challenge`
- ✅ `🤖 Handling AI mention from user`
- ✅ `Slack command: /investigate from user`
- ❌ `Invalid signature` or `Missing timestamp`

## Advanced Features

### AI-Powered Investigation
Once setup is complete, users can:
- **Mention the bot**: `@Incident Management Bot investigate INC-12345`
- **Use slash commands**: `/investigate INC-12345 performance`
- **Click AI buttons**: Interactive investigation buttons in notifications
- **Get automated analysis**: Root cause analysis, remediation suggestions

### Integration Capabilities
The system provides:
- 🔍 **Real-time Splunk queries** via MCP
- 📟 **PagerDuty incident management** 
- 🤖 **AI-powered root cause analysis**
- 📊 **Interactive dashboards** and metrics
- 🔄 **Automated remediation workflows**
- 👥 **Team collaboration** features

### Production Deployment
For production use:
1. **Deploy to AWS ECS** using the provided infrastructure
2. **Configure HTTPS** with SSL certificates
3. **Set up monitoring** and alerting
4. **Configure team routing** for different incident types
5. **Add custom integrations** for your specific tools

## Security Notes

- ✅ **Signature verification** prevents unauthorized requests
- ✅ **Challenge handling** secures event subscriptions  
- ✅ **Token-based authentication** for all Slack API calls
- ✅ **Environment variable protection** for sensitive data
- ⚠️ **HTTPS required** for production deployments

Your AI-powered incident management system is now ready for real-time Slack collaboration! 🚀