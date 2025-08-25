"""
User feedback collection and improvement tracking system.

This module provides comprehensive feedback collection, analysis, and
improvement tracking for the incident management system.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import statistics
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)


class FeedbackType(Enum):
    """Types of feedback"""
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"
    USABILITY_ISSUE = "usability_issue"
    PERFORMANCE_ISSUE = "performance_issue"
    DOCUMENTATION_ISSUE = "documentation_issue"
    GENERAL_FEEDBACK = "general_feedback"
    TUTORIAL_FEEDBACK = "tutorial_feedback"
    COMMAND_FEEDBACK = "command_feedback"


class FeedbackPriority(Enum):
    """Feedback priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FeedbackStatus(Enum):
    """Feedback processing status"""
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REJECTED = "rejected"


@dataclass
class FeedbackItem:
    """Individual feedback item"""
    feedback_id: str
    user_id: str
    feedback_type: FeedbackType
    title: str
    description: str
    priority: FeedbackPriority
    status: FeedbackStatus
    submitted_at: datetime
    context: Dict[str, Any]  # Additional context (command used, page visited, etc.)
    attachments: List[str]  # File paths or URLs
    tags: List[str]
    votes: int  # User votes for this feedback
    admin_notes: Optional[str] = None
    resolution: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


@dataclass
class ImprovementMetric:
    """Improvement tracking metric"""
    metric_id: str
    name: str
    description: str
    current_value: float
    target_value: float
    measurement_unit: str
    last_updated: datetime
    trend_data: List[Tuple[datetime, float]]  # Historical data points
    related_feedback: List[str]  # Related feedback IDs


@dataclass
class UserSatisfactionSurvey:
    """User satisfaction survey response"""
    survey_id: str
    user_id: str
    submitted_at: datetime
    overall_satisfaction: int  # 1-5 scale
    ease_of_use: int  # 1-5 scale
    feature_completeness: int  # 1-5 scale
    performance_rating: int  # 1-5 scale
    documentation_rating: int  # 1-5 scale
    likelihood_to_recommend: int  # 1-10 scale (NPS)
    most_useful_feature: str
    least_useful_feature: str
    suggested_improvements: str
    additional_comments: str


