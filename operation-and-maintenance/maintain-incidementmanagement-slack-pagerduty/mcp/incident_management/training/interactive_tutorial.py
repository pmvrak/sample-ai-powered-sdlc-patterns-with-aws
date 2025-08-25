"""
Interactive tutorial system for new users.

This module provides step-by-step tutorials for learning the incident management system,
including guided walkthroughs, interactive exercises, and progress tracking.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class TutorialStep(Enum):
    """Tutorial step types"""
    INTRODUCTION = "introduction"
    DEMONSTRATION = "demonstration"
    PRACTICE = "practice"
    QUIZ = "quiz"
    COMPLETION = "completion"


class TutorialStatus(Enum):
    """Tutorial completion status"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


@dataclass
class TutorialProgress:
    """User progress through a tutorial"""
    user_id: str
    tutorial_id: str
    status: TutorialStatus
    current_step: int
    completed_steps: List[int]
    started_at: datetime
    completed_at: Optional[datetime] = None
    score: Optional[int] = None
    feedback: Optional[str] = None


@dataclass
class TutorialStepData:
    """Individual tutorial step data"""
    step_id: int
    step_type: TutorialStep
    title: str
    content: str
    instructions: List[str]
    interactive_elements: Dict[str, Any]
    validation_criteria: Dict[str, Any]
    hints: List[str]
    estimated_duration: int  # minutes


@dataclass
class Tutorial:
    """Complete tutorial definition"""
    tutorial_id: str
    title: str
    description: str
    category: str
    difficulty: str  # beginner, intermediate, advanced
    prerequisites: List[str]
    estimated_duration: int  # minutes
    steps: List[TutorialStepData]
    learning_objectives: List[str]
    resources: List[Dict[str, str]]


