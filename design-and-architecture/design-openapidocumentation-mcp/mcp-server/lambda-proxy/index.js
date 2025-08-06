const AWS = require('aws-sdk');
const https = require('https');

// Your ECS service endpoint
const MCP_SERVER_ENDPOINT = process.env.MCP_SERVER_ENDPOINT;

exports.handler = async (event) => {
    try {
        // Extract user info from Cognito JWT token
        const userInfo = event.requestContext.authorizer.claims;
        
        // Forward request to MCP server
        const mcpResponse = await forwardToMCPServer({
            method: event.httpMethod,
            path: event.path,
            headers: event.headers,
            body: event.body,
            userInfo: userInfo
        });
        
        return {
            statusCode: mcpResponse.statusCode,
            headers: {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
            },
            body: mcpResponse.body
        };
    } catch (error) {
        console.error('Proxy error:', error);
        return {
            statusCode: 500,
            body: JSON.stringify({ error: 'Internal server error' })
        };
    }
};

async function forwardToMCPServer(request) {
    return new Promise((resolve, reject) => {
        const options = {
            hostname: MCP_SERVER_ENDPOINT,
            port: 3000,
            path: request.path,
            method: request.method,
            headers: {
                ...request.headers,
                'X-User-Info': JSON.stringify(request.userInfo)
            }
        };
        
        const req = https.request(options, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                resolve({
                    statusCode: res.statusCode,
                    body: data
                });
            });
        });
        
        req.on('error', reject);
        
        if (request.body) {
            req.write(request.body);
        }
        
        req.end();
    });
}