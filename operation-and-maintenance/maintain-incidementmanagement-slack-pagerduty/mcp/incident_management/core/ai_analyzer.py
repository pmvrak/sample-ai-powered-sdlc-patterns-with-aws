"""
AI-powered incident analysis using AWS Bedrock integration.

This module provides intelligent analysis of incidents using the existing
Bedrock client integration from the Splunk MCP server.
"""

import json
import logging
import boto3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import asdict

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.incident import Incident, IncidentSeverity
from models.analysis import AnalysisResult, RiskLevel, IncidentCorrelation
from interfaces.base import BaseAnalyzer

logger = logging.getLogger(__name__)


class AIAnalyzer(BaseAnalyzer):
    """
    AI-powered incident analyzer that leverages AWS Bedrock for intelligent analysis.
    
    This class provides root cause analysis, severity classification, and incident
    correlation using structured prompts and the existing Bedrock integration.
    """
    
    def __init__(self, bedrock_region: str = 'us-east-1', model_id: str = 'anthropic.claude-3-haiku-20240307-v1:0'):
        """
        Initialize the AI analyzer with Bedrock client.
        
        Args:
            bedrock_region: AWS region for Bedrock service
            model_id: Bedrock model ID to use for analysis
        """
        self.bedrock_region = bedrock_region
        self.model_id = model_id
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=bedrock_region)
        self.knowledge_base = {}  # Simple in-memory knowledge base for now
        
        logger.info(f"Initialized AIAnalyzer with model {model_id} in region {bedrock_region}")
    
    async def analyze_incident(self, incident: Incident, log_data: Optional[List[Dict]] = None) -> AnalysisResult:
        """
        Perform comprehensive AI analysis of an incident.
        
        Args:
            incident: The incident to analyze
            log_data: Optional log data from Splunk for additional context
            
        Returns:
            AnalysisResult: Comprehensive analysis results
        """
        logger.info(f"Starting AI analysis for incident {incident.id}")
        
        try:
            # Prepare context for analysis
            context = self._prepare_analysis_context(incident, log_data)
            
            # Perform root cause analysis
            root_causes = await self._analyze_root_causes(context)
            
            # Classify severity
            severity_analysis = await self._classify_severity(context)
            
            # Generate remediation suggestions
            suggested_actions = await self._suggest_remediation(context, root_causes)
            
            # Find similar incidents
            similar_incidents = await self._find_similar_incidents(incident)
            
            # Assess risk level
            risk_assessment = self._assess_risk_level(incident, severity_analysis)
            
            # Estimate resolution time
            estimated_time = self._estimate_resolution_time(incident, root_causes)
            
            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(
                root_causes, severity_analysis, suggested_actions
            )
            
            # Create analysis result
            analysis_result = AnalysisResult(
                incident_id=incident.id,
                root_causes=root_causes,
                confidence_score=confidence_score,
                affected_components=self._extract_affected_components(context),
                suggested_actions=suggested_actions,
                similar_incidents=similar_incidents,
                risk_assessment=risk_assessment,
                estimated_resolution_time=estimated_time,
                metadata={
                    'model_id': self.model_id,
                    'analysis_method': 'bedrock_llm',
                    'log_data_available': log_data is not None,
                    'log_entries_count': len(log_data) if log_data else 0
                }
            )
            
            logger.info(f"Completed AI analysis for incident {incident.id} with confidence {confidence_score:.2f}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error during AI analysis for incident {incident.id}: {str(e)}")
            # Return a basic analysis result with error information
            return AnalysisResult(
                incident_id=incident.id,
                root_causes=[f"Analysis failed: {str(e)}"],
                confidence_score=0.1,
                affected_components=incident.affected_systems,
                suggested_actions=["Manual investigation required"],
                similar_incidents=[],
                risk_assessment=RiskLevel.HIGH,  # Conservative approach on error
                estimated_resolution_time=timedelta(hours=4),
                metadata={'error': str(e), 'analysis_failed': True}
            )
    
    async def correlate_incidents(self, incidents: List[Incident]) -> List[IncidentCorrelation]:
        """
        Correlate multiple incidents to identify relationships and reduce alert fatigue.
        
        Args:
            incidents: List of incidents to correlate
            
        Returns:
            List[IncidentCorrelation]: Correlation results
        """
        logger.info(f"Correlating {len(incidents)} incidents")
        
        if len(incidents) < 2:
            return []
        
        correlations = []
        processed_incidents = set()
        
        for i, primary_incident in enumerate(incidents):
            if primary_incident.id in processed_incidents:
                continue
                
            related_incidents = []
            correlation_factors = []
            
            for j, other_incident in enumerate(incidents[i+1:], i+1):
                if other_incident.id in processed_incidents:
                    continue
                    
                correlation_score, factors = await self._calculate_incident_correlation(
                    primary_incident, other_incident
                )
                
                if correlation_score > 0.6:  # Threshold for correlation
                    related_incidents.append(other_incident.id)
                    correlation_factors.extend(factors)
                    processed_incidents.add(other_incident.id)
            
            if related_incidents:
                correlation = IncidentCorrelation(
                    correlation_id=f"CORR-{primary_incident.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    primary_incident_id=primary_incident.id,
                    related_incident_ids=related_incidents,
                    correlation_score=min(1.0, len(related_incidents) * 0.3 + 0.4),
                    correlation_factors=list(set(correlation_factors))
                )
                correlations.append(correlation)
                processed_incidents.add(primary_incident.id)
        
        logger.info(f"Found {len(correlations)} incident correlations")
        return correlations
    
    async def learn_from_resolution(self, incident: Incident, resolution_data: Dict[str, Any]) -> None:
        """
        Learn from incident resolution to improve future analysis.
        
        Args:
            incident: The resolved incident
            resolution_data: Data about how the incident was resolved
        """
        logger.info(f"Learning from resolution of incident {incident.id}")
        
        try:
            # Extract learning points
            learning_prompt = self._create_learning_prompt(incident, resolution_data)
            learning_insights = await self._invoke_bedrock_model(learning_prompt)
            
            # Store in knowledge base (simplified for now)
            key = f"{incident.severity.value}_{','.join(incident.affected_systems)}"
            if key not in self.knowledge_base:
                self.knowledge_base[key] = []
            
            self.knowledge_base[key].append({
                'incident_id': incident.id,
                'resolution_time': resolution_data.get('resolution_time'),
                'successful_actions': resolution_data.get('successful_actions', []),
                'failed_actions': resolution_data.get('failed_actions', []),
                'insights': learning_insights,
                'timestamp': datetime.utcnow().isoformat()
            })
            
            logger.info(f"Stored learning insights for incident {incident.id}")
            
        except Exception as e:
            logger.error(f"Error learning from incident {incident.id}: {str(e)}")
    
    def _prepare_analysis_context(self, incident: Incident, log_data: Optional[List[Dict]]) -> Dict[str, Any]:
        """Prepare context data for AI analysis."""
        context = {
            'incident': asdict(incident),
            'log_data': log_data or [],
            'timestamp': datetime.utcnow().isoformat(),
            'affected_systems': incident.affected_systems,
            'severity': incident.severity.value,
            'source_query': incident.source_query
        }
        return context
    
    async def _analyze_root_causes(self, context: Dict[str, Any]) -> List[str]:
        """Analyze root causes using Bedrock LLM."""
        prompt = self._create_root_cause_prompt(context)
        
        try:
            response = await self._invoke_bedrock_model(prompt)
            root_causes = self._parse_root_causes_response(response)
            return root_causes
        except Exception as e:
            logger.error(f"Error in root cause analysis: {str(e)}")
            return ["Unable to determine root cause due to analysis error"]
    
    async def _classify_severity(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Classify incident severity using AI analysis."""
        prompt = self._create_severity_classification_prompt(context)
        
        try:
            response = await self._invoke_bedrock_model(prompt)
            severity_analysis = self._parse_severity_response(response)
            return severity_analysis
        except Exception as e:
            logger.error(f"Error in severity classification: {str(e)}")
            return {
                'severity': context['severity'],
                'confidence': 0.5,
                'reasoning': 'Classification failed, using original severity'
            }
    
    async def _suggest_remediation(self, context: Dict[str, Any], root_causes: List[str]) -> List[str]:
        """Generate remediation suggestions using AI."""
        prompt = self._create_remediation_prompt(context, root_causes)
        
        try:
            response = await self._invoke_bedrock_model(prompt)
            suggestions = self._parse_remediation_response(response)
            return suggestions
        except Exception as e:
            logger.error(f"Error generating remediation suggestions: {str(e)}")
            return ["Manual investigation and remediation required"]
    
    async def _find_similar_incidents(self, incident: Incident) -> List[str]:
        """Find similar incidents from knowledge base."""
        # Simplified similarity search
        similar = []
        key_pattern = f"{incident.severity.value}_"
        
        for key, incidents in self.knowledge_base.items():
            if key.startswith(key_pattern):
                for stored_incident in incidents[-3:]:  # Get last 3 similar incidents
                    similar.append(stored_incident['incident_id'])
        
        return similar[:5]  # Return top 5 similar incidents
    
    def _assess_risk_level(self, incident: Incident, severity_analysis: Dict[str, Any]) -> RiskLevel:
        """Assess risk level based on incident and analysis data."""
        severity_mapping = {
            IncidentSeverity.CRITICAL: RiskLevel.CRITICAL,
            IncidentSeverity.HIGH: RiskLevel.HIGH,
            IncidentSeverity.MEDIUM: RiskLevel.MEDIUM,
            IncidentSeverity.LOW: RiskLevel.LOW
        }
        
        base_risk = severity_mapping.get(incident.severity, RiskLevel.MEDIUM)
        
        # Adjust based on affected systems
        if len(incident.affected_systems) > 3:
            risk_levels = [RiskLevel.MINIMAL, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
            current_index = risk_levels.index(base_risk)
            if current_index < len(risk_levels) - 1:
                base_risk = risk_levels[current_index + 1]
        
        return base_risk
    
    def _estimate_resolution_time(self, incident: Incident, root_causes: List[str]) -> timedelta:
        """Estimate resolution time based on incident characteristics."""
        base_times = {
            IncidentSeverity.CRITICAL: timedelta(hours=1),
            IncidentSeverity.HIGH: timedelta(hours=4),
            IncidentSeverity.MEDIUM: timedelta(hours=8),
            IncidentSeverity.LOW: timedelta(hours=24)
        }
        
        base_time = base_times.get(incident.severity, timedelta(hours=8))
        
        # Adjust based on complexity (number of root causes and affected systems)
        complexity_factor = 1 + (len(root_causes) * 0.2) + (len(incident.affected_systems) * 0.1)
        
        return timedelta(seconds=base_time.total_seconds() * complexity_factor)
    
    def _calculate_confidence_score(self, root_causes: List[str], severity_analysis: Dict[str, Any], 
                                  suggested_actions: List[str]) -> float:
        """Calculate confidence score for the analysis."""
        base_confidence = 0.7
        
        # Adjust based on analysis completeness
        if len(root_causes) > 0 and "Unable to determine" not in str(root_causes):
            base_confidence += 0.1
        
        if severity_analysis.get('confidence', 0) > 0.8:
            base_confidence += 0.1
        
        if len(suggested_actions) > 1 and "Manual investigation" not in str(suggested_actions):
            base_confidence += 0.1
        
        return min(1.0, base_confidence)
    
    def _extract_affected_components(self, context: Dict[str, Any]) -> List[str]:
        """Extract affected components from context."""
        components = context.get('affected_systems', [])
        
        # Extract additional components from log data if available
        log_data = context.get('log_data', [])
        for log_entry in log_data:
            if isinstance(log_entry, dict):
                # Look for common component fields
                for field in ['service', 'component', 'host', 'source']:
                    if field in log_entry and log_entry[field] not in components:
                        components.append(log_entry[field])
        
        return components
    
    async def _calculate_incident_correlation(self, incident1: Incident, incident2: Incident) -> Tuple[float, List[str]]:
        """Calculate correlation score between two incidents."""
        score = 0.0
        factors = []
        
        # Time proximity (within 1 hour)
        time_diff = abs((incident1.created_at - incident2.created_at).total_seconds())
        if time_diff < 3600:  # 1 hour
            score += 0.3
            factors.append("temporal_proximity")
        
        # Affected systems overlap
        common_systems = set(incident1.affected_systems) & set(incident2.affected_systems)
        if common_systems:
            score += 0.4 * (len(common_systems) / max(len(incident1.affected_systems), len(incident2.affected_systems)))
            factors.append("common_affected_systems")
        
        # Similar severity
        if incident1.severity == incident2.severity:
            score += 0.2
            factors.append("similar_severity")
        
        # Similar source queries (simplified check)
        if incident1.source_query and incident2.source_query:
            query_similarity = len(set(incident1.source_query.split()) & set(incident2.source_query.split()))
            if query_similarity > 2:
                score += 0.1
                factors.append("similar_queries")
        
        return min(1.0, score), factors
    
    async def _invoke_bedrock_model(self, prompt: str) -> str:
        """Invoke Bedrock model with the given prompt."""
        try:
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            response = self.bedrock_client.invoke_model(
                body=json.dumps(body),
                modelId=self.model_id,
                accept='application/json',
                contentType='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']
            
        except Exception as e:
            logger.error(f"Error invoking Bedrock model: {str(e)}")
            raise
    
    def _create_root_cause_prompt(self, context: Dict[str, Any]) -> str:
        """Create prompt for root cause analysis."""
        return f"""
Analyze the following incident data and identify the most likely root causes:

Incident Details:
- Title: {context['incident']['title']}
- Description: {context['incident']['description']}
- Severity: {context['incident']['severity']}
- Affected Systems: {', '.join(context['incident']['affected_systems'])}
- Source Query: {context['incident']['source_query']}

Log Data Summary:
- Number of log entries: {len(context['log_data'])}
- Sample entries: {json.dumps(context['log_data'][:3], indent=2) if context['log_data'] else 'No log data available'}

Please provide:
1. Top 3 most likely root causes
2. Brief explanation for each cause
3. Confidence level for each cause

Format your response as a JSON array of objects with 'cause', 'explanation', and 'confidence' fields.
"""
    
    def _create_severity_classification_prompt(self, context: Dict[str, Any]) -> str:
        """Create prompt for severity classification."""
        return f"""
Analyze the following incident and classify its severity level:

Incident Details:
- Title: {context['incident']['title']}
- Description: {context['incident']['description']}
- Current Severity: {context['incident']['severity']}
- Affected Systems: {', '.join(context['incident']['affected_systems'])}
- Log Data Available: {len(context['log_data']) > 0}

Severity Levels:
- CRITICAL: System down, major service outage, data loss
- HIGH: Significant performance degradation, partial service outage
- MEDIUM: Minor performance issues, non-critical functionality affected
- LOW: Cosmetic issues, minimal impact

Please provide:
1. Recommended severity level
2. Confidence score (0.0-1.0)
3. Reasoning for the classification

Format as JSON with 'severity', 'confidence', and 'reasoning' fields.
"""
    
    def _create_remediation_prompt(self, context: Dict[str, Any], root_causes: List[str]) -> str:
        """Create prompt for remediation suggestions."""
        return f"""
Based on the incident analysis and identified root causes, suggest remediation actions:

Incident Details:
- Title: {context['incident']['title']}
- Severity: {context['incident']['severity']}
- Affected Systems: {', '.join(context['incident']['affected_systems'])}

Root Causes:
{json.dumps(root_causes, indent=2)}

Please provide:
1. Immediate actions to mitigate the issue
2. Short-term fixes to resolve the problem
3. Long-term preventive measures
4. Priority order for actions

Format as a JSON array of action strings, ordered by priority.
"""
    
    def _create_learning_prompt(self, incident: Incident, resolution_data: Dict[str, Any]) -> str:
        """Create prompt for learning from resolution."""
        return f"""
Analyze this resolved incident to extract learning insights:

Incident:
- ID: {incident.id}
- Title: {incident.title}
- Severity: {incident.severity.value}
- Affected Systems: {', '.join(incident.affected_systems)}

Resolution Data:
{json.dumps(resolution_data, indent=2)}

Please identify:
1. Key success factors in the resolution
2. What could have been done faster/better
3. Patterns that could help with similar future incidents
4. Preventive measures to avoid recurrence

Format as structured insights for future reference.
"""
    
    def _parse_root_causes_response(self, response: str) -> List[str]:
        """Parse root causes from LLM response."""
        try:
            # Try to parse as JSON first
            causes_data = json.loads(response)
            if isinstance(causes_data, list):
                return [item.get('cause', str(item)) for item in causes_data]
            else:
                return [str(causes_data)]
        except json.JSONDecodeError:
            # Fallback to text parsing
            lines = response.strip().split('\n')
            causes = []
            for line in lines:
                if line.strip() and not line.startswith('#'):
                    causes.append(line.strip())
            return causes[:3]  # Limit to top 3
    
    def _parse_severity_response(self, response: str) -> Dict[str, Any]:
        """Parse severity classification from LLM response."""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback parsing
            return {
                'severity': 'medium',
                'confidence': 0.5,
                'reasoning': 'Failed to parse AI response'
            }
    
    def _parse_remediation_response(self, response: str) -> List[str]:
        """Parse remediation suggestions from LLM response."""
        try:
            suggestions = json.loads(response)
            if isinstance(suggestions, list):
                return suggestions
            else:
                return [str(suggestions)]
        except json.JSONDecodeError:
            # Fallback to text parsing
            lines = response.strip().split('\n')
            suggestions = []
            for line in lines:
                if line.strip() and not line.startswith('#'):
                    suggestions.append(line.strip())
            return suggestions    
    
    def _prepare_analysis_context(self, incident: Incident, log_data: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Prepare context for AI analysis"""
        context = {
            'incident': asdict(incident),
            'log_data': log_data or [],
            'timestamp': datetime.utcnow().isoformat(),
            'affected_systems': incident.affected_systems,
            'severity': incident.severity.value,
            'status': incident.status.value,
            'description': incident.description,
            'tags': incident.tags
        }
        return context
    
