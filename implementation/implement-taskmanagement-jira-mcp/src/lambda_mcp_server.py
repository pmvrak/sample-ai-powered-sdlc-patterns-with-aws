#!/usr/bin/env python3
"""
Lambda-compatible JIRA MCP Server
Simple implementation without FastAPI dependencies
"""

import json
from typing import Dict, List, Any, Optional

class JiraMCPServer:
    """Simple JIRA MCP Server for Lambda"""
    
    def __init__(self):
        self.tools = [
            {
                "name": "jira_health_check",
                "description": "Check JIRA server health and connection",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "jira_list_projects",
                "description": "List all JIRA projects you have access to",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "jira_create_issue",
                "description": "Create a new JIRA issue",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_key": {
                            "type": "string",
                            "description": "Project key (e.g., 'DP')"
                        },
                        "summary": {
                            "type": "string",
                            "description": "Issue summary/title"
                        },
                        "description": {
                            "type": "string",
                            "description": "Issue description (optional)"
                        },
                        "issue_type": {
                            "type": "string",
                            "description": "Issue type (e.g., 'Task', 'Bug', 'Story')",
                            "default": "Task"
                        },
                        "priority": {
                            "type": "string",
                            "description": "Issue priority (optional - only if supported by project)"
                        }
                    },
                    "required": ["project_key", "summary"]
                }
            },
            {
                "name": "jira_search_issues",
                "description": "Search for JIRA issues using JQL",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "jql": {
                            "type": "string",
                            "description": "JQL query string"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results",
                            "default": 10
                        }
                    },
                    "required": ["jql"]
                }
            },
            {
                "name": "jira_get_issue",
                "description": "Get detailed information about a specific JIRA issue",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "issue_key": {
                            "type": "string",
                            "description": "Issue key (e.g., 'DP-123')"
                        }
                    },
                    "required": ["issue_key"]
                }
            },
            {
                "name": "jira_add_comment",
                "description": "Add a comment to a JIRA issue",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "issue_key": {
                            "type": "string",
                            "description": "Issue key (e.g., 'DP-123')"
                        },
                        "comment": {
                            "type": "string",
                            "description": "Comment text to add to the issue"
                        }
                    },
                    "required": ["issue_key", "comment"]
                }
            }
        ]
    
    def list_tools(self) -> Dict[str, Any]:
        """List available tools"""
        return {
            "tools": self.tools
        }
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific tool"""
        try:
            # Import JIRA client
            from jira_client.client import JiraClient
            jira_client = JiraClient()
            
            # Set up asyncio loop for async methods
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                if tool_name == "jira_health_check":
                    result = loop.run_until_complete(jira_client.test_connection())
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"JIRA Health Check:\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jira_list_projects":
                    result = loop.run_until_complete(jira_client.get_projects())
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"JIRA Projects:\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jira_create_issue":
                    project_key = arguments.get("project_key")
                    summary = arguments.get("summary")
                    description = arguments.get("description", "")
                    issue_type = arguments.get("issue_type", "Task")
                    priority = arguments.get("priority")  # Don't set default priority
                    
                    result = loop.run_until_complete(jira_client.create_issue(
                        project_key=project_key,
                        summary=summary,
                        description=description,
                        issue_type=issue_type,
                        priority=priority
                    ))
                    
                    # Check if there was an error
                    if "error" in result:
                        return {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Error creating JIRA Issue: {result['error']}\nIssue data attempted: {json.dumps(result.get('issue_data', {}), indent=2)}"
                                }
                            ]
                        }
                    else:
                        return {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"✅ Created JIRA Issue Successfully!\n\nKey: {result.get('key', 'Unknown')}\nID: {result.get('id', 'Unknown')}\nSelf: {result.get('self', 'Unknown')}\n\nFull Response:\n{json.dumps(result, indent=2)}"
                                }
                            ]
                        }
                
                elif tool_name == "jira_search_issues":
                    jql = arguments.get("jql")
                    max_results = arguments.get("max_results", 10)
                    
                    result = loop.run_until_complete(jira_client.search_issues(jql=jql, max_results=max_results))
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"JIRA Search Results:\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jira_get_issue":
                    issue_key = arguments.get("issue_key")
                    
                    result = loop.run_until_complete(jira_client.get_issue(issue_key=issue_key))
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"JIRA Issue Details:\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jira_add_comment":
                    issue_key = arguments.get("issue_key")
                    comment = arguments.get("comment")
                    
                    result = loop.run_until_complete(jira_client.add_comment(issue_key=issue_key, comment=comment))
                    
                    if result.get("error"):
                        return {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"❌ Error adding comment to JIRA Issue {issue_key}: {result.get('error')}"
                                }
                            ]
                        }
                    else:
                        return {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"✅ Comment added successfully to JIRA Issue {issue_key}!\n\nComment ID: {result.get('comment_id', 'Unknown')}\nAuthor: {result.get('author', 'Unknown')}\nCreated: {result.get('created', 'Unknown')}\n\nComment: {result.get('comment', '')}"
                                }
                            ]
                        }
                
                else:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Unknown tool: {tool_name}"
                            }
                        ]
                    }
            finally:
                loop.close()
                
        except Exception as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error calling {tool_name}: {str(e)}"
                    }
                ]
            }

if __name__ == "__main__":
    # Test the server
    server = JiraMCPServer()
    print("Tools:", json.dumps(server.list_tools(), indent=2))
