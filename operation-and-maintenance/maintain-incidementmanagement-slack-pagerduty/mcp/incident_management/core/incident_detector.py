"""
AI-powered incident detection engine that analyzes Splunk data for anomalies and incidents.
Integrates with existing Splunk MCP server tools for data retrieval.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from ..models.incident import Incident, IncidentSeverity, IncidentStatus
from ..interfaces.base import BaseIncidentManager

logger = logging.getLogger(__name__)


@dataclass
class DetectionRule:
    """Configuration for incident detection rule"""
    name: str
    query: str
    severity: IncidentSeverity
    description: str
    threshold: int = 1
    time_window: str = "5m"
    correlation_fields: List[str] = None
    tags: List[str] = None
    
    def __post_init__(self):
        if self.correlation_fields is None:
            self.correlation_fields = []
        if self.tags is None:
            self.tags = []


@dataclass
class IncidentCorrelation:
    """Represents correlation between incidents"""
    primary_incident_id: str
    related_incident_ids: List[str]
    correlation_score: float
    correlation_reason: str

class IncidentDetector(BaseIncidentManager):
    """
    AI-powered incident detection using Splunk data analysis.
    Integrates with existing Splunk MCP server tools for data retrieval.
    """
    
    def __init__(self, splunk_tool_client=None, bedrock_client=None):
        """
        Initialize incident detector with existing MCP tool clients.
        
        Args:
            splunk_tool_client: Client that can call existing Splunk MCP tools
            bedrock_client: AWS Bedrock client for AI analysis
        """
        self.splunk_tool_client = splunk_tool_client
        self.bedrock_client = bedrock_client
        self.detection_rules = self._load_detection_rules()
        self.active_incidents = {}
        self.correlation_window = timedelta(minutes=30)  # Time window for incident correlation
        
    def _load_detection_rules(self) -> Dict[str, DetectionRule]:
        """Load configurable incident detection rules and patterns"""
        rules = {
            "error_spike": DetectionRule(
                name="error_spike",
                query="search index=main sourcetype=aws:cloudtrail errorCode!=success | bucket _time span=5m | stats count by _time | where count > 50",
                severity=IncidentSeverity.HIGH,
                description="High error rate detected in CloudTrail logs",
                threshold=50,
                time_window="5m",
                correlation_fields=["eventSource", "errorCode"],
                tags=["aws", "cloudtrail", "errors"]
            ),
            "failed_logins": DetectionRule(
                name="failed_logins",
                query="search index=main sourcetype=aws:cloudtrail eventName=ConsoleLogin errorCode=SigninFailure | bucket _time span=10m | stats count by _time, sourceIPAddress | where count > 10",
                severity=IncidentSeverity.CRITICAL,
                description="Multiple failed login attempts detected",
                threshold=10,
                time_window="10m",
                correlation_fields=["sourceIPAddress", "userIdentity.type"],
                tags=["security", "authentication", "aws"]
            ),
            "service_unavailable": DetectionRule(
                name="service_unavailable",
                query="search index=main sourcetype=aws:elb:accesslogs response_code=503 | bucket _time span=5m | stats count by _time | where count > 20",
                severity=IncidentSeverity.CRITICAL,
                description="Service unavailability detected in ELB logs",
                threshold=20,
                time_window="5m",
                correlation_fields=["elb", "target_ip"],
                tags=["availability", "elb", "service"]
            ),
            "unusual_data_transfer": DetectionRule(
                name="unusual_data_transfer",
                query="search index=main sourcetype=aws:cloudwatchlogs:vpcflow action=ACCEPT | stats sum(bytes) as total_bytes by srcaddr | where total_bytes > 1000000000",
                severity=IncidentSeverity.MEDIUM,
                description="Unusual data transfer volume detected",
                threshold=1000000000,
                time_window="1h",
                correlation_fields=["srcaddr", "dstaddr"],
                tags=["network", "data-transfer", "vpc"]
            ),
            "high_cpu_usage": DetectionRule(
                name="high_cpu_usage",
                query="search index=main sourcetype=aws:cloudwatch:metric MetricName=CPUUtilization | stats avg(Average) as avg_cpu by InstanceId | where avg_cpu > 90",
                severity=IncidentSeverity.HIGH,
                description="High CPU utilization detected on EC2 instances",
                threshold=90,
                time_window="15m",
                correlation_fields=["InstanceId", "AutoScalingGroupName"],
                tags=["performance", "ec2", "cpu"]
            ),
            "disk_space_low": DetectionRule(
                name="disk_space_low",
                query="search index=main sourcetype=linux:df | eval usage_pct=round((used/size)*100,2) | where usage_pct > 85",
                severity=IncidentSeverity.MEDIUM,
                description="Low disk space detected on systems",
                threshold=85,
                time_window="10m",
                correlation_fields=["host", "mount"],
                tags=["storage", "disk", "capacity"]
            )
        }
        return rules
    
    async def detect_incidents(self) -> List[Incident]:
        """
        Run incident detection across all configured rules.
        Implements Requirements 1.1, 1.3, 7.4
        """
        detected_incidents = []
        
        for rule_name, rule_config in self.detection_rules.items():
            try:
                logger.info(f"Running detection rule: {rule_name}")
                results = await self._execute_detection_query(rule_config.query)
                
                if results and len(results) > 0:
                    # Check if results exceed threshold
                    if self._check_threshold(results, rule_config):
                        incident = await self._create_incident_from_results(
                            rule_name, rule_config, results
                        )
                        if incident:
                            detected_incidents.append(incident)
                            logger.info(f"Incident detected: {incident.id} from rule {rule_name}")
                        
            except Exception as e:
                logger.error(f"Error running detection rule {rule_name}: {str(e)}")
        
        # Correlate incidents to group related events (Requirement 1.3)
        if detected_incidents:
            correlated_incidents = await self._correlate_incidents(detected_incidents)
            return correlated_incidents
                
        return detected_incidents
    
    async def _execute_detection_query(self, query: str) -> List[Dict]:
        """
        Execute Splunk query for incident detection using existing MCP tools.
        Integrates with the existing get_splunk_results tool.
        """
        try:
            if self.splunk_tool_client:
                # Call the existing get_splunk_results tool from the MCP server
                results = await self._call_splunk_search(query)
                if isinstance(results, str) and "Query did not return any results" in results:
                    return []
                elif isinstance(results, list):
                    return results
                else:
                    logger.warning(f"Unexpected result type from Splunk query: {type(results)}")
                    return []
            else:
                logger.warning("No Splunk tool client available, returning empty results")
                return []
        except Exception as e:
            logger.error(f"Error executing detection query: {str(e)}")
            return []
    
    async def _call_splunk_search(self, query: str) -> Any:
        """
        Call the existing Splunk MCP tool get_splunk_results.
        This integrates with the existing MCP server infrastructure.
        """
        try:
            if self.splunk_tool_client:
                # This would be the actual call to the MCP tool
                # For now, we'll simulate the interface
                return await self.splunk_tool_client.get_splunk_results(query)
            else:
                # Fallback for testing without actual Splunk connection
                logger.warning("No Splunk tool client available")
                return []
        except Exception as e:
            logger.error(f"Error calling Splunk search tool: {str(e)}")
            return []
    
    def _handle_no_data_fallback(self, query: str) -> List[Dict]:
        """Handle cases where no data source is available"""
        logger.warning(f"❌ No data source available for query: {query}")
        logger.warning("❌ Check Splunk connectivity and configuration")
        return []
    
    def _check_threshold(self, results: List[Dict], rule_config: DetectionRule) -> bool:
        """Check if detection results exceed the configured threshold"""
        try:
            if not results:
                return False
            
            # For count-based rules, check if any result exceeds threshold
            for result in results:
                if 'count' in result and int(result['count']) >= rule_config.threshold:
                    return True
                # For percentage-based rules (like CPU usage)
                if 'avg_cpu' in result and float(result['avg_cpu']) >= rule_config.threshold:
                    return True
                if 'usage_pct' in result and float(result['usage_pct']) >= rule_config.threshold:
                    return True
                if 'total_bytes' in result and int(result['total_bytes']) >= rule_config.threshold:
                    return True
            
            # If no specific threshold field found, assume threshold is met if we have results
            return len(results) >= rule_config.threshold
            
        except Exception as e:
            logger.error(f"Error checking threshold: {str(e)}")
            return False

    async def _create_incident_from_results(self, rule_name: str, rule_config: DetectionRule, results: List[Dict]) -> Optional[Incident]:
        """Create incident object from detection results"""
        try:
            # Generate unique incident ID
            incident_id = Incident.generate_incident_id()
            
            # Analyze results with AI to generate detailed description
            ai_analysis = await self._analyze_incident_with_ai(rule_name, results)
            
            # Extract affected systems from results
            affected_systems = self._extract_affected_systems(results, rule_config.correlation_fields)
            
            # Create comprehensive title and description
            title = f"{rule_config.description} - {len(results)} events detected"
            description = ai_analysis.get("description", rule_config.description)
            
            # Combine rule tags with AI-generated tags
            all_tags = list(set(rule_config.tags + ai_analysis.get("tags", [rule_name])))
            
            incident = Incident(
                id=incident_id,
                title=title,
                description=description,
                severity=rule_config.severity,
                status=IncidentStatus.DETECTED,
                source_query=rule_config.query,
                affected_systems=affected_systems,
                tags=all_tags
            )
            
            # Add AI analysis metadata
            if ai_analysis:
                incident.set_metadata('ai_analysis', ai_analysis)
                incident.set_metadata('detection_rule', rule_name)
                incident.set_metadata('event_count', len(results))
                incident.set_metadata('detection_time', datetime.utcnow().isoformat())
            
            # Store in active incidents
            self.active_incidents[incident_id] = incident
            
            logger.info(f"Created incident: {incident_id} with {len(results)} events")
            return incident
            
        except Exception as e:
            logger.error(f"Error creating incident: {str(e)}")
            return None
    
    async def _correlate_incidents(self, incidents: List[Incident]) -> List[Incident]:
        """
        Correlate incidents to group related events and reduce alert fatigue.
        Implements Requirement 1.3 - incident correlation logic.
        """
        if len(incidents) <= 1:
            return incidents
        
        try:
            correlated_incidents = []
            processed_incident_ids = set()
            
            for incident in incidents:
                if incident.id in processed_incident_ids:
                    continue
                
                # Find related incidents
                related_incidents = []
                for other_incident in incidents:
                    if (other_incident.id != incident.id and 
                        other_incident.id not in processed_incident_ids):
                        
                        correlation_score = self._calculate_correlation_score(incident, other_incident)
                        if correlation_score > 0.7:  # High correlation threshold
                            related_incidents.append(other_incident)
                            processed_incident_ids.add(other_incident.id)
                
                if related_incidents:
                    # Create a master incident that combines related incidents
                    master_incident = await self._merge_incidents(incident, related_incidents)
                    correlated_incidents.append(master_incident)
                    processed_incident_ids.add(incident.id)
                    logger.info(f"Correlated {len(related_incidents)} incidents into {master_incident.id}")
                else:
                    correlated_incidents.append(incident)
                    processed_incident_ids.add(incident.id)
            
            return correlated_incidents
            
        except Exception as e:
            logger.error(f"Error correlating incidents: {str(e)}")
            return incidents
    
    def _calculate_correlation_score(self, incident1: Incident, incident2: Incident) -> float:
        """Calculate correlation score between two incidents"""
        score = 0.0
        
        # Time proximity (incidents within correlation window)
        time_diff = abs((incident1.created_at - incident2.created_at).total_seconds())
        if time_diff <= self.correlation_window.total_seconds():
            score += 0.3
        
        # Affected systems overlap
        systems1 = set(incident1.affected_systems)
        systems2 = set(incident2.affected_systems)
        if systems1 and systems2:
            overlap = len(systems1.intersection(systems2))
            union = len(systems1.union(systems2))
            if union > 0:
                score += 0.4 * (overlap / union)
        
        # Tag similarity
        tags1 = set(incident1.tags)
        tags2 = set(incident2.tags)
        if tags1 and tags2:
            tag_overlap = len(tags1.intersection(tags2))
            tag_union = len(tags1.union(tags2))
            if tag_union > 0:
                score += 0.2 * (tag_overlap / tag_union)
        
        # Severity similarity
        if incident1.severity == incident2.severity:
            score += 0.1
        
        return min(score, 1.0)
    
    async def _merge_incidents(self, primary: Incident, related: List[Incident]) -> Incident:
        """Merge related incidents into a single master incident"""
        try:
            # Combine affected systems
            all_systems = set(primary.affected_systems)
            for incident in related:
                all_systems.update(incident.affected_systems)
            
            # Combine tags
            all_tags = set(primary.tags)
            for incident in related:
                all_tags.update(incident.tags)
            
            # Create merged title and description
            related_count = len(related)
            merged_title = f"{primary.title} (+ {related_count} related incidents)"
            
            merged_description = f"{primary.description}\n\nRelated incidents:\n"
            for incident in related:
                merged_description += f"- {incident.title}\n"
            
            # Use highest severity
            highest_severity = primary.severity
            for incident in related:
                if incident.severity.value == "critical":
                    highest_severity = IncidentSeverity.CRITICAL
                elif incident.severity.value == "high" and highest_severity.value != "critical":
                    highest_severity = IncidentSeverity.HIGH
            
            # Update primary incident
            primary.title = merged_title
            primary.description = merged_description
            primary.severity = highest_severity
            primary.affected_systems = list(all_systems)
            primary.tags = list(all_tags)
            
            # Add correlation metadata
            related_ids = [inc.id for inc in related]
            primary.set_metadata('correlated_incidents', related_ids)
            primary.set_metadata('correlation_count', related_count)
            primary.set_metadata('correlation_time', datetime.utcnow().isoformat())
            
            return primary
            
        except Exception as e:
            logger.error(f"Error merging incidents: {str(e)}")
            return primary

    async def _analyze_incident_with_ai(self, rule_name: str, results: List[Dict]) -> Dict:
        """Use AI to analyze incident data and provide insights"""
        try:
            # Prepare data for AI analysis
            analysis_prompt = f"""
            Analyze the following incident data for detection rule '{rule_name}':
            
            Sample Results (first 5 entries): {json.dumps(results[:5], indent=2)}
            Total Events: {len(results)}
            
            Please analyze this incident and provide:
            1. A detailed description of what happened
            2. Potential root causes based on the data patterns
            3. Suggested immediate actions for investigation/remediation
            4. Relevant tags for categorization
            5. Risk assessment (low/medium/high/critical)
            
            Respond in JSON format:
            {{
                "description": "detailed description of the incident",
                "root_causes": ["cause1", "cause2"],
                "immediate_actions": ["action1", "action2"],
                "tags": ["tag1", "tag2"],
                "risk_level": "medium",
                "confidence_score": 0.85
            }}
            """
            
            # Call Bedrock for analysis
            response = await self._call_bedrock_analysis(analysis_prompt)
            if response:
                try:
                    return json.loads(response)
                except json.JSONDecodeError:
                    logger.warning("AI response was not valid JSON, using fallback")
                    return self._create_fallback_analysis(rule_name, results)
            else:
                return self._create_fallback_analysis(rule_name, results)
            
        except Exception as e:
            logger.error(f"Error in AI analysis: {str(e)}")
            return self._create_fallback_analysis(rule_name, results)
    
    def _create_fallback_analysis(self, rule_name: str, results: List[Dict]) -> Dict:
        """Create fallback analysis when AI is unavailable"""
        return {
            "description": f"Incident detected by rule: {rule_name}. {len(results)} events detected requiring investigation.",
            "root_causes": ["Automated detection triggered", "Pattern threshold exceeded"],
            "immediate_actions": ["Review event details", "Check affected systems", "Investigate root cause"],
            "tags": [rule_name, "automated-detection"],
            "risk_level": "medium",
            "confidence_score": 0.6
        }
    
    async def _call_bedrock_analysis(self, prompt: str) -> str:
        """Call AWS Bedrock for AI analysis"""
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            })
            
            response = self.bedrock_client.invoke_model(
                body=body,
                modelId='anthropic.claude-3-sonnet-20240229-v1:0',
                accept='application/json',
                contentType='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']
            
        except Exception as e:
            logger.error(f"Error calling Bedrock: {str(e)}")
            return ""
    
    def _extract_affected_systems(self, results: List[Dict], correlation_fields: List[str] = None) -> List[str]:
        """Extract affected systems from query results using correlation fields"""
        systems = set()
        
        # Use correlation fields if provided
        if correlation_fields:
            for result in results:
                for field in correlation_fields:
                    if field in result and result[field]:
                        systems.add(f"{field}:{result[field]}")
        
        # Extract from common system identifier fields
        for result in results:
            # Standard system identifiers
            if 'host' in result and result['host']:
                systems.add(f"host:{result['host']}")
            if 'source' in result and result['source']:
                systems.add(f"source:{result['source']}")
            if 'eventSource' in result and result['eventSource']:
                systems.add(f"service:{result['eventSource']}")
            if 'sourceIPAddress' in result and result['sourceIPAddress']:
                systems.add(f"ip:{result['sourceIPAddress']}")
            if 'InstanceId' in result and result['InstanceId']:
                systems.add(f"instance:{result['InstanceId']}")
            if 'elb' in result and result['elb']:
                systems.add(f"elb:{result['elb']}")
            if 'target_ip' in result and result['target_ip']:
                systems.add(f"target:{result['target_ip']}")
                
        return list(systems)
    
    async def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Retrieve incident by ID"""
        return self.active_incidents.get(incident_id)
    
    async def update_incident(self, incident_id: str, **updates) -> bool:
        """Update incident with new information"""
        if incident_id in self.active_incidents:
            incident = self.active_incidents[incident_id]
            
            for key, value in updates.items():
                if hasattr(incident, key):
                    # Handle enum conversions
                    if key == 'status' and isinstance(value, str):
                        value = IncidentStatus(value)
                    elif key == 'severity' and isinstance(value, str):
                        value = IncidentSeverity(value)
                    setattr(incident, key, value)
            
            incident.updated_at = datetime.utcnow()
            return True
        return False
    
    async def get_active_incidents(self, filters: Optional[Dict] = None) -> List[Incident]:
        """Get all active incidents with optional filters"""
        active = [inc for inc in self.active_incidents.values() 
                 if inc.status not in [IncidentStatus.RESOLVED, IncidentStatus.CLOSED]]
        
        if filters:
            # Apply filters if provided
            if 'severity' in filters:
                active = [inc for inc in active if inc.severity == filters['severity']]
            if 'assigned_team' in filters:
                active = [inc for inc in active if inc.assigned_team == filters['assigned_team']]
            if 'tags' in filters:
                filter_tags = filters['tags'] if isinstance(filters['tags'], list) else [filters['tags']]
                active = [inc for inc in active if any(tag in inc.tags for tag in filter_tags)]
        
        return active
    
    async def create_incident(self, data: Dict) -> Incident:
        """Create a new incident from provided data"""
        incident = Incident(
            id=data.get('id', Incident.generate_incident_id()),
            title=data['title'],
            description=data['description'],
            severity=IncidentSeverity(data['severity']) if isinstance(data['severity'], str) else data['severity'],
            status=IncidentStatus(data.get('status', 'detected')) if isinstance(data.get('status'), str) else data.get('status', IncidentStatus.DETECTED),
            source_query=data['source_query'],
            affected_systems=data.get('affected_systems', []),
            assigned_team=data.get('assigned_team'),
            assigned_user=data.get('assigned_user'),
            tags=data.get('tags', [])
        )
        
        self.active_incidents[incident.id] = incident
        logger.info(f"Created incident: {incident.id}")
        return incident
    
    async def assign_incident(self, incident_id: str, team: str, user: Optional[str] = None) -> bool:
        """Assign incident to team/user"""
        if incident_id in self.active_incidents:
            incident = self.active_incidents[incident_id]
            incident.assign_to_team(team, user)
            logger.info(f"Assigned incident {incident_id} to team {team}, user {user}")
            return True
        return False
    
    async def resolve_incident(self, incident_id: str, resolution: str, resolved_by: str) -> bool:
        """Mark incident as resolved"""
        if incident_id in self.active_incidents:
            incident = self.active_incidents[incident_id]
            incident.update_status(IncidentStatus.RESOLVED)
            incident.set_metadata('resolution', resolution)
            incident.set_metadata('resolved_by', resolved_by)
            logger.info(f"Resolved incident {incident_id} by {resolved_by}")
            return True
        return False
    
    def add_detection_rule(self, rule: DetectionRule) -> bool:
        """Add a new configurable detection rule"""
        try:
            self.detection_rules[rule.name] = rule
            logger.info(f"Added detection rule: {rule.name}")
            return True
        except Exception as e:
            logger.error(f"Error adding detection rule: {str(e)}")
            return False
    
    def update_detection_rule(self, rule_name: str, rule: DetectionRule) -> bool:
        """Update an existing detection rule"""
        try:
            if rule_name in self.detection_rules:
                self.detection_rules[rule_name] = rule
                logger.info(f"Updated detection rule: {rule_name}")
                return True
            else:
                logger.warning(f"Detection rule not found: {rule_name}")
                return False
        except Exception as e:
            logger.error(f"Error updating detection rule: {str(e)}")
            return False
    
    def remove_detection_rule(self, rule_name: str) -> bool:
        """Remove a detection rule"""
        try:
            if rule_name in self.detection_rules:
                del self.detection_rules[rule_name]
                logger.info(f"Removed detection rule: {rule_name}")
                return True
            else:
                logger.warning(f"Detection rule not found: {rule_name}")
                return False
        except Exception as e:
            logger.error(f"Error removing detection rule: {str(e)}")
            return False
    
    def get_detection_rules(self) -> Dict[str, DetectionRule]:
        """Get all configured detection rules"""
        return self.detection_rules.copy()
    
    async def test_detection_rule(self, rule: DetectionRule) -> Dict[str, Any]:
        """Test a detection rule and return results without creating incidents"""
        try:
            logger.info(f"Testing detection rule: {rule.name}")
            results = await self._execute_detection_query(rule.query)
            
            test_result = {
                "rule_name": rule.name,
                "query": rule.query,
                "results_count": len(results) if results else 0,
                "threshold_met": False,
                "sample_results": results[:3] if results else [],
                "would_trigger": False
            }
            
            if results:
                test_result["threshold_met"] = self._check_threshold(results, rule)
                test_result["would_trigger"] = test_result["threshold_met"]
                
                if test_result["would_trigger"]:
                    # Simulate affected systems extraction
                    affected_systems = self._extract_affected_systems(results, rule.correlation_fields)
                    test_result["affected_systems"] = affected_systems
            
            return test_result
            
        except Exception as e:
            logger.error(f"Error testing detection rule: {str(e)}")
            return {
                "rule_name": rule.name,
                "error": str(e),
                "results_count": 0,
                "would_trigger": False
            }

    async def search_incidents(self, query: str, limit: int = 50) -> List[Incident]:
        """Search incidents by query"""
        results = []
        query_lower = query.lower()
        
        for incident in self.active_incidents.values():
            # Simple text search across title, description, and tags
            if (query_lower in incident.title.lower() or 
                query_lower in incident.description.lower() or
                any(query_lower in tag.lower() for tag in incident.tags)):
                results.append(incident)
                
                if len(results) >= limit:
                    break
        
        return results
    
    async def get_incident_statistics(self) -> Dict[str, Any]:
        """Get statistics about detected incidents"""
        try:
            total_incidents = len(self.active_incidents)
            
            # Count by status
            status_counts = {}
            for status in IncidentStatus:
                status_counts[status.value] = sum(1 for inc in self.active_incidents.values() 
                                                if inc.status == status)
            
            # Count by severity
            severity_counts = {}
            for severity in IncidentSeverity:
                severity_counts[severity.value] = sum(1 for inc in self.active_incidents.values() 
                                                    if inc.severity == severity)
            
            # Recent incidents (last 24 hours)
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            recent_incidents = sum(1 for inc in self.active_incidents.values() 
                                 if inc.created_at >= recent_cutoff)
            
            return {
                "total_incidents": total_incidents,
                "status_breakdown": status_counts,
                "severity_breakdown": severity_counts,
                "recent_incidents_24h": recent_incidents,
                "detection_rules_count": len(self.detection_rules),
                "last_detection_run": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting incident statistics: {str(e)}")
            return {"error": str(e)}