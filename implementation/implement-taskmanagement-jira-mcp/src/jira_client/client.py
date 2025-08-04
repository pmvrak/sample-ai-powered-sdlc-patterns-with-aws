# src/jira_client/client.py
import asyncio
import sys
import os
from typing import Dict, List, Optional, Any
from atlassian import Jira
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Settings:
    """Simple settings class"""
    jira_url = os.getenv("JIRA_URL", "")
    jira_username = os.getenv("JIRA_USERNAME", "")
    jira_api_token = os.getenv("JIRA_API_TOKEN", "")

settings = Settings()

def validate_jira_config() -> bool:
    """Validate that all required JIRA configuration is present"""
    required_fields = [settings.jira_url, settings.jira_username, settings.jira_api_token]
    return all(field.strip() for field in required_fields)

class JiraClient:
    def __init__(self):
        """Initialize JIRA client with credentials from settings"""
        self.jira = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the JIRA client connection"""
        try:
            self.jira = Jira(
                url=settings.jira_url,
                username=settings.jira_username,
                password=settings.jira_api_token,  # API token goes in password field
                cloud=True  # Important for Atlassian Cloud
            )
            logger.info(f"JIRA client initialized for: {settings.jira_url}")
        except Exception as e:
            logger.error(f"Failed to initialize JIRA client: {e}")
            raise
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test the JIRA connection and return server info"""
        try:
            # Run in thread pool since atlassian-python-api is synchronous
            loop = asyncio.get_event_loop()
            server_info = await loop.run_in_executor(
                None, 
                self.jira.get_server_info
            )
            logger.info("JIRA connection test successful")
            return {
                "status": "success",
                "server_info": server_info,
                "url": settings.jira_url
            }
        except Exception as e:
            logger.error(f"JIRA connection test failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "url": settings.jira_url
            }
    
    async def get_projects(self) -> List[Dict[str, Any]]:
        """Get all projects from JIRA"""
        try:
            loop = asyncio.get_event_loop()
            projects = await loop.run_in_executor(
                None,
                self.jira.projects
            )
            logger.info(f"Retrieved {len(projects)} projects")
            return projects
        except Exception as e:
            logger.error(f"Failed to get projects: {e}")
            raise
    
    async def search_issues(self, jql: str, max_results: int = 50, fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """Search issues using JQL"""
        try:
            loop = asyncio.get_event_loop()
            
            # Default fields if none specified
            if fields is None:
                fields = ['summary', 'status', 'assignee', 'created', 'updated', 'issuetype', 'priority']
            
            results = await loop.run_in_executor(
                None,
                lambda: self.jira.jql(jql, limit=max_results, fields=fields)
            )
            
            logger.info(f"JQL search returned {results.get('total', 0)} results")
            return results
        except Exception as e:
            logger.error(f"JQL search failed: {e}")
            raise
    
    async def get_issue(self, issue_key: str) -> Dict[str, Any]:
        """Get specific issue by key"""
        try:
            loop = asyncio.get_event_loop()
            issue = await loop.run_in_executor(
                None,
                lambda: self.jira.issue(issue_key)
            )
            logger.info(f"Retrieved issue: {issue_key}")
            return issue
        except Exception as e:
            logger.error(f"Failed to get issue {issue_key}: {e}")
            raise

    async def create_issue(self, project_key: str, summary: str, description: str = "", 
                          issue_type: str = "Task", priority: str = None, 
                          assignee: Optional[str] = None) -> Dict[str, Any]:
        """Create a new JIRA issue"""
        try:
            # Prepare basic issue data (only required fields)
            issue_data = {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issue_type}
            }
            
            # Add description if provided
            if description:
                issue_data["description"] = description
            
            # Only add priority if explicitly provided and not None
            if priority:
                issue_data["priority"] = {"name": priority}
            
            # Only add assignee if provided
            if assignee:
                issue_data["assignee"] = {"name": assignee}
            
            logger.info(f"Creating issue with data: {issue_data}")
            
            # Create the issue using the synchronous method
            new_issue = self.jira.issue_create(fields=issue_data)
            
            logger.info(f"Created issue: {new_issue.get('key', 'Unknown')}")
            return new_issue
        except Exception as e:
            logger.error(f"Failed to create issue: {e}")
            # Return more detailed error information
            return {
                "error": str(e),
                "issue_data": issue_data if 'issue_data' in locals() else None
            }

    async def add_comment(self, issue_key: str, comment: str) -> Dict[str, Any]:
        """Add a comment to a JIRA issue"""
        try:
            logger.info(f"Adding comment to issue {issue_key}")
            
            # Add comment using the synchronous method
            result = self.jira.issue_add_comment(issue_key, comment)
            
            logger.info(f"Comment added successfully to {issue_key}")
            return {
                "success": True,
                "comment_id": result.get("id"),
                "issue_key": issue_key,
                "comment": comment,
                "created": result.get("created"),
                "author": result.get("author", {}).get("displayName", "Unknown")
            }
        except Exception as e:
            logger.error(f"Failed to add comment to {issue_key}: {e}")
            return {
                "error": str(e),
                "issue_key": issue_key,
                "comment": comment
            }

# Global JIRA client instance
jira_client = JiraClient()