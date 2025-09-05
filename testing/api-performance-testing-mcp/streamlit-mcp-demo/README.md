# Performance Test Runner - Streamlit MCP Demo

A clean, functional web interface for the AI-powered performance testing MCP server. This Streamlit app provides an intuitive way to interact with the MCP server and visualize test artifacts stored in S3.

## 🚀 Features

- **Interactive MCP Tool Execution**: 7 buttons for all MCP tools (analyze architecture, generate scenarios, etc.)
- **Real-time Status Monitoring**: Live status badges and request/response inspection
- **S3 Artifact Visualization**: Browse scenarios, test plans, results, and analysis files
- **Live Logs**: Auto-refreshing logs from S3 during test execution
- **Performance Metrics**: Computed statistics from JTL result files
- **Demo Mode**: Run with simulated data for testing the UI

## 🛠️ Setup Instructions

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Set the required environment variables:

```bash
# Required for production use
export MCP_FUNCTION_URL="https://<your-function-id>.lambda-url.<region>.on.aws/"
export AWS_REGION="us-east-1"
export ARTIFACT_BUCKET="performance-testing-<account-id>-us-east-1"

# Optional: Enable demo mode for testing
export DEMO_MODE="true"
```

### 3. Configure AWS Credentials

Ensure your local AWS credentials are configured. You can use any of these methods:

```bash
# Option 1: AWS SSO
aws sso login --profile your-profile

# Option 2: AWS Configure
aws configure

# Option 3: Environment variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
```

### 4. Run the Application

```bash
streamlit run app.py
```

The app will be available at `http://localhost:8501`

## 🎯 Usage Guide

### Session Management
- **Session ID**: Enter a unique identifier for your test session (default: `demo-001`)
- **Parameters**: Configure optional parameters like target URL, cluster settings, etc.

### Tool Execution
Click any of the 7 tool buttons in the sidebar:

1. **🏗️ Analyze Architecture** - Parse architecture documents using AI
2. **📋 Generate Scenarios** - Create realistic test scenarios
3. **⚙️ Generate Test Plans** - Convert scenarios to JMeter Java DSL code
4. **✅ Validate Test Plans** - Validate and fix generated code
5. **🚀 Execute Tests** - Run performance tests on ECS Fargate
6. **📦 Get Artifacts** - Retrieve test artifacts from S3
7. **🧠 Analyze Results** - AI-powered performance analysis

### Artifact Visualization

The main area contains 4 tabs:

- **📋 Scenarios**: View generated test scenarios in table format
- **⚙️ Plans**: Browse Java test plan files with code preview
- **📊 Results**: View JTL result files with computed performance metrics
- **🧠 Analysis**: View AI-generated performance analysis and recommendations

### Live Monitoring

- **Run Inspector**: Shows current tool execution status with request/response details
- **Live Logs**: Auto-refreshing logs from S3 during test execution
- **Status Badges**: Color-coded status indicators (Idle/Running/OK/Failed)

## 🎭 Demo Mode

For testing the UI without a real MCP server, enable demo mode:

```bash
export DEMO_MODE="true"
streamlit run app.py
```

Demo mode provides:
- Simulated MCP tool responses
- Mock S3 artifacts and data
- Realistic performance metrics
- Sample log entries

## 📁 Project Structure

```
streamlit-mcp-demo/
├── app.py                 # Main Streamlit application
├── mcp_client.py         # MCP server communication with SigV4 auth
├── s3_utils.py           # S3 artifact reading and processing
├── ui_components.py      # Reusable UI components
├── requirements.txt      # Python dependencies
├── .streamlit/
│   └── config.toml      # Streamlit configuration
└── README.md            # This file
```

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `MCP_FUNCTION_URL` | Yes* | Lambda Function URL | `https://abc123.lambda-url.us-east-1.on.aws/` |
| `AWS_REGION` | Yes* | AWS region | `us-east-1` |
| `ARTIFACT_BUCKET` | Yes* | S3 bucket for artifacts | `performance-testing-123456789-us-east-1` |
| `DEMO_MODE` | No | Enable demo mode | `true` or `false` |

*Not required when `DEMO_MODE=true`

### Streamlit Configuration

The app uses a wide layout with custom theming. Configuration is in `.streamlit/config.toml`.

## 🐛 Troubleshooting

### Common Issues

1. **Missing Environment Variables**
   - Error: "Missing required environment variables"
   - Solution: Set all required environment variables or enable `DEMO_MODE=true`

2. **AWS Credentials Not Found**
   - Error: "Unable to locate credentials"
   - Solution: Configure AWS credentials using `aws configure` or AWS SSO

3. **S3 Access Denied**
   - Error: "Access Denied" when reading artifacts
   - Solution: Ensure your AWS credentials have S3 read permissions for the artifact bucket

4. **Lambda Function URL Access Denied**
   - Error: "403 Forbidden" when calling MCP tools
   - Solution: Ensure your AWS credentials have `lambda:InvokeFunctionUrl` permission

### Debug Tips

- Enable demo mode to test the UI without backend dependencies
- Check the browser console for JavaScript errors
- Use the Run Inspector to see detailed request/response data
- Check AWS CloudWatch logs for Lambda function errors

## 🔒 Security Notes

- The app uses AWS SigV4 authentication for Lambda Function URL calls
- All S3 operations use your local AWS credentials
- No sensitive data is stored in the Streamlit session state
- Presigned URLs are generated for secure artifact downloads

## 🚀 Performance Tips

- Use session IDs to organize test runs
- The app auto-refreshes logs every 2 seconds during test execution
- Large JTL files are processed efficiently using pandas
- Artifact listings are cached until manually refreshed

## 📝 License

This demo application is part of the AI-powered performance testing system. See the main project for license information.