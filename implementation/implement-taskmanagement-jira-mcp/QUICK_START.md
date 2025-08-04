# 🚀 JIRA MCP Server - Quick Start Guide

## ✅ **CURRENT STATUS: FULLY WORKING**

Your JIRA MCP server is deployed and operational!

## 🎯 **Quick Start (30 seconds)**

```bash
# 1. Get fresh OAuth token and start Amazon Q
./refresh_and_start.sh

# 2. Test in Amazon Q
"List my JIRA projects"
```

## 📋 **Available Commands in Amazon Q**

| Command | Description | Example |
|---------|-------------|---------|
| **List Projects** | Show all JIRA projects | "List my JIRA projects" |
| **Health Check** | Test JIRA connection | "Check JIRA server health" |
| **Search Issues** | Find issues using JQL | "Search for issues in project DP" |
| **Get Issue** | Show issue details | "Show me issue DP-10" |
| **Create Issue** | Create new issue | "Create a task in DP: Test issue" |

## 🔄 **Token Management**

```bash
# When tokens expire (every hour):
./get_fresh_token.sh

# Then restart Amazon Q:
q chat
```

## 🏗️ **Architecture**

```
Amazon Q (Local) 
    ↓
Local MCP Proxy (proxy_jira_mcp.py)
    ↓ [OAuth Bearer Token]
Remote MCP Server (AWS Lambda)
    ↓
JIRA API (amazon-jira-mcp.atlassian.net)
```

## 🔗 **Working Endpoints**

- **MCP Server**: https://4p8xg1e2ii.execute-api.us-east-1.amazonaws.com/dev
- **OAuth Server**: https://0bmc3y5o9h.execute-api.us-east-1.amazonaws.com/dev
- **JIRA Instance**: https://amazon-jira-mcp.atlassian.net

## 🧪 **Test Results**

| Component | Status | Details |
|-----------|--------|---------|
| Remote MCP Server | ✅ Working | AWS Lambda healthy |
| OAuth Server | ✅ Working | Token generation working |
| JIRA Connection | ✅ Working | Connected successfully |
| All 5 MCP Tools | ✅ Working | Health, projects, search, get, create |
| Token Management | ✅ Working | Auto-refresh capability |
| Amazon Q Integration | ✅ Ready | MCP configuration complete |

## 🆘 **Troubleshooting**

### **Token Expired Error**
```bash
./get_fresh_token.sh
q chat
```

### **Amazon Q Not Seeing Tools**
Check MCP configuration in `~/.aws/amazonq/mcp.json`:
```json
{
  "mcpServers": {
    "jira-mcp-server": {
      "command": "python3",
      "args": [
        "/path/to/your/proxy_jira_mcp.py"
      ],
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

### **JIRA Connection Issues**
Test the health endpoint:
```bash
curl https://4p8xg1e2ii.execute-api.us-east-1.amazonaws.com/dev/health
```

## 📞 **Support**

- Check CloudWatch logs for AWS Lambda errors
- Verify JIRA credentials in `.env` file
- Test token refresh with `./get_fresh_token.sh`
- Ensure AWS CLI is configured properly

---

**🎉 Your JIRA MCP server is ready for production use with Amazon Q!**
