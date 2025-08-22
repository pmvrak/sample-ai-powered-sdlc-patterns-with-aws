"""
Incident routing engine for intelligent team assignment.
"""

import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from ..models.incident import Incident, IncidentSeverity
from ..interfaces.base import BaseRouter

logger = logging.getLogger(__name__)


class SkillLevel(Enum):
    """Skill proficiency levels"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class TeamStatus(Enum):
    """Team availability status"""
    AVAILABLE = "available"
    BUSY = "busy"
    OVERLOADED = "overloaded"
    OFFLINE = "offline"


@dataclass
class TeamMember:
    """Represents a team member with skills and availability"""
    id: str
    name: str
    team: str
    skills: Dict[str, SkillLevel] = field(default_factory=dict)
    current_incidents: List[str] = field(default_factory=list)
    max_concurrent_incidents: int = 3
    timezone: str = "UTC"
    is_available: bool = True
    last_activity: Optional[datetime] = None
    
    @property
    def workload_percentage(self) -> float:
        """Calculate current workload as percentage of capacity"""
        return (len(self.current_incidents) / self.max_concurrent_incidents) * 100
    
    @property
    def is_overloaded(self) -> bool:
        """Check if member is at or over capacity"""
        return len(self.current_incidents) >= self.max_concurrent_incidents
    
    def has_skill(self, skill: str, min_level: SkillLevel = SkillLevel.BEGINNER) -> bool:
        """Check if member has required skill at minimum level"""
        member_skill = self.skills.get(skill)
        if not member_skill:
            return False
        
        skill_levels = [SkillLevel.BEGINNER, SkillLevel.INTERMEDIATE, SkillLevel.ADVANCED, SkillLevel.EXPERT]
        return skill_levels.index(member_skill) >= skill_levels.index(min_level)


@dataclass
class TeamCapacity:
    """Represents team capacity and current load"""
    team_name: str
    members: List[TeamMember] = field(default_factory=list)
    current_incidents: List[str] = field(default_factory=list)
    max_concurrent_incidents: int = 20
    status: TeamStatus = TeamStatus.AVAILABLE
    average_resolution_time: timedelta = field(default_factory=lambda: timedelta(hours=2))
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def available_members(self) -> List[TeamMember]:
        """Get list of available team members"""
        return [member for member in self.members if member.is_available and not member.is_overloaded]
    
    @property
    def total_capacity(self) -> int:
        """Calculate total team capacity"""
        return sum(member.max_concurrent_incidents for member in self.members)
    
    @property
    def current_load(self) -> int:
        """Calculate current incident load"""
        return len(self.current_incidents)
    
    @property
    def load_percentage(self) -> float:
        """Calculate load as percentage of total capacity"""
        if self.total_capacity == 0:
            return 100.0
        return (self.current_load / self.total_capacity) * 100
    
    @property
    def is_overloaded(self) -> bool:
        """Check if team is overloaded"""
        return self.load_percentage >= 80.0 or self.status == TeamStatus.OVERLOADED
    
    def get_members_with_skill(self, skill: str, min_level: SkillLevel = SkillLevel.BEGINNER) -> List[TeamMember]:
        """Get available members with specific skill"""
        return [member for member in self.available_members if member.has_skill(skill, min_level)]
    
    def get_best_member_for_incident(self, incident: Incident) -> Optional[TeamMember]:
        """Find the best available member for an incident based on skills and workload"""
        available = self.available_members
        if not available:
            return None
        
        # Score members based on skills and current workload
        scored_members = []
        for member in available:
            score = self._calculate_member_score(member, incident)
            scored_members.append((member, score))
        
        # Sort by score (higher is better) and return best match
        scored_members.sort(key=lambda x: x[1], reverse=True)
        return scored_members[0][0] if scored_members else None
    
    def _calculate_member_score(self, member: TeamMember, incident: Incident) -> float:
        """Calculate how well a member matches an incident"""
        score = 0.0
        
        # Base score for availability
        score += 10.0
        
        # Penalty for current workload
        workload_penalty = member.workload_percentage / 10.0
        score -= workload_penalty
        
        # Bonus for relevant skills
        for tag in incident.tags:
            if member.has_skill(tag, SkillLevel.INTERMEDIATE):
                score += 20.0
            elif member.has_skill(tag, SkillLevel.BEGINNER):
                score += 10.0
        
        # Bonus for system expertise
        for system in incident.affected_systems:
            if member.has_skill(system, SkillLevel.INTERMEDIATE):
                score += 15.0
            elif member.has_skill(system, SkillLevel.BEGINNER):
                score += 7.0
        
        return max(score, 0.0)


@dataclass
class RoutingDecision:
    """Represents a routing decision with metadata"""
    incident_id: str
    target_team: str
    assigned_member: Optional[str] = None
    matched_rule: Optional[str] = None
    confidence: float = 0.0
    reasoning: List[str] = field(default_factory=list)
    escalated: bool = False
    escalation_reason: Optional[str] = None
    routing_timestamp: datetime = field(default_factory=datetime.utcnow)
    capacity_info: Optional[Dict[str, Any]] = None


class RoutingEngine(BaseRouter):
    """
    Advanced routing engine with skill-based routing, capacity tracking, and load balancing.
    
    Features:
    - Skill-based team and member assignment
    - Real-time capacity tracking and load balancing
    - Intelligent escalation path management
    - Configurable routing rules with priority scoring
    - Team performance metrics and optimization
    """
    
    def __init__(self):
        self.routing_rules = self._load_default_routing_rules()
        self.team_capacities: Dict[str, TeamCapacity] = {}
        self.escalation_paths = self._load_escalation_paths()
        self.skill_mappings = self._load_skill_mappings()
        self._initialize_default_teams()
    
    def _load_default_routing_rules(self) -> Dict[str, Any]:
        """Load default routing rules with skill requirements"""
        return {
            "rules": [
                {
                    "name": "critical_security_incidents",
                    "conditions": {
                        "tags": ["security", "breach", "unauthorized"],
                        "severity": ["critical"],
                        "required_skills": ["security", "incident-response"]
                    },
                    "target_team": "security-team",
                    "priority": 1,
                    "skill_level_required": SkillLevel.ADVANCED,
                    "max_response_time": timedelta(minutes=15)
                },
                {
                    "name": "high_security_incidents",
                    "conditions": {
                        "tags": ["security", "auth", "login", "vulnerability"],
                        "severity": ["high", "critical"],
                        "required_skills": ["security"]
                    },
                    "target_team": "security-team",
                    "priority": 2,
                    "skill_level_required": SkillLevel.INTERMEDIATE,
                    "max_response_time": timedelta(minutes=30)
                },
                {
                    "name": "critical_infrastructure_incidents",
                    "conditions": {
                        "affected_systems": ["aws", "ec2", "elb", "rds", "kubernetes"],
                        "severity": ["critical"],
                        "required_skills": ["aws", "infrastructure"]
                    },
                    "target_team": "infrastructure-team",
                    "priority": 3,
                    "skill_level_required": SkillLevel.ADVANCED,
                    "max_response_time": timedelta(minutes=20)
                },
                {
                    "name": "infrastructure_incidents", 
                    "conditions": {
                        "affected_systems": ["aws", "ec2", "elb", "rds", "docker", "kubernetes"],
                        "tags": ["infrastructure", "aws", "cloud"],
                        "required_skills": ["infrastructure"]
                    },
                    "target_team": "infrastructure-team",
                    "priority": 4,
                    "skill_level_required": SkillLevel.INTERMEDIATE,
                    "max_response_time": timedelta(hours=1)
                },
                {
                    "name": "database_incidents",
                    "conditions": {
                        "affected_systems": ["mysql", "postgresql", "mongodb", "redis"],
                        "tags": ["database", "db", "sql"],
                        "required_skills": ["database"]
                    },
                    "target_team": "database-team",
                    "priority": 5,
                    "skill_level_required": SkillLevel.INTERMEDIATE,
                    "max_response_time": timedelta(minutes=45)
                },
                {
                    "name": "application_incidents",
                    "conditions": {
                        "tags": ["application", "service", "api"],
                        "affected_systems": ["api", "web", "service", "microservice"],
                        "required_skills": ["development"]
                    },
                    "target_team": "application-team", 
                    "priority": 6,
                    "skill_level_required": SkillLevel.INTERMEDIATE,
                    "max_response_time": timedelta(hours=2)
                },
                {
                    "name": "network_incidents",
                    "conditions": {
                        "tags": ["network", "connectivity", "dns"],
                        "affected_systems": ["router", "switch", "firewall", "dns"],
                        "required_skills": ["networking"]
                    },
                    "target_team": "network-team",
                    "priority": 7,
                    "skill_level_required": SkillLevel.INTERMEDIATE,
                    "max_response_time": timedelta(hours=1)
                },
                {
                    "name": "default_routing",
                    "conditions": {},
                    "target_team": "ops-team",
                    "priority": 999,
                    "skill_level_required": SkillLevel.BEGINNER,
                    "max_response_time": timedelta(hours=4)
                }
            ]
        }
    
    def _load_escalation_paths(self) -> Dict[str, List[str]]:
        """Load escalation paths for teams with multiple levels"""
        return {
            "security-team": ["security-lead", "security-manager", "ops-team", "management"],
            "infrastructure-team": ["infrastructure-lead", "infrastructure-manager", "ops-team", "management"],
            "database-team": ["database-lead", "infrastructure-team", "ops-team"],
            "application-team": ["application-lead", "application-manager", "ops-team"],
            "network-team": ["network-lead", "infrastructure-team", "ops-team"],
            "ops-team": ["ops-lead", "ops-manager", "management"],
            "management": ["executive-team"]
        }
    
    def _load_skill_mappings(self) -> Dict[str, List[str]]:
        """Load mappings between incident characteristics and required skills"""
        return {
            "security": ["security", "incident-response", "forensics"],
            "infrastructure": ["aws", "kubernetes", "docker", "linux", "networking"],
            "database": ["mysql", "postgresql", "mongodb", "redis", "sql"],
            "application": ["development", "debugging", "api", "microservices"],
            "network": ["networking", "dns", "firewall", "routing"],
            "monitoring": ["observability", "metrics", "logging", "alerting"]
        }
    
    def _initialize_default_teams(self) -> None:
        """Initialize default team structures with sample members"""
        # Security team
        security_team = TeamCapacity(
            team_name="security-team",
            max_concurrent_incidents=15,
            average_resolution_time=timedelta(hours=1, minutes=30)
        )
        security_team.members = [
            TeamMember(
                id="sec001", name="Alice Security", team="security-team",
                skills={"security": SkillLevel.EXPERT, "incident-response": SkillLevel.ADVANCED, "forensics": SkillLevel.INTERMEDIATE},
                max_concurrent_incidents=4
            ),
            TeamMember(
                id="sec002", name="Bob SecOps", team="security-team",
                skills={"security": SkillLevel.ADVANCED, "incident-response": SkillLevel.ADVANCED, "aws": SkillLevel.INTERMEDIATE},
                max_concurrent_incidents=3
            )
        ]
        
        # Infrastructure team
        infra_team = TeamCapacity(
            team_name="infrastructure-team",
            max_concurrent_incidents=20,
            average_resolution_time=timedelta(hours=2)
        )
        infra_team.members = [
            TeamMember(
                id="inf001", name="Charlie Cloud", team="infrastructure-team",
                skills={"aws": SkillLevel.EXPERT, "kubernetes": SkillLevel.ADVANCED, "docker": SkillLevel.ADVANCED},
                max_concurrent_incidents=4
            ),
            TeamMember(
                id="inf002", name="Diana DevOps", team="infrastructure-team",
                skills={"infrastructure": SkillLevel.ADVANCED, "linux": SkillLevel.EXPERT, "networking": SkillLevel.INTERMEDIATE},
                max_concurrent_incidents=3
            )
        ]
        
        # Application team
        app_team = TeamCapacity(
            team_name="application-team",
            max_concurrent_incidents=25,
            average_resolution_time=timedelta(hours=3)
        )
        app_team.members = [
            TeamMember(
                id="app001", name="Eve Developer", team="application-team",
                skills={"development": SkillLevel.EXPERT, "api": SkillLevel.ADVANCED, "debugging": SkillLevel.ADVANCED},
                max_concurrent_incidents=5
            ),
            TeamMember(
                id="app002", name="Frank Fullstack", team="application-team",
                skills={"development": SkillLevel.ADVANCED, "microservices": SkillLevel.INTERMEDIATE, "database": SkillLevel.INTERMEDIATE},
                max_concurrent_incidents=4
            )
        ]
        
        # Database team
        db_team = TeamCapacity(
            team_name="database-team",
            max_concurrent_incidents=12,
            average_resolution_time=timedelta(hours=1, minutes=45)
        )
        db_team.members = [
            TeamMember(
                id="db001", name="Grace DBA", team="database-team",
                skills={"database": SkillLevel.EXPERT, "mysql": SkillLevel.EXPERT, "postgresql": SkillLevel.ADVANCED},
                max_concurrent_incidents=3
            )
        ]
        
        # Operations team (catch-all)
        ops_team = TeamCapacity(
            team_name="ops-team",
            max_concurrent_incidents=30,
            average_resolution_time=timedelta(hours=4)
        )
        ops_team.members = [
            TeamMember(
                id="ops001", name="Henry Ops", team="ops-team",
                skills={"monitoring": SkillLevel.ADVANCED, "troubleshooting": SkillLevel.EXPERT},
                max_concurrent_incidents=6
            ),
            TeamMember(
                id="ops002", name="Iris Support", team="ops-team",
                skills={"support": SkillLevel.ADVANCED, "documentation": SkillLevel.INTERMEDIATE},
                max_concurrent_incidents=5
            )
        ]
        
        # Store team capacities
        self.team_capacities = {
            "security-team": security_team,
            "infrastructure-team": infra_team,
            "application-team": app_team,
            "database-team": db_team,
            "ops-team": ops_team
        }
    
    async def route_incident(self, incident: Incident) -> RoutingDecision:
        """
        Route incident to appropriate team and member based on skills, capacity, and rules.
        
        This is the main routing method that:
        1. Finds the best matching routing rule
        2. Checks team capacity and availability
        3. Performs skill-based member assignment
        4. Handles load balancing and escalation
        """
        try:
            # Find matching routing rule with skill requirements
            matched_rule = self._find_best_matching_rule(incident)
            
            if not matched_rule:
                logger.warning(f"No routing rule matched for incident {incident.id}")
                matched_rule = self._get_default_rule()
            
            target_team = matched_rule["target_team"]
            reasoning = [f"Matched rule: {matched_rule['name']}"]
            
            # Get team capacity and check availability
            team_capacity = self.team_capacities.get(target_team)
            if not team_capacity:
                logger.error(f"Team {target_team} not found, falling back to ops-team")
                target_team = "ops-team"
                team_capacity = self.team_capacities.get("ops-team")
                reasoning.append("Fallback to ops-team due to missing team configuration")
            
            # Check if team is overloaded and needs escalation
            if team_capacity.is_overloaded:
                escalation_result = await self._handle_team_overload(incident, target_team, matched_rule)
                if escalation_result["escalated"]:
                    return escalation_result["decision"]
                reasoning.append("Team overloaded but no escalation path available")
            
            # Perform skill-based member assignment
            assigned_member = None
            required_skills = matched_rule.get("required_skills", [])
            skill_level = matched_rule.get("skill_level_required", SkillLevel.BEGINNER)
            
            if required_skills:
                assigned_member = self._find_best_member_for_skills(team_capacity, required_skills, skill_level, incident)
                if assigned_member:
                    reasoning.append(f"Assigned to {assigned_member.name} based on skills: {required_skills}")
                else:
                    reasoning.append(f"No member found with required skills: {required_skills}")
            
            # If no skill-based assignment, use load balancing
            if not assigned_member:
                assigned_member = team_capacity.get_best_member_for_incident(incident)
                if assigned_member:
                    reasoning.append(f"Load-balanced assignment to {assigned_member.name}")
            
            # Calculate routing confidence
            confidence = self._calculate_routing_confidence(incident, matched_rule, team_capacity, assigned_member)
            
            # Update team and member assignments
            if assigned_member:
                assigned_member.current_incidents.append(incident.id)
                incident.assign_to_team(target_team, assigned_member.id)
            else:
                incident.assign_to_team(target_team)
                reasoning.append("No specific member assigned - team will handle")
            
            team_capacity.current_incidents.append(incident.id)
            team_capacity.last_updated = datetime.utcnow()
            
            decision = RoutingDecision(
                incident_id=incident.id,
                target_team=target_team,
                assigned_member=assigned_member.id if assigned_member else None,
                matched_rule=matched_rule["name"],
                confidence=confidence,
                reasoning=reasoning,
                capacity_info=self._get_capacity_summary(team_capacity)
            )
            
            logger.info(f"Routed incident {incident.id} to team {target_team}" + 
                       (f" (member: {assigned_member.name})" if assigned_member else ""))
            
            return decision
            
        except Exception as e:
            logger.error(f"Error routing incident {incident.id}: {str(e)}")
            # Fallback routing decision
            return RoutingDecision(
                incident_id=incident.id,
                target_team="ops-team",
                confidence=0.1,
                reasoning=[f"Error in routing: {str(e)}", "Fallback to ops-team"]
            )
    
    def _find_best_matching_rule(self, incident: Incident) -> Optional[Dict[str, Any]]:
        """Find the best matching routing rule for an incident with skill consideration"""
        scored_rules = []
        
        for rule in self.routing_rules["rules"]:
            score = self._calculate_rule_match_score(incident, rule)
            if score > 0:
                scored_rules.append((rule, score))
        
        if not scored_rules:
            return None
        
        # Sort by priority (lower number = higher priority) then by score
        scored_rules.sort(key=lambda x: (x[0]["priority"], -x[1]))
        return scored_rules[0][0]
    
    def _find_best_member_for_skills(self, team_capacity: TeamCapacity, required_skills: List[str], 
                                   min_level: SkillLevel, incident: Incident) -> Optional[TeamMember]:
        """Find the best team member based on required skills"""
        suitable_members = []
        
        for member in team_capacity.available_members:
            skill_match_count = 0
            total_skill_level = 0
            
            for skill in required_skills:
                if member.has_skill(skill, min_level):
                    skill_match_count += 1
                    skill_levels = [SkillLevel.BEGINNER, SkillLevel.INTERMEDIATE, SkillLevel.ADVANCED, SkillLevel.EXPERT]
                    total_skill_level += skill_levels.index(member.skills.get(skill, SkillLevel.BEGINNER))
            
            if skill_match_count > 0:
                # Calculate member score based on skills and workload
                skill_score = (skill_match_count / len(required_skills)) * 100
                level_bonus = total_skill_level * 5
                workload_penalty = member.workload_percentage
                
                final_score = skill_score + level_bonus - workload_penalty
                suitable_members.append((member, final_score, skill_match_count))
        
        if not suitable_members:
            return None
        
        # Sort by skill match count first, then by score
        suitable_members.sort(key=lambda x: (-x[2], -x[1]))
        return suitable_members[0][0]
    
    async def _handle_team_overload(self, incident: Incident, overloaded_team: str, 
                                  matched_rule: Dict[str, Any]) -> Dict[str, Any]:
        """Handle team overload by attempting escalation or load balancing"""
        escalation_path = self.escalation_paths.get(overloaded_team, [])
        
        # Try to escalate to next available team in path
        for next_team in escalation_path:
            if next_team in self.team_capacities:
                next_capacity = self.team_capacities[next_team]
                if not next_capacity.is_overloaded:
                    logger.info(f"Escalating incident {incident.id} from {overloaded_team} to {next_team}")
                    
                    # Create escalated routing decision
                    decision = RoutingDecision(
                        incident_id=incident.id,
                        target_team=next_team,
                        matched_rule=matched_rule["name"],
                        confidence=0.7,  # Lower confidence due to escalation
                        reasoning=[
                            f"Original team {overloaded_team} overloaded",
                            f"Escalated to {next_team}",
                            f"Team capacity: {next_capacity.load_percentage:.1f}%"
                        ],
                        escalated=True,
                        escalation_reason="team_overloaded",
                        capacity_info=self._get_capacity_summary(next_capacity)
                    )
                    
                    return {"escalated": True, "decision": decision}
        
        # No escalation possible
        return {"escalated": False, "reason": "No available escalation path"}
    
    def _calculate_rule_match_score(self, incident: Incident, rule: Dict[str, Any]) -> int:
        """Calculate how well a rule matches an incident with enhanced scoring"""
        score = 0
        conditions = rule.get("conditions", {})
        
        # Check tag matches (higher weight for exact matches)
        if "tags" in conditions:
            rule_tags = conditions["tags"]
            matching_tags = set(incident.tags) & set(rule_tags)
            score += len(matching_tags) * 15
            
            # Bonus for high percentage of tag matches
            if len(rule_tags) > 0:
                match_percentage = len(matching_tags) / len(rule_tags)
                score += int(match_percentage * 10)
        
        # Check severity matches (critical severity gets highest priority)
        if "severity" in conditions:
            rule_severities = conditions["severity"]
            if incident.severity.value in rule_severities:
                severity_bonus = {"critical": 30, "high": 20, "medium": 10, "low": 5}
                score += severity_bonus.get(incident.severity.value, 5)
        
        # Check affected systems matches
        if "affected_systems" in conditions:
            rule_systems = conditions["affected_systems"]
            matching_systems = set(incident.affected_systems) & set(rule_systems)
            score += len(matching_systems) * 12
            
            # Bonus for system expertise match
            if len(rule_systems) > 0:
                match_percentage = len(matching_systems) / len(rule_systems)
                score += int(match_percentage * 8)
        
        # Check if team has required skills available
        if "required_skills" in conditions:
            required_skills = conditions["required_skills"]
            target_team = rule["target_team"]
            team_capacity = self.team_capacities.get(target_team)
            
            if team_capacity:
                skill_level = rule.get("skill_level_required", SkillLevel.BEGINNER)
                available_skilled_members = 0
                
                for skill in required_skills:
                    skilled_members = team_capacity.get_members_with_skill(skill, skill_level)
                    available_skilled_members += len(skilled_members)
                
                if available_skilled_members > 0:
                    score += available_skilled_members * 5
                else:
                    # Penalty if no one has required skills
                    score -= 10
        
        # Time-based urgency bonus
        max_response_time = rule.get("max_response_time")
        if max_response_time and incident.severity in [IncidentSeverity.CRITICAL, IncidentSeverity.HIGH]:
            # Bonus for rules with faster response time requirements
            if max_response_time <= timedelta(minutes=30):
                score += 15
            elif max_response_time <= timedelta(hours=1):
                score += 10
        
        # If no conditions specified, it's a catch-all rule with minimal score
        if not conditions:
            score = 1
        
        return max(score, 0)
    
    def _get_default_rule(self) -> Dict[str, Any]:
        """Get the default routing rule"""
        return {
            "name": "default_routing",
            "target_team": "ops-team",
            "priority": 999
        }
    
    def _calculate_routing_confidence(self, incident: Incident, rule: Dict[str, Any], 
                                    team_capacity: TeamCapacity, assigned_member: Optional[TeamMember]) -> float:
        """Calculate confidence score for routing decision based on multiple factors"""
        confidence = 0.3  # Base confidence
        
        # Rule specificity bonus
        if rule["name"] != "default_routing":
            confidence += 0.3
        
        # Incident data completeness
        if incident.tags:
            confidence += 0.1
        if incident.affected_systems:
            confidence += 0.1
        if incident.description and len(incident.description) > 20:
            confidence += 0.05
        
        # Team capacity factor
        if team_capacity:
            load_factor = 1.0 - (team_capacity.load_percentage / 100.0)
            confidence += load_factor * 0.2
        
        # Member assignment bonus
        if assigned_member:
            confidence += 0.15
            
            # Skill match bonus
            required_skills = rule.get("required_skills", [])
            if required_skills:
                skill_matches = sum(1 for skill in required_skills if assigned_member.has_skill(skill))
                skill_ratio = skill_matches / len(required_skills)
                confidence += skill_ratio * 0.1
        
        # Severity urgency factor
        severity_bonus = {
            IncidentSeverity.CRITICAL: 0.05,
            IncidentSeverity.HIGH: 0.03,
            IncidentSeverity.MEDIUM: 0.01,
            IncidentSeverity.LOW: 0.0
        }
        confidence += severity_bonus.get(incident.severity, 0.0)
        
        return min(confidence, 1.0)
    
    def _get_capacity_summary(self, team_capacity: TeamCapacity) -> Dict[str, Any]:
        """Get a summary of team capacity information"""
        return {
            "team": team_capacity.team_name,
            "current_incidents": len(team_capacity.current_incidents),
            "total_capacity": team_capacity.total_capacity,
            "load_percentage": round(team_capacity.load_percentage, 1),
            "available_members": len(team_capacity.available_members),
            "total_members": len(team_capacity.members),
            "status": team_capacity.status.value,
            "is_overloaded": team_capacity.is_overloaded,
            "average_resolution_time": str(team_capacity.average_resolution_time),
            "last_updated": team_capacity.last_updated.isoformat()
        }
    
    async def escalate_incident(self, incident: Incident, reason: str) -> bool:
        """
        Escalate incident to next level in escalation path.
        
        Enhanced escalation with capacity checking and skill requirements.
        """
        try:
            current_team = incident.assigned_team or "ops-team"
            escalation_path = self.escalation_paths.get(current_team, [])
            
            if not escalation_path:
                logger.warning(f"No escalation path found for team {current_team}")
                return False
            
            # Try each level in escalation path
            for next_level in escalation_path:
                if next_level in self.team_capacities:
                    next_team_capacity = self.team_capacities[next_level]
                    
                    # Check if escalation target has capacity
                    if not next_team_capacity.is_overloaded:
                        logger.info(f"Escalating incident {incident.id} from {current_team} to {next_level} - Reason: {reason}")
                        
                        # Remove from current team
                        if current_team in self.team_capacities:
                            current_capacity = self.team_capacities[current_team]
                            if incident.id in current_capacity.current_incidents:
                                current_capacity.current_incidents.remove(incident.id)
                            
                            # Remove from current member if assigned
                            if incident.assigned_user:
                                for member in current_capacity.members:
                                    if member.id == incident.assigned_user and incident.id in member.current_incidents:
                                        member.current_incidents.remove(incident.id)
                        
                        # Assign to escalation team
                        next_team_capacity.current_incidents.append(incident.id)
                        incident.assign_to_team(next_level)
                        
                        # Update incident metadata
                        incident.set_metadata("escalated_from", current_team)
                        incident.set_metadata("escalation_reason", reason)
                        incident.set_metadata("escalation_timestamp", datetime.utcnow().isoformat())
                        incident.set_metadata("escalation_level", incident.get_metadata("escalation_level", 0) + 1)
                        
                        return True
                    else:
                        logger.warning(f"Escalation target {next_level} is also overloaded, trying next level")
                        continue
                else:
                    # Handle escalation to non-team entities (like managers)
                    logger.info(f"Escalating incident {incident.id} to {next_level} (management level)")
                    incident.set_metadata("escalated_to_management", next_level)
                    incident.set_metadata("escalation_reason", reason)
                    incident.set_metadata("escalation_timestamp", datetime.utcnow().isoformat())
                    return True
            
            logger.error(f"All escalation paths exhausted for incident {incident.id}")
            return False
                
        except Exception as e:
            logger.error(f"Error escalating incident {incident.id}: {str(e)}")
            return False
    
    async def get_team_capacity(self, team: str) -> Dict[str, Any]:
        """Get comprehensive team capacity information"""
        team_capacity = self.team_capacities.get(team)
        
        if not team_capacity:
            logger.warning(f"Team {team} not found in capacity tracking")
            return {
                "team": team,
                "error": "Team not found",
                "current_incidents": 0,
                "total_capacity": 0,
                "available_members": 0,
                "overloaded": True,
                "last_updated": datetime.utcnow().isoformat()
            }
        
        # Calculate detailed capacity metrics
        member_details = []
        for member in team_capacity.members:
            member_details.append({
                "id": member.id,
                "name": member.name,
                "current_incidents": len(member.current_incidents),
                "max_capacity": member.max_concurrent_incidents,
                "workload_percentage": member.workload_percentage,
                "is_available": member.is_available,
                "is_overloaded": member.is_overloaded,
                "skills": {skill: level.value for skill, level in member.skills.items()}
            })
        
        return {
            "team": team,
            "current_incidents": len(team_capacity.current_incidents),
            "total_capacity": team_capacity.total_capacity,
            "load_percentage": round(team_capacity.load_percentage, 1),
            "available_members": len(team_capacity.available_members),
            "total_members": len(team_capacity.members),
            "status": team_capacity.status.value,
            "is_overloaded": team_capacity.is_overloaded,
            "average_resolution_time": str(team_capacity.average_resolution_time),
            "last_updated": team_capacity.last_updated.isoformat(),
            "member_details": member_details,
            "escalation_path": self.escalation_paths.get(team, [])
        }
    
    async def update_routing_rules(self, rules: Dict[str, Any]) -> bool:
        """Update routing configuration with enhanced validation"""
        try:
            # Validate rules format
            if "rules" not in rules:
                raise ValueError("Rules must contain 'rules' key")
            
            for rule in rules["rules"]:
                # Required fields
                if "name" not in rule or "target_team" not in rule:
                    raise ValueError("Each rule must have 'name' and 'target_team'")
                
                # Validate target team exists
                if rule["target_team"] not in self.team_capacities:
                    logger.warning(f"Target team {rule['target_team']} not found in capacity tracking")
                
                # Validate skill level if specified
                if "skill_level_required" in rule:
                    try:
                        SkillLevel(rule["skill_level_required"])
                    except ValueError:
                        raise ValueError(f"Invalid skill level: {rule['skill_level_required']}")
                
                # Validate priority
                if "priority" not in rule:
                    rule["priority"] = 999  # Default priority
                
                # Validate max_response_time format
                if "max_response_time" in rule and isinstance(rule["max_response_time"], str):
                    # Convert string to timedelta if needed
                    # This is a simplified parser - in production, use a proper time parser
                    pass
            
            self.routing_rules = rules
            logger.info(f"Updated routing rules successfully - {len(rules['rules'])} rules loaded")
            return True
            
        except Exception as e:
            logger.error(f"Error updating routing rules: {str(e)}")
            return False
    
    async def get_available_teams(self, incident_type: str = None) -> List[Dict[str, Any]]:
        """Get teams available for incident type with capacity information"""
        available_teams = []
        
        for team_name, team_capacity in self.team_capacities.items():
            team_info = {
                "name": team_name,
                "available": not team_capacity.is_overloaded,
                "load_percentage": team_capacity.load_percentage,
                "available_members": len(team_capacity.available_members),
                "total_members": len(team_capacity.members),
                "skills": set()
            }
            
            # Collect all skills available in the team
            for member in team_capacity.members:
                team_info["skills"].update(member.skills.keys())
            
            team_info["skills"] = list(team_info["skills"])
            available_teams.append(team_info)
        
        # Sort by availability and load
        available_teams.sort(key=lambda x: (not x["available"], x["load_percentage"]))
        return available_teams
    
    def add_team_member(self, team: str, member: TeamMember) -> bool:
        """Add a new member to a team"""
        try:
            if team not in self.team_capacities:
                logger.error(f"Team {team} not found")
                return False
            
            team_capacity = self.team_capacities[team]
            
            # Check if member already exists
            existing_ids = [m.id for m in team_capacity.members]
            if member.id in existing_ids:
                logger.warning(f"Member {member.id} already exists in team {team}")
                return False
            
            member.team = team  # Ensure team assignment is correct
            team_capacity.members.append(member)
            team_capacity.last_updated = datetime.utcnow()
            
            logger.info(f"Added member {member.name} to team {team}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding member to team {team}: {str(e)}")
            return False
    
    def remove_team_member(self, team: str, member_id: str) -> bool:
        """Remove a member from a team"""
        try:
            if team not in self.team_capacities:
                logger.error(f"Team {team} not found")
                return False
            
            team_capacity = self.team_capacities[team]
            
            # Find and remove member
            for i, member in enumerate(team_capacity.members):
                if member.id == member_id:
                    # Reassign any current incidents
                    if member.current_incidents:
                        logger.warning(f"Member {member_id} has {len(member.current_incidents)} active incidents")
                        # In production, these would need to be reassigned
                    
                    team_capacity.members.pop(i)
                    team_capacity.last_updated = datetime.utcnow()
                    logger.info(f"Removed member {member_id} from team {team}")
                    return True
            
            logger.warning(f"Member {member_id} not found in team {team}")
            return False
            
        except Exception as e:
            logger.error(f"Error removing member from team {team}: {str(e)}")
            return False
    
    def update_member_skills(self, team: str, member_id: str, skills: Dict[str, SkillLevel]) -> bool:
        """Update a team member's skills"""
        try:
            if team not in self.team_capacities:
                logger.error(f"Team {team} not found")
                return False
            
            team_capacity = self.team_capacities[team]
            
            for member in team_capacity.members:
                if member.id == member_id:
                    member.skills.update(skills)
                    team_capacity.last_updated = datetime.utcnow()
                    logger.info(f"Updated skills for member {member_id} in team {team}")
                    return True
            
            logger.warning(f"Member {member_id} not found in team {team}")
            return False
            
        except Exception as e:
            logger.error(f"Error updating member skills: {str(e)}")
            return False
    
    def get_load_balancing_recommendations(self) -> Dict[str, Any]:
        """Get recommendations for load balancing across teams"""
        recommendations = {
            "overloaded_teams": [],
            "underutilized_teams": [],
            "suggested_redistributions": [],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        for team_name, team_capacity in self.team_capacities.items():
            if team_capacity.is_overloaded:
                recommendations["overloaded_teams"].append({
                    "team": team_name,
                    "load_percentage": team_capacity.load_percentage,
                    "current_incidents": len(team_capacity.current_incidents),
                    "available_members": len(team_capacity.available_members)
                })
            elif team_capacity.load_percentage < 30:
                recommendations["underutilized_teams"].append({
                    "team": team_name,
                    "load_percentage": team_capacity.load_percentage,
                    "available_capacity": team_capacity.total_capacity - team_capacity.current_load
                })
        
        # Generate redistribution suggestions
        for overloaded in recommendations["overloaded_teams"]:
            for underutilized in recommendations["underutilized_teams"]:
                recommendations["suggested_redistributions"].append({
                    "from_team": overloaded["team"],
                    "to_team": underutilized["team"],
                    "suggested_incidents_to_move": min(2, overloaded["current_incidents"] // 4)
                })
        
        return recommendations
    
    def get_routing_statistics(self) -> Dict[str, Any]:
        """Get comprehensive routing statistics and metrics"""
        total_incidents = sum(len(team.current_incidents) for team in self.team_capacities.values())
        total_capacity = sum(team.total_capacity for team in self.team_capacities.values())
        
        team_stats = {}
        for team_name, team_capacity in self.team_capacities.items():
            team_stats[team_name] = {
                "current_load": len(team_capacity.current_incidents),
                "capacity": team_capacity.total_capacity,
                "load_percentage": team_capacity.load_percentage,
                "members": len(team_capacity.members),
                "available_members": len(team_capacity.available_members),
                "status": team_capacity.status.value
            }
        
        return {
            "total_rules": len(self.routing_rules["rules"]),
            "tracked_teams": list(self.team_capacities.keys()),
            "total_incidents": total_incidents,
            "total_capacity": total_capacity,
            "overall_load_percentage": (total_incidents / total_capacity * 100) if total_capacity > 0 else 0,
            "team_statistics": team_stats,
            "escalation_paths": len(self.escalation_paths),
            "skill_mappings": len(self.skill_mappings),
            "last_updated": datetime.utcnow().isoformat()
        }


# Maintain backward compatibility
IncidentRouter = RoutingEngine