class InteractiveTutorialSystem:
    """
    Interactive tutorial system for user onboarding and training.
    
    Provides:
    - Step-by-step guided tutorials
    - Interactive exercises and simulations
    - Progress tracking and analytics
    - Adaptive learning paths
    - Contextual help integration
    """
    
    def __init__(self):
        """Initialize tutorial system"""
        self.tutorials: Dict[str, Tutorial] = {}
        self.user_progress: Dict[str, Dict[str, TutorialProgress]] = {}
        self.tutorial_analytics: Dict[str, Dict[str, Any]] = {}
        
        # Initialize built-in tutorials
        self._initialize_tutorials()
    
    def _initialize_tutorials(self) -> None:
        """Initialize built-in tutorials"""
        
        # Basic incident management tutorial
        basic_tutorial = Tutorial(
            tutorial_id="basic_incident_management",
            title="Basic Incident Management",
            description="Learn the fundamentals of incident management using chat commands and the dashboard",
            category="getting_started",
            difficulty="beginner",
            prerequisites=[],
            estimated_duration=15,
            learning_objectives=[
                "Understand incident lifecycle",
                "Use basic chat commands",
                "Navigate the dashboard",
                "Create and manage incidents"
            ],
            resources=[
                {"type": "documentation", "title": "Chat Commands Reference", "url": "/docs/chat-commands"},
                {"type": "video", "title": "Dashboard Overview", "url": "/videos/dashboard-intro"},
                {"type": "guide", "title": "Quick Start Guide", "url": "/docs/quick-start"}
            ],
            steps=[
                TutorialStepData(
                    step_id=1,
                    step_type=TutorialStep.INTRODUCTION,
                    title="Welcome to Incident Management",
                    content="""
                    Welcome to the Intelligent Incident Management System! 
                    
                    This tutorial will teach you how to:
                    • View and manage incidents
                    • Use chat commands effectively
                    • Navigate the dashboard
                    • Collaborate with your team
                    
                    The tutorial takes about 15 minutes to complete.
                    """,
                    instructions=[
                        "Read the introduction carefully",
                        "Click 'Next' when you're ready to continue"
                    ],
                    interactive_elements={
                        "type": "introduction_card",
                        "show_progress": True,
                        "allow_skip": True
                    },
                    validation_criteria={},
                    hints=[],
                    estimated_duration=2
                ),
                
                TutorialStepData(
                    step_id=2,
                    step_type=TutorialStep.DEMONSTRATION,
                    title="Understanding Incidents",
                    content="""
                    An incident represents a problem or issue that needs attention.
                    
                    Key incident properties:
                    • **ID**: Unique identifier (e.g., INC-20240123-ABC123)
                    • **Title**: Brief description of the issue
                    • **Severity**: CRITICAL, HIGH, MEDIUM, or LOW
                    • **Status**: DETECTED, ASSIGNED, IN_PROGRESS, RESOLVED, CLOSED
                    • **Assignment**: Team and/or individual responsible
                    
                    Let's look at a sample incident...
                    """,
                    instructions=[
                        "Review the incident properties",
                        "Examine the sample incident below",
                        "Click 'Next' to continue"
                    ],
                    interactive_elements={
                        "type": "incident_demo",
                        "sample_incident": {
                            "id": "INC-20240123-DEMO01",
                            "title": "Database connection timeout",
                            "severity": "HIGH",
                            "status": "ASSIGNED",
                            "team": "devops",
                            "user": "john.doe"
                        }
                    },
                    validation_criteria={},
                    hints=[
                        "Notice how the incident ID includes the date",
                        "Severity helps prioritize response efforts"
                    ],
                    estimated_duration=3
                ),
                
                TutorialStepData(
                    step_id=3,
                    step_type=TutorialStep.PRACTICE,
                    title="Using Chat Commands",
                    content="""
                    You can manage incidents directly from Slack or Teams using slash commands.
                    
                    Try these commands in the practice area:
                    • `/incident help` - Show available commands
                    • `/incident list` - List current incidents
                    • `/incident status INC-123` - Show incident details
                    
                    Let's practice with a simulated chat interface...
                    """,
                    instructions=[
                        "Type `/incident help` in the chat simulator below",
                        "Try `/incident list` to see available incidents",
                        "Use `/incident status` with one of the incident IDs"
                    ],
                    interactive_elements={
                        "type": "chat_simulator",
                        "available_commands": [
                            "/incident help",
                            "/incident list", 
                            "/incident status",
                            "/incident create",
                            "/incident assign"
                        ],
                        "mock_incidents": [
                            {"id": "INC-20240123-DEMO01", "title": "Database timeout", "status": "ASSIGNED"},
                            {"id": "INC-20240123-DEMO02", "title": "API errors", "status": "IN_PROGRESS"}
                        ]
                    },
                    validation_criteria={
                        "required_commands": ["/incident help", "/incident list", "/incident status"],
                        "min_interactions": 3
                    },
                    hints=[
                        "Start with `/incident help` to see all available commands",
                        "Use tab completion for command suggestions",
                        "Incident IDs follow the format INC-YYYYMMDD-XXXXXX"
                    ],
                    estimated_duration=5
                ),
                
                TutorialStepData(
                    step_id=4,
                    step_type=TutorialStep.PRACTICE,
                    title="Dashboard Navigation",
                    content="""
                    The dashboard provides a visual interface for incident management.
                    
                    Key dashboard features:
                    • **Incident List**: View all incidents with filtering
                    • **Details Panel**: Detailed incident information
                    • **Metrics Bar**: Real-time system statistics
                    • **Team Performance**: Team workload and metrics
                    
                    Let's explore the dashboard interface...
                    """,
                    instructions=[
                        "Click on an incident in the list to view details",
                        "Try filtering incidents by status or team",
                        "Explore the metrics at the top of the dashboard"
                    ],
                    interactive_elements={
                        "type": "dashboard_simulator",
                        "features": [
                            "incident_list",
                            "details_panel", 
                            "filters",
                            "metrics_bar"
                        ],
                        "mock_data": {
                            "incidents": [
                                {"id": "INC-20240123-DEMO01", "title": "Database timeout", "severity": "HIGH", "status": "ASSIGNED", "team": "devops"},
                                {"id": "INC-20240123-DEMO02", "title": "API errors", "severity": "MEDIUM", "status": "IN_PROGRESS", "team": "platform"}
                            ],
                            "metrics": {
                                "active": 5,
                                "high_priority": 2,
                                "resolved_today": 12,
                                "avg_resolution_time": "2.5h"
                            }
                        }
                    },
                    validation_criteria={
                        "required_interactions": ["click_incident", "use_filter", "view_metrics"],
                        "min_time_spent": 60  # seconds
                    },
                    hints=[
                        "Click on any incident to see detailed information",
                        "Use the filter buttons to narrow down the incident list",
                        "The metrics bar shows real-time system statistics"
                    ],
                    estimated_duration=4
                ),
                
                TutorialStepData(
                    step_id=5,
                    step_type=TutorialStep.QUIZ,
                    title="Knowledge Check",
                    content="""
                    Let's test your understanding of incident management basics.
                    
                    Answer the following questions to complete the tutorial.
                    """,
                    instructions=[
                        "Answer all questions correctly to proceed",
                        "You can retry if you get any wrong"
                    ],
                    interactive_elements={
                        "type": "quiz",
                        "questions": [
                            {
                                "id": 1,
                                "question": "What command shows all available incident management commands?",
                                "type": "multiple_choice",
                                "options": [
                                    "/incident help",
                                    "/incident list",
                                    "/incident status",
                                    "/incident info"
                                ],
                                "correct_answer": 0,
                                "explanation": "/incident help displays all available commands and their usage"
                            },
                            {
                                "id": 2,
                                "question": "Which incident severity level indicates the highest priority?",
                                "type": "multiple_choice",
                                "options": [
                                    "HIGH",
                                    "CRITICAL", 
                                    "URGENT",
                                    "PRIORITY"
                                ],
                                "correct_answer": 1,
                                "explanation": "CRITICAL is the highest severity level, followed by HIGH, MEDIUM, and LOW"
                            },
                            {
                                "id": 3,
                                "question": "What information is included in an incident ID?",
                                "type": "multiple_choice",
                                "options": [
                                    "Only a random number",
                                    "Date and random identifier",
                                    "Team name and number",
                                    "Severity and timestamp"
                                ],
                                "correct_answer": 1,
                                "explanation": "Incident IDs follow the format INC-YYYYMMDD-XXXXXX, including the date and a unique identifier"
                            }
                        ]
                    },
                    validation_criteria={
                        "min_score": 80,
                        "allow_retries": True
                    },
                    hints=[
                        "Review the previous steps if you're unsure",
                        "Think about what you learned in the demonstration"
                    ],
                    estimated_duration=3
                ),
                
                TutorialStepData(
                    step_id=6,
                    step_type=TutorialStep.COMPLETION,
                    title="Tutorial Complete!",
                    content="""
                    Congratulations! You've completed the Basic Incident Management tutorial.
                    
                    You've learned how to:
                    ✅ Understand incident properties and lifecycle
                    ✅ Use chat commands for incident management
                    ✅ Navigate the dashboard interface
                    ✅ Apply your knowledge through practice
                    
                    Next steps:
                    • Explore the Advanced Incident Management tutorial
                    • Try the Team Collaboration tutorial
                    • Practice with real incidents (if available)
                    • Review the documentation for more details
                    """,
                    instructions=[
                        "Review your progress and achievements",
                        "Choose your next learning path",
                        "Provide feedback on this tutorial"
                    ],
                    interactive_elements={
                        "type": "completion_card",
                        "show_achievements": True,
                        "next_tutorials": [
                            "advanced_incident_management",
                            "team_collaboration",
                            "automation_basics"
                        ],
                        "feedback_form": True
                    },
                    validation_criteria={},
                    hints=[],
                    estimated_duration=2
                )
            ]
        )
        
        self.tutorials["basic_incident_management"] = basic_tutorial
        
        # Advanced incident management tutorial
        advanced_tutorial = Tutorial(
            tutorial_id="advanced_incident_management",
            title="Advanced Incident Management",
            description="Learn advanced features including automation, escalation, and team coordination",
            category="advanced",
            difficulty="intermediate",
            prerequisites=["basic_incident_management"],
            estimated_duration=25,
            learning_objectives=[
                "Use automation features effectively",
                "Manage incident escalation",
                "Coordinate team responses",
                "Analyze incident patterns"
            ],
            resources=[
                {"type": "documentation", "title": "Automation Guide", "url": "/docs/automation"},
                {"type": "documentation", "title": "Team Management", "url": "/docs/team-management"},
                {"type": "video", "title": "Advanced Features", "url": "/videos/advanced-features"}
            ],
            steps=[
                # Advanced tutorial steps would be defined here
                # Similar structure but with more complex scenarios
            ]
        )
        
        self.tutorials["advanced_incident_management"] = advanced_tutorial
    
    async def get_available_tutorials(self, user_id: str) -> List[Dict[str, Any]]:
        """Get tutorials available to a user based on their progress"""
        available = []
        user_progress = self.user_progress.get(user_id, {})
        
        for tutorial_id, tutorial in self.tutorials.items():
            # Check prerequisites
            prerequisites_met = True
            for prereq in tutorial.prerequisites:
                if prereq not in user_progress or user_progress[prereq].status != TutorialStatus.COMPLETED:
                    prerequisites_met = False
                    break
            
            if prerequisites_met:
                progress = user_progress.get(tutorial_id)
                tutorial_info = {
                    "tutorial_id": tutorial_id,
                    "title": tutorial.title,
                    "description": tutorial.description,
                    "category": tutorial.category,
                    "difficulty": tutorial.difficulty,
                    "estimated_duration": tutorial.estimated_duration,
                    "learning_objectives": tutorial.learning_objectives,
                    "status": progress.status.value if progress else TutorialStatus.NOT_STARTED.value,
                    "progress_percentage": self._calculate_progress_percentage(progress) if progress else 0
                }
                available.append(tutorial_info)
        
        return available
    
    async def start_tutorial(self, user_id: str, tutorial_id: str) -> Dict[str, Any]:
        """Start a tutorial for a user"""
        if tutorial_id not in self.tutorials:
            raise ValueError(f"Tutorial {tutorial_id} not found")
        
        tutorial = self.tutorials[tutorial_id]
        
        # Check prerequisites
        user_progress = self.user_progress.get(user_id, {})
        for prereq in tutorial.prerequisites:
            if prereq not in user_progress or user_progress[prereq].status != TutorialStatus.COMPLETED:
                raise ValueError(f"Prerequisite tutorial {prereq} not completed")
        
        # Initialize or update progress
        if user_id not in self.user_progress:
            self.user_progress[user_id] = {}
        
        progress = TutorialProgress(
            user_id=user_id,
            tutorial_id=tutorial_id,
            status=TutorialStatus.IN_PROGRESS,
            current_step=1,
            completed_steps=[],
            started_at=datetime.utcnow()
        )
        
        self.user_progress[user_id][tutorial_id] = progress
        
        # Return first step
        first_step = tutorial.steps[0]
        return {
            "tutorial": {
                "id": tutorial_id,
                "title": tutorial.title,
                "description": tutorial.description,
                "total_steps": len(tutorial.steps)
            },
            "step": asdict(first_step),
            "progress": asdict(progress)
        }
    
    async def get_tutorial_step(self, user_id: str, tutorial_id: str, step_id: int) -> Dict[str, Any]:
        """Get a specific tutorial step"""
        if tutorial_id not in self.tutorials:
            raise ValueError(f"Tutorial {tutorial_id} not found")
        
        tutorial = self.tutorials[tutorial_id]
        
        if step_id < 1 or step_id > len(tutorial.steps):
            raise ValueError(f"Invalid step ID {step_id}")
        
        step = tutorial.steps[step_id - 1]
        progress = self.user_progress.get(user_id, {}).get(tutorial_id)
        
        return {
            "tutorial": {
                "id": tutorial_id,
                "title": tutorial.title,
                "total_steps": len(tutorial.steps)
            },
            "step": asdict(step),
            "progress": asdict(progress) if progress else None
        }
    
    async def validate_step_completion(self, user_id: str, tutorial_id: str, step_id: int, 
                                     user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Validate user input for step completion"""
        if tutorial_id not in self.tutorials:
            raise ValueError(f"Tutorial {tutorial_id} not found")
        
        tutorial = self.tutorials[tutorial_id]
        step = tutorial.steps[step_id - 1]
        
        validation_result = {
            "valid": True,
            "errors": [],
            "hints": [],
            "score": 100
        }
        
        # Validate based on step type and criteria
        if step.step_type == TutorialStep.PRACTICE:
            validation_result = await self._validate_practice_step(step, user_input)
        elif step.step_type == TutorialStep.QUIZ:
            validation_result = await self._validate_quiz_step(step, user_input)
        
        # Update progress if validation passed
        if validation_result["valid"]:
            await self._update_step_progress(user_id, tutorial_id, step_id)
        
        return validation_result
    
    async def _validate_practice_step(self, step: TutorialStepData, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Validate practice step completion"""
        criteria = step.validation_criteria
        result = {"valid": True, "errors": [], "hints": [], "score": 100}
        
        # Check required commands (for chat simulator)
        if "required_commands" in criteria:
            executed_commands = user_input.get("executed_commands", [])
            missing_commands = []
            
            for required_cmd in criteria["required_commands"]:
                if required_cmd not in executed_commands:
                    missing_commands.append(required_cmd)
            
            if missing_commands:
                result["valid"] = False
                result["errors"].append(f"Please try these commands: {', '.join(missing_commands)}")
                result["hints"].extend(step.hints)
        
        # Check minimum interactions
        if "min_interactions" in criteria:
            interaction_count = user_input.get("interaction_count", 0)
            if interaction_count < criteria["min_interactions"]:
                result["valid"] = False
                result["errors"].append(f"Please complete at least {criteria['min_interactions']} interactions")
        
        # Check required interactions (for dashboard simulator)
        if "required_interactions" in criteria:
            completed_interactions = user_input.get("completed_interactions", [])
            missing_interactions = []
            
            for required_interaction in criteria["required_interactions"]:
                if required_interaction not in completed_interactions:
                    missing_interactions.append(required_interaction)
            
            if missing_interactions:
                result["valid"] = False
                result["errors"].append(f"Please complete these actions: {', '.join(missing_interactions)}")
        
        return result
    
    async def _validate_quiz_step(self, step: TutorialStepData, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Validate quiz step completion"""
        questions = step.interactive_elements["questions"]
        user_answers = user_input.get("answers", {})
        
        correct_count = 0
        total_questions = len(questions)
        errors = []
        
        for question in questions:
            question_id = str(question["id"])
            user_answer = user_answers.get(question_id)
            correct_answer = question["correct_answer"]
            
            if user_answer == correct_answer:
                correct_count += 1
            else:
                errors.append(f"Question {question_id}: {question['explanation']}")
        
        score = (correct_count / total_questions) * 100
        min_score = step.validation_criteria.get("min_score", 70)
        
        return {
            "valid": score >= min_score,
            "errors": errors if score < min_score else [],
            "hints": step.hints if score < min_score else [],
            "score": score,
            "correct_count": correct_count,
            "total_questions": total_questions
        }
    
    async def _update_step_progress(self, user_id: str, tutorial_id: str, step_id: int) -> None:
        """Update user progress for completed step"""
        if user_id not in self.user_progress:
            self.user_progress[user_id] = {}
        
        if tutorial_id not in self.user_progress[user_id]:
            return  # Tutorial not started
        
        progress = self.user_progress[user_id][tutorial_id]
        
        # Mark step as completed
        if step_id not in progress.completed_steps:
            progress.completed_steps.append(step_id)
        
        # Update current step
        tutorial = self.tutorials[tutorial_id]
        if step_id < len(tutorial.steps):
            progress.current_step = step_id + 1
        else:
            # Tutorial completed
            progress.status = TutorialStatus.COMPLETED
            progress.completed_at = datetime.utcnow()
    
    async def get_next_step(self, user_id: str, tutorial_id: str) -> Optional[Dict[str, Any]]:
        """Get the next step in the tutorial"""
        progress = self.user_progress.get(user_id, {}).get(tutorial_id)
        if not progress or progress.status == TutorialStatus.COMPLETED:
            return None
        
        tutorial = self.tutorials[tutorial_id]
        if progress.current_step > len(tutorial.steps):
            return None
        
        next_step = tutorial.steps[progress.current_step - 1]
        return {
            "tutorial": {
                "id": tutorial_id,
                "title": tutorial.title,
                "total_steps": len(tutorial.steps)
            },
            "step": asdict(next_step),
            "progress": asdict(progress)
        }
    
    async def skip_tutorial(self, user_id: str, tutorial_id: str) -> None:
        """Mark tutorial as skipped"""
        if user_id not in self.user_progress:
            self.user_progress[user_id] = {}
        
        if tutorial_id in self.user_progress[user_id]:
            self.user_progress[user_id][tutorial_id].status = TutorialStatus.SKIPPED
        else:
            progress = TutorialProgress(
                user_id=user_id,
                tutorial_id=tutorial_id,
                status=TutorialStatus.SKIPPED,
                current_step=0,
                completed_steps=[],
                started_at=datetime.utcnow()
            )
            self.user_progress[user_id][tutorial_id] = progress
    
    async def submit_feedback(self, user_id: str, tutorial_id: str, feedback: Dict[str, Any]) -> None:
        """Submit tutorial feedback"""
        progress = self.user_progress.get(user_id, {}).get(tutorial_id)
        if progress:
            progress.feedback = json.dumps(feedback)
        
        # Store analytics
        if tutorial_id not in self.tutorial_analytics:
            self.tutorial_analytics[tutorial_id] = {
                "completion_rate": 0,
                "average_score": 0,
                "feedback_count": 0,
                "common_issues": []
            }
        
        analytics = self.tutorial_analytics[tutorial_id]
        analytics["feedback_count"] += 1
        
        # Update analytics based on feedback
        if "rating" in feedback:
            # Update average rating logic here
            pass
        
        if "issues" in feedback:
            analytics["common_issues"].extend(feedback["issues"])
    
    def _calculate_progress_percentage(self, progress: TutorialProgress) -> int:
        """Calculate progress percentage"""
        if progress.status == TutorialStatus.COMPLETED:
            return 100
        elif progress.status == TutorialStatus.NOT_STARTED:
            return 0
        else:
            tutorial = self.tutorials[progress.tutorial_id]
            return int((len(progress.completed_steps) / len(tutorial.steps)) * 100)
    
    async def get_user_analytics(self, user_id: str) -> Dict[str, Any]:
        """Get analytics for a specific user"""
        user_progress = self.user_progress.get(user_id, {})
        
        total_tutorials = len(self.tutorials)
        completed_tutorials = sum(1 for p in user_progress.values() 
                                if p.status == TutorialStatus.COMPLETED)
        in_progress_tutorials = sum(1 for p in user_progress.values() 
                                  if p.status == TutorialStatus.IN_PROGRESS)
        
        total_time_spent = 0
        for progress in user_progress.values():
            if progress.completed_at and progress.started_at:
                total_time_spent += (progress.completed_at - progress.started_at).total_seconds()
        
        return {
            "user_id": user_id,
            "total_tutorials": total_tutorials,
            "completed_tutorials": completed_tutorials,
            "in_progress_tutorials": in_progress_tutorials,
            "completion_rate": (completed_tutorials / total_tutorials) * 100 if total_tutorials > 0 else 0,
            "total_time_spent_minutes": total_time_spent / 60,
            "tutorials": [asdict(p) for p in user_progress.values()]
        }
    
    async def get_system_analytics(self) -> Dict[str, Any]:
        """Get system-wide tutorial analytics"""
        total_users = len(self.user_progress)
        total_tutorials = len(self.tutorials)
        
        completion_stats = {}
        for tutorial_id in self.tutorials:
            completed = sum(1 for user_progress in self.user_progress.values()
                          if tutorial_id in user_progress and 
                          user_progress[tutorial_id].status == TutorialStatus.COMPLETED)
            started = sum(1 for user_progress in self.user_progress.values()
                        if tutorial_id in user_progress)
            
            completion_stats[tutorial_id] = {
                "started": started,
                "completed": completed,
                "completion_rate": (completed / started) * 100 if started > 0 else 0
            }
        
        return {
            "total_users": total_users,
            "total_tutorials": total_tutorials,
            "completion_stats": completion_stats,
            "tutorial_analytics": self.tutorial_analytics
        }


# Global tutorial system instance
tutorial_system = InteractiveTutorialSystem()