# Chat Commands Reference

The Incident Management System provides comprehensive chat integration for Slack and Microsoft Teams, allowing you to manage incidents directly from your chat platform without switching contexts.

## 📋 Table of Contents

- [Getting Started](#getting-started)
- [Command Overview](#command-overview)
- [Detailed Command Reference](#detailed-command-reference)
- [Interactive Features](#interactive-features)
- [Permissions](#permissions)
- [Tips and Best Practices](#tips-and-best-practices)
- [Troubleshooting](#troubleshooting)

## 🚀 Getting Started

### Slack Setup
1. Ensure the Incident Management bot is added to your workspace
2. Invite the bot to relevant channels: `/invite @incident-bot`
3. Test with: `/incident help`

### Microsoft Teams Setup
1. Install the Incident Management app from your organization's app catalog
2. Add the bot to your team
3. Test with: `/incident help`

### First Steps
```
/incident help                    # Show all available commands
/incident list                    # View current incidents
/incident status INC-123          # Check specific incident
```

## 📖 Command Overview

| Command | Purpose | Permission | Example |
|---------|---------|------------|---------|
| `/incident help` | Show help information | Public | `/incident help assign` |
| `/incident list` | List incidents with filters | Public | `/incident list open devops` |
| `/incident status` | Show incident details | Public | `/incident status INC-123` |
| `/incident create` | Create new incident | Responder | `/incident create API errors` |
| `/incident assign` | Assign incident to team/user | Responder | `/incident assign INC-123 devops @john` |
| `/incident resolve` | Mark incident as resolved | Responder | `/incident resolve INC-123` |
| `/incident escalate` | Escalate incident | Responder | `/incident escalate INC-123` |
| `/incident note` | Add note to incident | Public | `/incident note INC-123 Investigating` |

## 📚 Detailed Command Reference

### `/incident help [command]`

**Purpose**: Display help information for commands

**Permission**: Public (anyone can use)

**Usage**:
```
/incident help                    # Show all commands
/incident help assign             # Show help for specific command
```

**Examples**:
```
/incident help
/incident help create
/incident help resolve
```

---

### `/incident list [status] [team] [limit]`

**Purpose**: List incidents with optional filtering

**Permission**: Public

**Parameters**:
- `status` (optional): Filter by status (`open`, `assigned`, `in_progress`, `resolved`, `closed`, `all`)
- `team` (optional): Filter by assigned team
- `limit` (optional): Number of results (1-50, default: 10)

**Usage**:
```
/incident list                    # Show open incidents (default)
/incident list assigned           # Show assigned incidents
/incident list open devops        # Show open incidents for devops team
/incident list all devops 20      # Show all devops incidents, limit 20
```

**Response Format**:
```
🚨 Incidents (status: open, team: devops)

🔴 INC-20240123-ABC123 - Database connection timeout
   Status: ASSIGNED | Severity: HIGH | Team: devops | User: @john.doe
   Created: 2 hours ago | Updated: 30 minutes ago

🟡 INC-20240123-DEF456 - API response time degradation  
   Status: IN_PROGRESS | Severity: MEDIUM | Team: devops | User: @jane.smith
   Created: 1 hour ago | Updated: 15 minutes ago

📊 Total: 2 incidents | Showing: 1-2
```

---

### `/incident status <incident_id>`

**Purpose**: Show detailed information for a specific incident

**Permission**: Public

**Parameters**:
- `incident_id` (required): Incident ID (format: INC-YYYYMMDD-XXXXXX)

**Usage**:
```
/incident status INC-20240123-ABC123
```

**Response Format**:
```
🚨 Incident Details: INC-20240123-ABC123

📋 Title: Database connection timeout
📝 Description: Multiple database connection timeouts detected in production
🔴 Severity: HIGH | Status: ASSIGNED
👥 Team: devops | User: @john.doe
🕐 Created: 2024-01-23 10:30 UTC (2 hours ago)
🔄 Updated: 2024-01-23 12:00 UTC (30 minutes ago)

🎯 Affected Systems: database, api
🏷️ Tags: database, timeout, production

🤖 AI Analysis:
• Root cause: Database connection pool exhaustion
• Confidence: 85%
• Suggested actions: Increase connection pool size, optimize queries

🔗 Actions: [Assign] [Resolve] [Escalate] [Add Note]
```

---

### `/incident create <title> [description]`

**Purpose**: Create a new incident

**Permission**: Responder

**Parameters**:
- `title` (required): Brief incident title
- `description` (optional): Detailed description

**Usage**:
```
/incident create Database connection issues
/incident create API errors High error rate in production API
```

**Response Format**:
```
✅ Incident created: INC-20240123-GHI789

📋 Title: Database connection issues
👤 Created by: @your.username
🕐 Created: 2024-01-23 12:30 UTC
🔄 Status: DETECTED → Routing to appropriate team...

The incident has been automatically analyzed and will be assigned to the appropriate team shortly.
```

---

### `/incident assign <incident_id> [team] [user]`

**Purpose**: Assign incident to a team and/or user

**Permission**: Responder

**Parameters**:
- `incident_id` (required): Incident ID
- `team` (optional): Team name
- `user` (optional): User mention (@username)

**Usage**:
```
/incident assign INC-123 devops                    # Assign to team
/incident assign INC-123 devops @john.doe          # Assign to team and user
/incident assign INC-123 @jane.smith               # Assign to user only
```

**Response Format**:
```
✅ Incident INC-20240123-ABC123 assigned to team `devops` and user @john.doe by @your.username

The assigned team and user have been notified via their preferred channels.
```

---

### `/incident resolve <incident_id> [resolution_notes]`

**Purpose**: Mark an incident as resolved

**Permission**: Responder

**Parameters**:
- `incident_id` (required): Incident ID
- `resolution_notes` (optional): Resolution description

**Usage**:
```
/incident resolve INC-123
/incident resolve INC-123 Fixed database connection pool configuration
```

**Response Format**:
```
✅ Incident INC-20240123-ABC123 resolved by @your.username

Resolution: Fixed database connection pool configuration
Resolution time: 2 hours 15 minutes
Status: RESOLVED

All stakeholders have been notified of the resolution.
```

---

### `/incident escalate <incident_id> [reason]`

**Purpose**: Escalate an incident to higher priority or different team

**Permission**: Responder

**Parameters**:
- `incident_id` (required): Incident ID
- `reason` (optional): Escalation reason

**Usage**:
```
/incident escalate INC-123
/incident escalate INC-123 No response from assigned team for 2 hours
```

**Response Format**:
```
⚠️ Incident INC-20240123-ABC123 escalated by @your.username

Reason: No response from assigned team for 2 hours
Escalated to: Senior DevOps Team
Previous team: DevOps Team

The escalation team has been notified and will take over the incident.
```

---

### `/incident note <incident_id> <note_text>`

**Purpose**: Add a note or update to an incident

**Permission**: Public

**Parameters**:
- `incident_id` (required): Incident ID
- `note_text` (required): Note content

**Usage**:
```
/incident note INC-123 Investigating database logs
/incident note INC-123 Found root cause in connection pool configuration
```

**Response Format**:
```
✅ Note added to incident INC-20240123-ABC123

Note: Investigating database logs
Added by: @your.username
Time: 2024-01-23 12:45 UTC

The note has been added to the incident timeline and stakeholders have been notified.
```

## 🎛️ Interactive Features

### Action Buttons
Many responses include interactive buttons for quick actions:

```
🚨 New Incident: INC-20240123-ABC123
Database connection timeout detected

[Assign to Me] [Assign to Team] [Analyze] [View Details]
```

### Modal Dialogs
Complex operations open modal dialogs:

**Assignment Modal**:
```
Assign Incident: INC-20240123-ABC123

Team: [Dropdown: devops, platform, security, ...]
User: [@mention or select from list]
Priority: [Normal] [High] [Urgent]
Notes: [Optional assignment notes]

[Cancel] [Assign Incident]
```

**Resolution Modal**:
```
Resolve Incident: INC-20240123-ABC123

Resolution Category:
○ Fixed
○ Workaround Applied  
○ No Action Required
○ Duplicate

Resolution Notes:
[Text area for detailed resolution]

Notify Stakeholders: ☑️
Close Related Incidents: ☑️

[Cancel] [Resolve Incident]
```

### Confirmation Prompts
Destructive actions require confirmation:

```
⚠️ Confirm Escalation

Are you sure you want to escalate incident INC-20240123-ABC123?

This will:
• Notify the escalation team
• Increase incident priority
• Add escalation to audit log

[Cancel] [Confirm Escalation]
```

## 🔐 Permissions

### Permission Levels

**Public**: Anyone in the channel can use
- `/incident help`
- `/incident list`
- `/incident status`
- `/incident note`

**Responder**: Incident responders and team members
- `/incident create`
- `/incident assign`
- `/incident resolve`
- `/incident escalate`

**Admin**: System administrators only
- Advanced configuration commands
- User permission management
- System maintenance commands

### Permission Checking
The system automatically checks permissions:

```
❌ Insufficient permissions for command `assign`

Required: responder
Your level: public

Contact your administrator to request responder permissions.
```

## 💡 Tips and Best Practices

### Efficient Incident Management

1. **Use filters effectively**:
   ```
   /incident list open devops 5        # Quick team overview
   /incident list high                 # Focus on critical issues
   ```

2. **Add meaningful notes**:
   ```
   /incident note INC-123 Deployed fix to staging, testing now
   /incident note INC-123 Fix confirmed, deploying to production
   ```

3. **Resolve with details**:
   ```
   /incident resolve INC-123 Increased connection pool from 10 to 50 connections
   ```

### Team Collaboration

1. **Mention relevant people**:
   ```
   /incident assign INC-123 devops @john.doe
   /incident note INC-123 @jane.smith please review the database logs
   ```

2. **Use escalation appropriately**:
   ```
   /incident escalate INC-123 Customer impact increasing, need senior help
   ```

3. **Keep stakeholders informed**:
   ```
   /incident note INC-123 ETA for fix: 30 minutes, workaround deployed
   ```

### Automation Integration

1. **Create incidents from monitoring**:
   ```
   /incident create High CPU usage CPU > 90% for 10 minutes on web-01
   ```

2. **Link to external systems**:
   ```
   /incident note INC-123 Related Jira ticket: PROJ-1234
   /incident note INC-123 Monitoring dashboard: https://grafana.com/d/abc123
   ```

## 🔧 Troubleshooting

### Common Issues

**Command not recognized**:
```
❌ Unknown command: `statu`. Did you mean `status`?

Use `/incident help` for available commands.
```

**Invalid incident ID**:
```
❌ Invalid incident ID format: `123`

Expected format: INC-YYYYMMDD-XXXXXX
Example: INC-20240123-ABC123
```

**Permission denied**:
```
❌ Insufficient permissions for command `resolve`

Required: responder
Contact your administrator for access.
```

**Incident not found**:
```
❌ Incident not found: INC-20240123-XYZ999

Please check the incident ID and try again.
Use `/incident list` to see available incidents.
```

### Getting Help

1. **Command-specific help**:
   ```
   /incident help assign
   ```

2. **Check your permissions**:
   ```
   /incident help permissions
   ```

3. **System status**:
   ```
   /incident help status
   ```

### Error Recovery

If a command fails:

1. **Check the error message** - it usually contains helpful information
2. **Verify the incident ID format** - must be INC-YYYYMMDD-XXXXXX
3. **Confirm your permissions** - some commands require responder access
4. **Try the command again** - temporary network issues may cause failures
5. **Contact your administrator** - for persistent issues or access problems

## 📱 Platform-Specific Features

### Slack-Specific Features

- **Slash command autocomplete**: Type `/incident` and press Tab
- **Rich message formatting**: Incidents display with colors and emojis
- **Thread replies**: Bot responses can be threaded to reduce noise
- **Workflow integration**: Connect with Slack workflows and automations

### Teams-Specific Features

- **Adaptive Cards**: Rich interactive cards for incident details
- **Action buttons**: Native Teams action buttons for quick operations
- **Notification integration**: Integrates with Teams notification system
- **Tab integration**: Pin incident dashboard as a Teams tab

## 🔄 Real-time Updates

The chat integration provides real-time updates:

```
🔄 Incident Update: INC-20240123-ABC123

Status changed: ASSIGNED → IN_PROGRESS
Assigned user: @john.doe started working on the incident

Updated: 2024-01-23 13:15 UTC
```

```
✅ Incident Resolved: INC-20240123-ABC123

Database connection timeout has been resolved
Resolution time: 2 hours 45 minutes
Resolved by: @john.doe

All affected systems are now operational.
```

## 📞 Support

- **Command help**: Use `/incident help` for immediate assistance
- **Documentation**: Check the [User Guide](user-guide.md) for detailed information
- **System issues**: Contact your administrator or check system status
- **Feature requests**: Provide feedback through your organization's channels

---

*For more advanced usage and integration patterns, see the [User Guide](user-guide.md) and [Integration Guide](integration-guide.md).*