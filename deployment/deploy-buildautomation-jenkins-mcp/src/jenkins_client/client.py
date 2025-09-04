# src/jenkins_client/client.py
import asyncio
import sys
import os
from typing import Dict, List, Optional, Any
import requests
import json
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Settings:
    """Simple settings class"""
    jenkins_url = os.getenv("JENKINS_URL", "")
    jenkins_username = os.getenv("JENKINS_USERNAME", "")
    jenkins_api_token = os.getenv("JENKINS_API_TOKEN", "")

settings = Settings()

def validate_jenkins_config() -> bool:
    """Validate that all required Jenkins configuration is present"""
    required_fields = [settings.jenkins_url, settings.jenkins_username, settings.jenkins_api_token]
    return all(field.strip() for field in required_fields)

class JenkinsClient:
    def __init__(self):
        """Initialize Jenkins client with credentials from settings"""
        self.base_url = settings.jenkins_url.rstrip('/')
        self.auth = (settings.jenkins_username, settings.jenkins_api_token)
        self.session = requests.Session()
        self.session.auth = self.auth
        logger.info(f"Jenkins client initialized for: {self.base_url}")
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make authenticated request to Jenkins API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test Jenkins connection and get server info"""
        try:
            response = self._make_request('GET', '/api/json')
            data = response.json()
            return {
                "status": "success",
                "server_info": {
                    "version": data.get("version", "unknown"),
                    "url": self.base_url,
                    "user": settings.jenkins_username
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    async def list_jobs(self) -> List[Dict[str, Any]]:
        """List all Jenkins jobs"""
        try:
            response = self._make_request('GET', '/api/json?tree=jobs[name,url,color,buildable]')
            data = response.json()
            return data.get("jobs", [])
        except Exception as e:
            logger.error(f"Error listing jobs: {e}")
            raise
    
    async def get_job_info(self, job_name: str) -> Dict[str, Any]:
        """Get detailed information about a specific job"""
        try:
            response = self._make_request('GET', f'/job/{job_name}/api/json')
            return response.json()
        except Exception as e:
            logger.error(f"Error getting job info for {job_name}: {e}")
            raise
    
    async def trigger_build(self, job_name: str, parameters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Trigger a build for a job"""
        try:
            if parameters:
                endpoint = f'/job/{job_name}/buildWithParameters'
                response = self._make_request('POST', endpoint, data=parameters)
            else:
                endpoint = f'/job/{job_name}/build'
                response = self._make_request('POST', endpoint)
            
            return {
                "status": "success",
                "message": f"Build triggered for job: {job_name}",
                "queue_location": response.headers.get('Location', '')
            }
        except Exception as e:
            logger.error(f"Error triggering build for {job_name}: {e}")
            raise
    
    async def get_build_info(self, job_name: str, build_number: int) -> Dict[str, Any]:
        """Get information about a specific build"""
        try:
            response = self._make_request('GET', f'/job/{job_name}/{build_number}/api/json')
            return response.json()
        except Exception as e:
            logger.error(f"Error getting build info for {job_name}#{build_number}: {e}")
            raise
    
    async def get_build_log(self, job_name: str, build_number: int) -> str:
        """Get console log for a specific build"""
        try:
            response = self._make_request('GET', f'/job/{job_name}/{build_number}/consoleText')
            return response.text
        except Exception as e:
            logger.error(f"Error getting build log for {job_name}#{build_number}: {e}")
            raise
    
    async def list_builds(self, job_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent builds for a job"""
        try:
            response = self._make_request('GET', f'/job/{job_name}/api/json?tree=builds[number,url,result,timestamp,duration]{{0,{limit}}}')
            data = response.json()
            return data.get("builds", [])
        except Exception as e:
            logger.error(f"Error listing builds for {job_name}: {e}")
            raise
    
    async def get_queue_info(self) -> List[Dict[str, Any]]:
        """Get current build queue information"""
        try:
            response = self._make_request('GET', '/queue/api/json')
            data = response.json()
            return data.get("items", [])
        except Exception as e:
            logger.error(f"Error getting queue info: {e}")
            raise
    
    async def get_nodes(self) -> List[Dict[str, Any]]:
        """Get information about Jenkins nodes/agents"""
        try:
            response = self._make_request('GET', '/computer/api/json')
            data = response.json()
            return data.get("computer", [])
        except Exception as e:
            logger.error(f"Error getting nodes info: {e}")
            raise
    
    async def abort_build(self, job_name: str, build_number: int) -> Dict[str, Any]:
        """Abort a running build"""
        try:
            response = self._make_request('POST', f'/job/{job_name}/{build_number}/stop')
            return {
                "status": "success",
                "message": f"Build {job_name}#{build_number} aborted"
            }
        except Exception as e:
            logger.error(f"Error aborting build {job_name}#{build_number}: {e}")
            raise
    
    async def create_job(self, job_name: str, config_xml: str) -> Dict[str, Any]:
        """Create a new Jenkins job"""
        try:
            headers = {'Content-Type': 'application/xml'}
            response = self._make_request('POST', f'/createItem?name={job_name}', 
                                        data=config_xml, headers=headers)
            return {
                "status": "success",
                "message": f"Job '{job_name}' created successfully"
            }
        except Exception as e:
            logger.error(f"Error creating job {job_name}: {e}")
            raise

# Test function for direct execution
async def main():
    """Test the Jenkins client"""
    if not validate_jenkins_config():
        print("Error: Missing Jenkins configuration. Please check your .env file.")
        return
    
    client = JenkinsClient()
    
    # Test connection
    print("Testing Jenkins connection...")
    result = await client.test_connection()
    print(f"Connection test: {result}")
    
    # List jobs
    print("\nListing jobs...")
    jobs = await client.list_jobs()
    print(f"Found {len(jobs)} jobs")
    for job in jobs[:5]:  # Show first 5
        print(f"  - {job['name']} ({job['color']})")

if __name__ == "__main__":
    asyncio.run(main())