class FeedbackCollectionSystem:
    """
    Comprehensive feedback collection and improvement tracking system.
    
    Features:
    - Multi-channel feedback collection
    - Automated categorization and prioritization
    - User satisfaction surveys
    - Improvement metric tracking
    - Trend analysis and reporting
    - Integration with development workflow
    """
    
    def __init__(self):
        """Initialize feedback system"""
        self.feedback_items: Dict[str, FeedbackItem] = {}
        self.improvement_metrics: Dict[str, ImprovementMetric] = {}
        self.satisfaction_surveys: Dict[str, UserSatisfactionSurvey] = {}
        self.feedback_analytics: Dict[str, Any] = {}
        
        # Initialize default metrics
        self._initialize_improvement_metrics()
    
    def _initialize_improvement_metrics(self) -> None:
        """Initialize default improvement metrics"""
        
        metrics = [
            ImprovementMetric(
                metric_id="user_satisfaction",
                name="Overall User Satisfaction",
                description="Average user satisfaction rating (1-5 scale)",
                current_value=0.0,
                target_value=4.0,
                measurement_unit="rating",
                last_updated=datetime.utcnow(),
                trend_data=[],
                related_feedback=[]
            ),
            
            ImprovementMetric(
                metric_id="command_success_rate",
                name="Command Success Rate",
                description="Percentage of commands executed successfully",
                current_value=0.0,
                target_value=95.0,
                measurement_unit="percentage",
                last_updated=datetime.utcnow(),
                trend_data=[],
                related_feedback=[]
            ),
            
            ImprovementMetric(
                metric_id="help_request_frequency",
                name="Help Request Frequency",
                description="Number of help requests per user per day",
                current_value=0.0,
                target_value=2.0,  # Lower is better
                measurement_unit="requests/user/day",
                last_updated=datetime.utcnow(),
                trend_data=[],
                related_feedback=[]
            ),
            
            ImprovementMetric(
                metric_id="tutorial_completion_rate",
                name="Tutorial Completion Rate",
                description="Percentage of users who complete tutorials",
                current_value=0.0,
                target_value=80.0,
                measurement_unit="percentage",
                last_updated=datetime.utcnow(),
                trend_data=[],
                related_feedback=[]
            ),
            
            ImprovementMetric(
                metric_id="feature_adoption_rate",
                name="Feature Adoption Rate",
                description="Percentage of users actively using new features",
                current_value=0.0,
                target_value=60.0,
                measurement_unit="percentage",
                last_updated=datetime.utcnow(),
                trend_data=[],
                related_feedback=[]
            )
        ]
        
        for metric in metrics:
            self.improvement_metrics[metric.metric_id] = metric
    
    async def submit_feedback(self, user_id: str, feedback_type: FeedbackType, 
                            title: str, description: str, 
                            context: Dict[str, Any] = None,
                            attachments: List[str] = None,
                            tags: List[str] = None) -> str:
        """Submit new feedback"""
        
        feedback_id = f"FB-{datetime.utcnow().strftime('%Y%m%d')}-{len(self.feedback_items) + 1:06d}"
        
        # Auto-prioritize based on type and content
        priority = self._auto_prioritize_feedback(feedback_type, description)
        
        feedback = FeedbackItem(
            feedback_id=feedback_id,
            user_id=user_id,
            feedback_type=feedback_type,
            title=title,
            description=description,
            priority=priority,
            status=FeedbackStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            context=context or {},
            attachments=attachments or [],
            tags=tags or [],
            votes=0
        )
        
        self.feedback_items[feedback_id] = feedback
        
        # Update related metrics
        await self._update_feedback_metrics(feedback)
        
        logger.info(f"Feedback submitted: {feedback_id} by {user_id}")
        return feedback_id
    
    def _auto_prioritize_feedback(self, feedback_type: FeedbackType, description: str) -> FeedbackPriority:
        """Automatically prioritize feedback based on type and content"""
        
        # High priority keywords
        high_priority_keywords = [
            "crash", "error", "broken", "not working", "critical", "urgent",
            "security", "data loss", "performance", "slow", "timeout"
        ]
        
        # Critical priority keywords
        critical_keywords = [
            "security vulnerability", "data breach", "system down", "cannot access",
            "production issue", "outage"
        ]
        
        description_lower = description.lower()
        
        # Check for critical issues
        if any(keyword in description_lower for keyword in critical_keywords):
            return FeedbackPriority.CRITICAL
        
        # Check for high priority issues
        if (feedback_type in [FeedbackType.BUG_REPORT, FeedbackType.PERFORMANCE_ISSUE] or
            any(keyword in description_lower for keyword in high_priority_keywords)):
            return FeedbackPriority.HIGH
        
        # Medium priority for usability and documentation issues
        if feedback_type in [FeedbackType.USABILITY_ISSUE, FeedbackType.DOCUMENTATION_ISSUE]:
            return FeedbackPriority.MEDIUM
        
        # Default to low priority
        return FeedbackPriority.LOW
    
    async def vote_on_feedback(self, feedback_id: str, user_id: str, vote: int) -> bool:
        """Vote on feedback item (upvote/downvote)"""
        if feedback_id not in self.feedback_items:
            return False
        
        feedback = self.feedback_items[feedback_id]
        feedback.votes += vote
        
        logger.info(f"Vote on feedback {feedback_id}: {vote} by {user_id}")
        return True
    
    async def update_feedback_status(self, feedback_id: str, status: FeedbackStatus,
                                   admin_user: str, notes: str = None,
                                   resolution: str = None) -> bool:
        """Update feedback status (admin function)"""
        if feedback_id not in self.feedback_items:
            return False
        
        feedback = self.feedback_items[feedback_id]
        old_status = feedback.status
        feedback.status = status
        
        if notes:
            feedback.admin_notes = notes
        
        if resolution:
            feedback.resolution = resolution
            feedback.resolved_at = datetime.utcnow()
            feedback.resolved_by = admin_user
        
        logger.info(f"Feedback {feedback_id} status updated: {old_status} -> {status} by {admin_user}")
        return True
    
    async def submit_satisfaction_survey(self, user_id: str, survey_data: Dict[str, Any]) -> str:
        """Submit user satisfaction survey"""
        
        survey_id = f"SURVEY-{datetime.utcnow().strftime('%Y%m%d')}-{len(self.satisfaction_surveys) + 1:06d}"
        
        survey = UserSatisfactionSurvey(
            survey_id=survey_id,
            user_id=user_id,
            submitted_at=datetime.utcnow(),
            overall_satisfaction=survey_data.get("overall_satisfaction", 3),
            ease_of_use=survey_data.get("ease_of_use", 3),
            feature_completeness=survey_data.get("feature_completeness", 3),
            performance_rating=survey_data.get("performance_rating", 3),
            documentation_rating=survey_data.get("documentation_rating", 3),
            likelihood_to_recommend=survey_data.get("likelihood_to_recommend", 5),
            most_useful_feature=survey_data.get("most_useful_feature", ""),
            least_useful_feature=survey_data.get("least_useful_feature", ""),
            suggested_improvements=survey_data.get("suggested_improvements", ""),
            additional_comments=survey_data.get("additional_comments", "")
        )
        
        self.satisfaction_surveys[survey_id] = survey
        
        # Update satisfaction metrics
        await self._update_satisfaction_metrics()
        
        logger.info(f"Satisfaction survey submitted: {survey_id} by {user_id}")
        return survey_id
    
    async def get_feedback_list(self, filters: Dict[str, Any] = None,
                              sort_by: str = "submitted_at",
                              sort_order: str = "desc",
                              limit: int = 50) -> List[Dict[str, Any]]:
        """Get filtered list of feedback items"""
        
        feedback_list = list(self.feedback_items.values())
        
        # Apply filters
        if filters:
            if "feedback_type" in filters:
                feedback_list = [f for f in feedback_list if f.feedback_type == filters["feedback_type"]]
            
            if "status" in filters:
                feedback_list = [f for f in feedback_list if f.status == filters["status"]]
            
            if "priority" in filters:
                feedback_list = [f for f in feedback_list if f.priority == filters["priority"]]
            
            if "user_id" in filters:
                feedback_list = [f for f in feedback_list if f.user_id == filters["user_id"]]
            
            if "date_from" in filters:
                date_from = datetime.fromisoformat(filters["date_from"])
                feedback_list = [f for f in feedback_list if f.submitted_at >= date_from]
            
            if "date_to" in filters:
                date_to = datetime.fromisoformat(filters["date_to"])
                feedback_list = [f for f in feedback_list if f.submitted_at <= date_to]
        
        # Sort
        reverse = sort_order.lower() == "desc"
        if sort_by == "votes":
            feedback_list.sort(key=lambda x: x.votes, reverse=reverse)
        elif sort_by == "priority":
            priority_order = {
                FeedbackPriority.CRITICAL: 4,
                FeedbackPriority.HIGH: 3,
                FeedbackPriority.MEDIUM: 2,
                FeedbackPriority.LOW: 1
            }
            feedback_list.sort(key=lambda x: priority_order[x.priority], reverse=reverse)
        else:  # Default to submitted_at
            feedback_list.sort(key=lambda x: x.submitted_at, reverse=reverse)
        
        # Limit results
        feedback_list = feedback_list[:limit]
        
        # Convert to dict format
        return [asdict(feedback) for feedback in feedback_list]
    
    async def get_feedback_analytics(self, time_period: str = "30d") -> Dict[str, Any]:
        """Get feedback analytics and insights"""
        
        # Parse time period
        if time_period == "7d":
            start_date = datetime.utcnow() - timedelta(days=7)
        elif time_period == "30d":
            start_date = datetime.utcnow() - timedelta(days=30)
        elif time_period == "90d":
            start_date = datetime.utcnow() - timedelta(days=90)
        else:
            start_date = datetime.utcnow() - timedelta(days=30)
        
        # Filter feedback by time period
        recent_feedback = [
            f for f in self.feedback_items.values()
            if f.submitted_at >= start_date
        ]
        
        # Calculate analytics
        total_feedback = len(recent_feedback)
        
        # Feedback by type
        feedback_by_type = Counter(f.feedback_type.value for f in recent_feedback)
        
        # Feedback by priority
        feedback_by_priority = Counter(f.priority.value for f in recent_feedback)
        
        # Feedback by status
        feedback_by_status = Counter(f.status.value for f in recent_feedback)
        
        # Resolution time analysis
        resolved_feedback = [f for f in recent_feedback if f.resolved_at]
        resolution_times = []
        for f in resolved_feedback:
            resolution_time = (f.resolved_at - f.submitted_at).total_seconds() / 3600  # hours
            resolution_times.append(resolution_time)
        
        avg_resolution_time = statistics.mean(resolution_times) if resolution_times else 0
        
        # Top issues (most voted feedback)
        top_issues = sorted(recent_feedback, key=lambda x: x.votes, reverse=True)[:10]
        
        # User engagement
        active_users = len(set(f.user_id for f in recent_feedback))
        
        return {
            "time_period": time_period,
            "total_feedback": total_feedback,
            "active_users": active_users,
            "feedback_by_type": dict(feedback_by_type),
            "feedback_by_priority": dict(feedback_by_priority),
            "feedback_by_status": dict(feedback_by_status),
            "average_resolution_time_hours": avg_resolution_time,
            "top_issues": [
                {
                    "feedback_id": f.feedback_id,
                    "title": f.title,
                    "votes": f.votes,
                    "priority": f.priority.value,
                    "status": f.status.value
                }
                for f in top_issues
            ]
        }
    
    async def get_satisfaction_analytics(self, time_period: str = "30d") -> Dict[str, Any]:
        """Get user satisfaction analytics"""
        
        # Parse time period
        if time_period == "7d":
            start_date = datetime.utcnow() - timedelta(days=7)
        elif time_period == "30d":
            start_date = datetime.utcnow() - timedelta(days=30)
        elif time_period == "90d":
            start_date = datetime.utcnow() - timedelta(days=90)
        else:
            start_date = datetime.utcnow() - timedelta(days=30)
        
        # Filter surveys by time period
        recent_surveys = [
            s for s in self.satisfaction_surveys.values()
            if s.submitted_at >= start_date
        ]
        
        if not recent_surveys:
            return {
                "time_period": time_period,
                "total_responses": 0,
                "metrics": {}
            }
        
        # Calculate metrics
        metrics = {
            "overall_satisfaction": statistics.mean(s.overall_satisfaction for s in recent_surveys),
            "ease_of_use": statistics.mean(s.ease_of_use for s in recent_surveys),
            "feature_completeness": statistics.mean(s.feature_completeness for s in recent_surveys),
            "performance_rating": statistics.mean(s.performance_rating for s in recent_surveys),
            "documentation_rating": statistics.mean(s.documentation_rating for s in recent_surveys),
            "net_promoter_score": self._calculate_nps(recent_surveys)
        }
        
        # Most/least useful features
        most_useful_features = Counter(
            s.most_useful_feature for s in recent_surveys 
            if s.most_useful_feature
        )
        
        least_useful_features = Counter(
            s.least_useful_feature for s in recent_surveys 
            if s.least_useful_feature
        )
        
        return {
            "time_period": time_period,
            "total_responses": len(recent_surveys),
            "metrics": metrics,
            "most_useful_features": dict(most_useful_features.most_common(5)),
            "least_useful_features": dict(least_useful_features.most_common(5))
        }
    
    def _calculate_nps(self, surveys: List[UserSatisfactionSurvey]) -> float:
        """Calculate Net Promoter Score"""
        if not surveys:
            return 0.0
        
        scores = [s.likelihood_to_recommend for s in surveys]
        
        promoters = sum(1 for score in scores if score >= 9)
        detractors = sum(1 for score in scores if score <= 6)
        total = len(scores)
        
        nps = ((promoters - detractors) / total) * 100
        return nps
    
    async def update_improvement_metric(self, metric_id: str, value: float) -> bool:
        """Update an improvement metric"""
        if metric_id not in self.improvement_metrics:
            return False
        
        metric = self.improvement_metrics[metric_id]
        
        # Add to trend data
        metric.trend_data.append((datetime.utcnow(), value))
        
        # Keep only last 100 data points
        if len(metric.trend_data) > 100:
            metric.trend_data = metric.trend_data[-100:]
        
        # Update current value
        metric.current_value = value
        metric.last_updated = datetime.utcnow()
        
        logger.info(f"Metric updated: {metric_id} = {value}")
        return True
    
    async def get_improvement_metrics(self) -> Dict[str, Any]:
        """Get all improvement metrics with trend analysis"""
        
        metrics_data = {}
        
        for metric_id, metric in self.improvement_metrics.items():
            # Calculate trend
            trend = "stable"
            if len(metric.trend_data) >= 2:
                recent_values = [point[1] for point in metric.trend_data[-5:]]
                if len(recent_values) >= 2:
                    if recent_values[-1] > recent_values[0]:
                        trend = "improving"
                    elif recent_values[-1] < recent_values[0]:
                        trend = "declining"
            
            # Calculate progress toward target
            if metric.target_value != 0:
                progress = (metric.current_value / metric.target_value) * 100
            else:
                progress = 0
            
            metrics_data[metric_id] = {
                "name": metric.name,
                "description": metric.description,
                "current_value": metric.current_value,
                "target_value": metric.target_value,
                "measurement_unit": metric.measurement_unit,
                "progress_percentage": min(progress, 100),
                "trend": trend,
                "last_updated": metric.last_updated.isoformat(),
                "trend_data": [
                    {"timestamp": point[0].isoformat(), "value": point[1]}
                    for point in metric.trend_data[-30:]  # Last 30 data points
                ]
            }
        
        return metrics_data
    
    async def generate_improvement_report(self, time_period: str = "30d") -> Dict[str, Any]:
        """Generate comprehensive improvement report"""
        
        feedback_analytics = await self.get_feedback_analytics(time_period)
        satisfaction_analytics = await self.get_satisfaction_analytics(time_period)
        improvement_metrics = await self.get_improvement_metrics()
        
        # Identify key insights
        insights = []
        
        # Check satisfaction trends
        if satisfaction_analytics["total_responses"] > 0:
            overall_satisfaction = satisfaction_analytics["metrics"]["overall_satisfaction"]
            if overall_satisfaction < 3.0:
                insights.append({
                    "type": "concern",
                    "title": "Low User Satisfaction",
                    "description": f"Overall satisfaction is {overall_satisfaction:.1f}/5.0, below target",
                    "recommendation": "Review recent feedback and address top user concerns"
                })
            elif overall_satisfaction >= 4.0:
                insights.append({
                    "type": "positive",
                    "title": "High User Satisfaction",
                    "description": f"Overall satisfaction is {overall_satisfaction:.1f}/5.0, meeting target",
                    "recommendation": "Continue current practices and gather feedback on new features"
                })
        
        # Check feedback volume
        if feedback_analytics["total_feedback"] > 0:
            bug_reports = feedback_analytics["feedback_by_type"].get("bug_report", 0)
            total_feedback = feedback_analytics["total_feedback"]
            bug_percentage = (bug_reports / total_feedback) * 100
            
            if bug_percentage > 30:
                insights.append({
                    "type": "concern",
                    "title": "High Bug Report Volume",
                    "description": f"{bug_percentage:.1f}% of feedback are bug reports",
                    "recommendation": "Focus on quality assurance and testing processes"
                })
        
        # Check resolution time
        if feedback_analytics["average_resolution_time_hours"] > 72:
            insights.append({
                "type": "concern",
                "title": "Slow Feedback Resolution",
                "description": f"Average resolution time is {feedback_analytics['average_resolution_time_hours']:.1f} hours",
                "recommendation": "Improve feedback triage and response processes"
            })
        
        return {
            "report_generated": datetime.utcnow().isoformat(),
            "time_period": time_period,
            "feedback_analytics": feedback_analytics,
            "satisfaction_analytics": satisfaction_analytics,
            "improvement_metrics": improvement_metrics,
            "key_insights": insights,
            "recommendations": self._generate_recommendations(insights)
        }
    
    def _generate_recommendations(self, insights: List[Dict[str, Any]]) -> List[str]:
        """Generate actionable recommendations based on insights"""
        recommendations = []
        
        concern_count = sum(1 for insight in insights if insight["type"] == "concern")
        
        if concern_count == 0:
            recommendations.append("Continue monitoring user feedback and satisfaction metrics")
            recommendations.append("Consider implementing new features based on user requests")
        else:
            recommendations.append("Address high-priority user concerns identified in feedback")
            recommendations.append("Implement process improvements to reduce resolution time")
            recommendations.append("Increase communication with users about issue resolution")
        
        recommendations.append("Conduct regular user satisfaction surveys")
        recommendations.append("Analyze feedback trends to identify systemic issues")
        
        return recommendations
    
    async def _update_feedback_metrics(self, feedback: FeedbackItem) -> None:
        """Update metrics based on new feedback"""
        
        # Update help request frequency if this is a help-related feedback
        if "help" in feedback.description.lower() or "tutorial" in feedback.description.lower():
            current_metric = self.improvement_metrics["help_request_frequency"]
            # This would typically be calculated from actual usage data
            # For now, we'll increment based on feedback
            await self.update_improvement_metric("help_request_frequency", current_metric.current_value + 0.1)
    
    async def _update_satisfaction_metrics(self) -> None:
        """Update satisfaction metrics based on recent surveys"""
        
        # Get recent surveys (last 30 days)
        recent_surveys = [
            s for s in self.satisfaction_surveys.values()
            if s.submitted_at >= datetime.utcnow() - timedelta(days=30)
        ]
        
        if recent_surveys:
            avg_satisfaction = statistics.mean(s.overall_satisfaction for s in recent_surveys)
            await self.update_improvement_metric("user_satisfaction", avg_satisfaction)


# Global feedback system instance
feedback_system = FeedbackCollectionSystem()