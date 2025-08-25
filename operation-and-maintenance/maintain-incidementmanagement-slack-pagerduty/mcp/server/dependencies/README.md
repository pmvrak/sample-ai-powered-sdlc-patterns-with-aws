# Follow these instructions to install the dependencies

## Ensure Python uv package is installed, initiate a project, create a virtual environment and install dependencies

```bash
uv create 
uv venv
source .venv/bin/activate 
uv add -r requirements.txt
```

## Create Secrets Manager Secret and upload your Splunk Host and Credentials
### Edit `create-splunk-secrets.py` and update your Splunk Host URL/IP and Splunk Access Token
```
secret_value['SplunkHost'] = "<Your Splunk Host IP or URL>"
secret_value['SplunkToken'] = "<Your Splunk Access Token>"
```
### Run the code to create the secrets in the Secret Manager. Note down the Secret Manager ARN

```
uv run create-splunk-secrets.py
```

### Edit the `.env` file in `server` directory to include the secrets manager ARN.
```
secret_arn=arn:aws:secretsmanager:us-east-1:123456789012:secret:splunk-bedrock-secret-bPya16
FASTMCP_DEBUG=true
```