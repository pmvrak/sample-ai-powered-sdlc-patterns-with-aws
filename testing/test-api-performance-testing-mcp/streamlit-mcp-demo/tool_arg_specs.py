"""
Tool argument specifications for dynamic form rendering
"""

TOOL_SPECS = {
    "analyze_architecture": {
        "help": "Parse BRD/architecture docs in S3 and persist analysis to this session.",
        "fields": [
            {
                "name": "documents_path",
                "type": "str",
                "label": "S3 documents path",
                "placeholder": "s3://bucket/architecture-docs/",
                "required": True
            }
        ]
    },
    "generate_test_scenarios": {
        "help": "Create scenarios. Toggle 'Auto-populate from Analysis' to load from session.",
        "fields": [
            {
                "name": "_auto_populate",
                "type": "checkbox",
                "label": "Auto-populate from Analysis",
                "help": "Load workflow_apis and NFRs from analysis.json",
                "default": False
            },
            {
                "name": "_analysis_session_id",
                "type": "str",
                "label": "Analysis Session ID",
                "help": "Session ID to load analysis from (e.g., demo-001)",
                "placeholder": "demo-001",
                "conditional": "_auto_populate"
            },
            {
                "name": "workflow_apis",
                "type": "json",
                "label": "Workflow APIs (JSON)",
                "placeholder": '[{"endpoint":"/api/auth/login","method":"POST","order":1}]',
                "required": True
            },
            {
                "name": "nfrs",
                "type": "json",
                "label": "NFRs (JSON)",
                "placeholder": '{"response_time_p95":"500ms","throughput":"1000rps","availability":"99.9%","error_rate":"<1%"}',
                "required": True
            },
            {
                "name": "scenario_types",
                "type": "multiselect",
                "label": "Scenario types",
                "options": ["load", "stress", "spike", "endurance", "scalability"],
                "default": ["load", "stress", "spike"]
            }
        ]
    },
    "generate_test_plans": {
        "help": "Convert scenarios to executable JMeter Java DSL.",
        "fields": [
            {
                "name": "output_format",
                "type": "select",
                "label": "Output format",
                "options": ["java_dsl", "jmx"],
                "default": "java_dsl"
            }
        ]
    },
    "validate_test_plans": {
        "help": "Compile and auto-fix generated Java DSL.",
        "fields": []
    },
    "execute_performance_test": {
        "help": "Run test plans on ECS Fargate. Provide environment details.",
        "fields": [
            {
                "name": "execution_environment.cluster_name",
                "type": "str",
                "label": "ECS Cluster",
                "required": True
            },
            {
                "name": "execution_environment.task_definition",
                "type": "str",
                "label": "Task Definition",
                "required": True
            },
            {
                "name": "execution_environment.target_url",
                "type": "str",
                "label": "Target URL",
                "required": True
            },
            {
                "name": "execution_environment.cpu",
                "type": "str",
                "label": "CPU (vCPUs)",
                "default": "2048",
                "required": False
            },
            {
                "name": "execution_environment.memory",
                "type": "str",
                "label": "Memory (MB)",
                "default": "4096",
                "required": False
            },
            {
                "name": "monitoring_config.duration",
                "type": "str",
                "label": "Duration (e.g., 10m)",
                "default": "10m"
            },
            {
                "name": "monitoring_config.metrics",
                "type": "multiselect",
                "label": "Metrics",
                "options": ["response_time", "throughput", "error_rate"],
                "default": ["response_time", "throughput", "error_rate"]
            }
        ]
    },
    "get_test_artifacts": {
        "help": "List artifacts for this session.",
        "fields": [
            {
                "name": "artifact_type",
                "type": "select",
                "label": "Artifact type",
                "options": ["all", "scenarios", "plans", "results", "analysis"],
                "default": "results"
            }
        ]
    },
    "analyze_test_results": {
        "help": "AI-driven analysis of .jtl results.",
        "fields": []
    }
}