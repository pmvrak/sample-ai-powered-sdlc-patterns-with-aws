# Jenkins MCP Server - Quick Start Guide

Get up and running with Jenkins MCP Server in 10 minutes!

## Prerequisites

- ✅ AWS CLI configured with credentials
- ✅ Python 3.11+ installed
- ✅ Node.js 18+ installed
- ✅ Jenkins server with API token
- ✅ Amazon Q Developer access

## 🚀 Quick Setup (5 steps)

### 1. Configure Jenkins Credentials

```bash
# Copy and edit environment file
cp .env.example .env

# Edit .env with your Jenkins details:
# JENKINS_URL=https://jenkins.yourcompany.com
# JENKINS_USERNAME=your-username
# JENKINS_API_TOKEN=your-jenkins-api-token
```

### 2. Deploy AWS Infrastructure

```bash
# Set environment variables
export JENKINS_URL="https://jenkins.yourcompany.com"
export JENKINS_USERNAME="your-username"
export JENKINS_API_TOKEN="your-jenkins-api-token"

# Deploy CDK stacks
./deployment/deploy_cdk.sh dev
```

### 3. Get OAuth Token

```bash
# Get fresh authentication token
./get_fresh_token.sh
```

### 4. Configure Amazon Q

Add to `~/.aws/amazonq/mcp.json`:

```json
{
  "mcpServers": {
    "jenkins-mcp-server": {
      "command": "python3",
      "args": [
        "/path/to/your/jenkins-mcp-server/proxy_jenkins_mcp.py"
      ],
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

### 5. Test & Use

```bash
# Start Amazon Q
q chat

# Try Jenkins commands:
# "Check Jenkins server health"
# "List all Jenkins jobs"
# "Trigger a build for my-job"
# "Create a new job called test-job that runs echo hello"
```

## 🎯 Available Jenkins Tools

- **jenkins_health_check** - Test connection and server info
- **jenkins_list_jobs** - List all jobs
- **jenkins_get_job_info** - Get job details
- **jenkins_trigger_build** - Start builds
- **jenkins_get_build_info** - Get build status
- **jenkins_get_build_log** - Get console output
- **jenkins_list_builds** - List recent builds
- **jenkins_get_queue_info** - Get build queue
- **jenkins_get_nodes** - Get agent information
- **jenkins_abort_build** - Stop running builds
- **jenkins_create_job** - Create new jobs

## 🔧 Troubleshooting

- **Connection issues**: Check Jenkins URL and credentials
- **Token expired**: Run `./get_fresh_token.sh`
- **Permission denied**: Verify Jenkins user permissions

## 📚 More Information

See [README.md](README.md) for complete documentation.
