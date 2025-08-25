# Splunk MCP Server Deployment Guide

This guide explains how to deploy and run the Splunk Model Context Protocol (MCP) server.

## Prerequisites

1. Python 3.8+ installed
2. UV package manager installed (`pip install uv`)
3. AWS credentials configured with access to:
   - AWS Bedrock
   - AWS Secrets Manager
   - Amazon OpenSearch Service
4. Splunk server access with a valid token

## Setup

1. **Install dependencies**:
   ```bash
   uv pip install -r requirements.txt
   ```

2. **Configure environment variables**:
   
   Make sure your `.env` file contains the following variables:
   ```
   secret_arn=arn:aws:secretsmanager:region:account:secret:your-secret-name
   FASTMCP_DEBUG=true
   ```

   The secret in AWS Secrets Manager should contain:
   ```json
   {
     "SplunkToken": "your-splunk-token",
     "SplunkHost": "your-splunk-host"
   }
   ```

3. **AWS Credentials**:
   
   Ensure your AWS credentials are properly configured either through:
   - Environment variables
   - AWS credentials file
   - IAM role (if running on AWS)

## Running the Server

To run the Splunk MCP server:

```bash
uv run splunk-server.py
```

The server will start and listen for MCP requests via stdio.

## Available Tools

The Splunk MCP server provides the following tools:

1. `search_aws_sourcetypes`: Searches a Vector database for Splunk sourcetypes for AWS source data
2. `get_splunk_fields`: Gets the list of fields for a given sourcetype
3. `get_splunk_results`: Executes a Splunk search query and returns results
4. `get_splunk_lookups`: Gets the list of lookup values for a sourcetype
5. `get_splunk_lookup_values`: Gets the values for a specific lookup

## Connecting to the Server

To connect to the server from a client application:

```python
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters
from contextlib import AsyncExitStack

async def connect_to_splunk_server():
    exit_stack = AsyncExitStack()
    
    # Connect to monitoring server
    monitoring_params = StdioServerParameters(
        command="uv",
        args=["run", "server/splunk-server.py"],
    )

    monitoring_transport = await exit_stack.enter_async_context(stdio_client(monitoring_params))
    monitoring_stdio, monitoring_write = monitoring_transport
    splunk_session = await exit_stack.enter_async_context(
        ClientSession(monitoring_stdio, monitoring_write)
    )

    # Initialize the monitoring MCP server
    await splunk_session.initialize()
    print(f"Connected to the Splunk MCP server")
    
    return splunk_session, exit_stack
```

## Troubleshooting

1. **Logs**: Check the logs in the `logs` directory for detailed error information
2. **AWS Credentials**: Ensure your AWS credentials have the necessary permissions
3. **Splunk Token**: Verify your Splunk token is valid and has the required permissions
4. **OpenSearch**: Confirm your OpenSearch endpoint is accessible and the index exists