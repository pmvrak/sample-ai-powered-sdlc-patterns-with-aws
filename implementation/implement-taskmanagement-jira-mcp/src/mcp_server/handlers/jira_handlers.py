# src/mcp_server/handlers/jira_handlers.py
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from jira_client.client import jira_client
from ..protocol import MCPResource, MCPTool

class JiraResourceHandler:
    """Handle JIRA resource operations"""
    
    def get_handlers(self) -> Dict[str, callable]:
        """Get resource handler functions"""
        return {
            'projects_list': self.list_projects,
            'projects_read': self.read_project,
            'issues_list': self.list_issues,
            'issues_read': self.read_issue,
        }
    
    async def list_projects(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """List JIRA projects as MCP resources"""
        try:
            projects = await jira_client.get_projects()
            resources = []
            
            for project in projects:
                resources.append({
                    "uri": f"jira://projects/{project['key']}",
                    "name": f"JIRA Project: {project['name']}",
                    "description": f"JIRA project {project['key']} - {project['name']}",
                    "mimeType": "application/json"
                })
            
            return resources
        except Exception as e:
            raise Exception(f"Failed to list projects: {e}")
    
    async def read_project(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read specific JIRA project"""
        uri = params.get('uri', '')
        project_key = uri.split('/')[-1] if '/' in uri else ''
        
        if not project_key:
            raise Exception("Invalid project URI")
        
        try:
            projects = await jira_client.get_projects()
            project = next((p for p in projects if p['key'] == project_key), None)
            
            if not project:
                raise Exception(f"Project {project_key} not found")
            
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": str(project)
                }]
            }
        except Exception as e:
            raise Exception(f"Failed to read project {project_key}: {e}")
    
    async def list_issues(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """List recent JIRA issues as MCP resources"""
        try:
            # Get recent issues across all projects
            jql = "ORDER BY updated DESC"
            issues_result = await jira_client.search_issues(jql, max_results=20)
            resources = []
            
            for issue in issues_result.get('issues', []):
                resources.append({
                    "uri": f"jira://issues/{issue['key']}",
                    "name": f"JIRA Issue: {issue['key']}",
                    "description": f"{issue['key']}: {issue['fields']['summary']}",
                    "mimeType": "application/json"
                })
            
            return resources
        except Exception as e:
            raise Exception(f"Failed to list issues: {e}")
    
    async def read_issue(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read specific JIRA issue"""
        uri = params.get('uri', '')
        issue_key = uri.split('/')[-1] if '/' in uri else ''
        
        if not issue_key:
            raise Exception("Invalid issue URI")
        
        try:
            issue = await jira_client.get_issue(issue_key)
            
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": str(issue)
                }]
            }
        except Exception as e:
            raise Exception(f"Failed to read issue {issue_key}: {e}")

class JiraToolHandler:
    """Handle JIRA tool operations"""
    
    def get_handlers(self) -> Dict[str, callable]:
        """Get tool handler functions"""
        return {
            'tools_list': self.list_tools,
            'search_issues_call': self.search_issues,
            'get_projects_call': self.get_projects,
        }
    
    async def list_tools(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """List available JIRA tools"""
        return [
            {
                "name": "search_issues",
                "description": "Search JIRA issues using JQL query",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "jql": {
                            "type": "string",
                            "description": "JQL query to search issues"
                        },
                        "maxResults": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 20
                        }
                    },
                    "required": ["jql"]
                }
            },
            {
                "name": "get_projects",
                "description": "Get all JIRA projects",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    
    async def search_issues(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search JIRA issues using JQL"""
        jql = params.get('arguments', {}).get('jql', '')
        max_results = params.get('arguments', {}).get('maxResults', 20)
        
        if not jql:
            raise Exception("JQL query is required")
        
        try:
            results = await jira_client.search_issues(jql, max_results=max_results)
            
            return {
                "content": [{
                    "type": "text",
                    "text": f"Found {results.get('total', 0)} issues matching query: {jql}\n\n" +
                           "\n".join([
                               f"• {issue['key']}: {issue['fields']['summary']}"
                               for issue in results.get('issues', [])
                           ])
                }]
            }
        except Exception as e:
            raise Exception(f"Failed to search issues: {e}")
    
    async def get_projects(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get all JIRA projects"""
        try:
            projects = await jira_client.get_projects()
            
            return {
                "content": [{
                    "type": "text",
                    "text": f"Found {len(projects)} JIRA projects:\n\n" +
                           "\n".join([
                               f"• {project['key']}: {project['name']}"
                               for project in projects
                           ])
                }]
            }
        except Exception as e:
            raise Exception(f"Failed to get projects: {e}")