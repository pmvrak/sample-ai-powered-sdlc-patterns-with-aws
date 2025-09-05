"""
UI components for the Streamlit MCP demo app
"""
import streamlit as st
import json
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime

def status_badge(status: str) -> str:
    """
    Generate HTML for status badge
    
    Args:
        status: Status string (Idle, Running, OK, Failed)
    
    Returns:
        HTML string for colored badge
    """
    colors = {
        "Idle": "#6c757d",      # Gray
        "Running": "#ffc107",   # Yellow
        "OK": "#28a745",        # Green
        "Failed": "#dc3545"     # Red
    }
    
    color = colors.get(status, "#6c757d")
    
    return f"""
    <span style="
        background-color: {color};
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-size: 0.875rem;
        font-weight: 500;
        display: inline-block;
        margin-left: 0.5rem;
    ">
        {status}
    </span>
    """

def render_run_inspector(current_tool: str, run_status: str, 
                        last_request: Optional[Dict], last_response: Optional[Dict]):
    """
    Render the run inspector card showing current operation status
    """
    st.subheader("🔍 Run Inspector")
    
    # Status line
    col1, col2 = st.columns([3, 1])
    with col1:
        if current_tool:
            st.write(f"**Tool:** `{current_tool}`")
        else:
            st.write("**Tool:** None")
    
    with col2:
        st.markdown(status_badge(run_status), unsafe_allow_html=True)
    
    # Request/Response sections - expanded by default
    col1, col2 = st.columns(2)
    
    with col1:
        with st.expander("📤 Request", expanded=True):
            if last_request:
                st.json(last_request)
            else:
                st.write("*No request data*")
    
    with col2:
        with st.expander("📥 Response", expanded=True):
            if last_response:
                st.json(last_response)
            else:
                st.write("*No response data*")

def render_scenarios_tab(session_id: str, bucket: str):
    """Render the Scenarios tab content"""
    from s3_utils import list_artifacts, read_json, BUCKET
    
    st.subheader("📋 Test Scenarios")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh Scenarios", key="refresh_scenarios"):
            st.rerun()
    
    try:
        # Look for scenarios.json
        artifacts = list_artifacts(session_id, None)  # Get all artifacts
        scenarios_file = None
        
        for artifact in artifacts:
            if artifact["name"] == "scenarios.json":
                scenarios_file = artifact
                break
        
        if scenarios_file:
            # Read and display scenarios
            scenarios_data = read_json(bucket or BUCKET, scenarios_file["key"])
            
            # Extract scenarios from different possible structures
            scenarios = scenarios_data.get("scenarios", {})
            
            # Try multiple possible scenario keys
            if not scenarios:
                for key in ["load_scenarios", "test_scenarios", "performance_scenarios", "scenario_list"]:
                    if key in scenarios_data:
                        data = scenarios_data[key]
                        if isinstance(data, list):
                            scenarios = {f"scenario_{i+1}": s for i, s in enumerate(data)}
                        elif isinstance(data, dict):
                            scenarios = data
                        break
            
            # If still no scenarios, try to find any dict-like structure that looks like scenarios
            if not scenarios:
                for key, value in scenarios_data.items():
                    if isinstance(value, dict) and any(subkey in str(value).lower() for subkey in ["user", "duration", "load", "test"]):
                        scenarios = {key: value}
                        break
                    elif isinstance(value, list) and value and isinstance(value[0], dict):
                        scenarios = {f"scenario_{i+1}": s for i, s in enumerate(value)}
                        break
            
            if scenarios:
                # Create summary table
                scenario_rows = []
                for name, config in scenarios.items():
                    if not isinstance(config, dict):
                        continue
                        
                    # FAULT-PROOF EXTRACTION: Search entire config structure recursively
                    def extract_value_fuzzy(data, keywords, default="N/A"):
                        """Recursively search for any field containing keywords"""
                        if not isinstance(data, dict):
                            return default
                            
                        # Direct key matching (case insensitive)
                        for key, value in data.items():
                            key_lower = key.lower()
                            for keyword in keywords:
                                if keyword in key_lower and isinstance(value, (int, float, str)):
                                    return value
                        
                        # Recursive search in nested objects
                        for key, value in data.items():
                            if isinstance(value, dict):
                                result = extract_value_fuzzy(value, keywords, None)
                                if result is not None:
                                    return result
                        
                        return default
                    
                    # Extract users with fuzzy matching
                    users = extract_value_fuzzy(config, ['user', 'concurrent', 'virtual', 'target'])
                    
                    # Extract duration with fuzzy matching  
                    duration = extract_value_fuzzy(config, ['duration', 'time', 'period'])
                    
                    # Extract ramp-up with fuzzy matching
                    ramp_up = extract_value_fuzzy(config, ['ramp', 'startup', 'warmup'])
                    
                    # Smart format conversion
                    def format_time_value(value):
                        if value == "N/A" or value is None:
                            return "N/A"
                        
                        # Handle string values like "2m", "120s", "2 minutes"
                        if isinstance(value, str):
                            value_lower = value.lower()
                            if 'm' in value_lower or 'min' in value_lower:
                                return value  # Already formatted
                            elif 's' in value_lower or 'sec' in value_lower:
                                return value  # Already formatted
                            else:
                                # Try to extract number
                                import re
                                numbers = re.findall(r'\d+', str(value))
                                if numbers:
                                    value = int(numbers[0])
                                else:
                                    return str(value)
                        
                        # Handle numeric values (assume seconds)
                        if isinstance(value, (int, float)):
                            if value >= 60:
                                return f"{int(value/60)}m {int(value%60)}s"
                            else:
                                return f"{int(value)}s"
                        
                        return str(value)
                    
                    # Apply smart formatting
                    duration = format_time_value(duration)
                    ramp_up = format_time_value(ramp_up)
                    
                    # Extract scenario type with fuzzy matching
                    scenario_type = extract_value_fuzzy(config, ['type', 'test_type', 'scenario'])
                    if scenario_type == "N/A":
                        # Infer from name or default
                        name_lower = name.lower()
                        if 'stress' in name_lower:
                            scenario_type = "Stress Test"
                        elif 'load' in name_lower:
                            scenario_type = "Load Test"
                        elif 'spike' in name_lower:
                            scenario_type = "Spike Test"
                        else:
                            scenario_type = "Performance Test"
                    
                    scenario_rows.append({
                        "Name": name.replace("_", " ").title(),
                        "Type": str(scenario_type).title(),
                        "Users": str(users) if users != "N/A" else "N/A",
                        "Duration": duration,
                        "Ramp-up": ramp_up
                    })
                
                if scenario_rows:
                    df = pd.DataFrame(scenario_rows)
                    st.dataframe(df, use_container_width=True)
                
                # Show raw JSON in expander
                with st.expander("📄 Raw Scenarios JSON"):
                    st.json(scenarios_data)
            else:
                st.warning("Scenarios file found but no scenarios data detected")
                st.write("**Debug Info:**")
                st.write(f"Available keys: {list(scenarios_data.keys())}")
                with st.expander("📄 Full Scenarios File Content"):
                    st.json(scenarios_data)
        else:
            st.info("No scenarios.json file found for this session")
            
    except Exception as e:
        st.error(f"Error loading scenarios: {str(e)}")

def render_plans_tab(session_id: str, bucket: str):
    """Render the Test Plans tab content"""
    from s3_utils import list_artifacts, read_text, presign, BUCKET
    
    st.subheader("⚙️ Test Plans")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh Plans", key="refresh_plans"):
            st.rerun()
    
    try:
        # Get Java test plan files
        artifacts = list_artifacts(session_id, "plans")
        java_files = [a for a in artifacts if a["name"].endswith(".java")]
        
        if java_files:
            # Create summary table
            plan_rows = []
            for plan in java_files:
                plan_rows.append({
                    "File": plan["name"],
                    "Size": f"{plan['size']:,} bytes",
                    "Modified": plan["last_modified"][:19].replace("T", " ")
                })
            
            df = pd.DataFrame(plan_rows)
            st.dataframe(df, use_container_width=True)
            
            # File preview and download
            st.subheader("📄 File Preview")
            selected_file = st.selectbox(
                "Select file to preview:",
                options=[p["name"] for p in java_files],
                key="plan_preview_select"
            )
            
            if selected_file:
                selected_plan = next(p for p in java_files if p["name"] == selected_file)
                
                col1, col2 = st.columns([1, 1])
                with col1:
                    # Download button
                    download_url = presign(bucket or BUCKET, selected_plan["key"])
                    st.markdown(f"[📥 Download {selected_file}]({download_url})")
                
                with col2:
                    # Preview toggle
                    show_preview = st.checkbox("Show code preview", key="show_plan_preview")
                
                if show_preview:
                    try:
                        code_content = read_text(bucket or BUCKET, selected_plan["key"])
                        st.code(code_content, language="java")
                    except Exception as e:
                        st.error(f"Error loading file content: {str(e)}")
        else:
            st.info("No test plan files found for this session")
            
    except Exception as e:
        st.error(f"Error loading test plans: {str(e)}")

def render_results_tab(session_id: str, bucket: str):
    """Render the Results tab content"""
    from s3_utils import list_artifacts, read_jtl_summary, presign, BUCKET
    
    st.subheader("📊 Test Results")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh Results", key="refresh_results"):
            st.rerun()
    
    try:
        # Get JTL result files
        artifacts = list_artifacts(session_id, "results")
        jtl_files = [a for a in artifacts if a["name"].endswith(".jtl")]
        
        if jtl_files:
            # Compute summaries for each file
            result_rows = []
            for result_file in jtl_files:
                try:
                    summary = read_jtl_summary(bucket or BUCKET, result_file["key"])
                    result_rows.append({
                        "File": result_file["name"],
                        "Requests": f"{summary.get('requests', 0):,}",
                        "Error %": f"{summary.get('errors_pct', 0):.2f}%",
                        "Avg (ms)": f"{summary.get('avg', 0):.1f}",
                        "P95 (ms)": f"{summary.get('p95', 0):.1f}",
                        "P99 (ms)": f"{summary.get('p99', 0):.1f}",
                        "Size": f"{result_file['size']:,} bytes"
                    })
                except Exception as e:
                    result_rows.append({
                        "File": result_file["name"],
                        "Requests": "Error",
                        "Error %": f"Parse error: {str(e)[:30]}...",
                        "Avg (ms)": "-",
                        "P95 (ms)": "-", 
                        "P99 (ms)": "-",
                        "Size": f"{result_file['size']:,} bytes"
                    })
            
            # Display results table
            df = pd.DataFrame(result_rows)
            st.dataframe(df, use_container_width=True)
            
            # Download links
            st.subheader("📥 Downloads")
            for result_file in jtl_files:
                download_url = presign(bucket or BUCKET, result_file["key"])
                st.markdown(f"[📥 {result_file['name']}]({download_url})")
        else:
            st.info("No result files found for this session")
            
    except Exception as e:
        st.error(f"Error loading results: {str(e)}")

def render_analysis_tab(session_id: str, bucket: str):
    """Render the Analysis tab content"""
    from s3_utils import list_artifacts, read_json, read_text, presign, BUCKET
    
    st.subheader("🧠 Performance Analysis")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh Analysis", key="refresh_analysis"):
            st.rerun()
    
    try:
        # Get analysis files
        artifacts = list_artifacts(session_id, "analysis")
        
        if artifacts:
            for artifact in artifacts:
                st.subheader(f"📄 {artifact['name']}")
                
                # Download link
                download_url = presign(bucket or BUCKET, artifact["key"])
                st.markdown(f"[📥 Download]({download_url})")
                
                # Content preview
                try:
                    if artifact["name"].endswith(".json"):
                        content = read_json(bucket or BUCKET, artifact["key"])
                        
                        # Special handling for results analysis
                        if "results_analysis" in artifact["name"]:
                            analysis = content.get("analysis", content)
                            
                            # Show key metrics
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                grade = analysis.get("performance_grade", "N/A")
                                st.metric("Performance Grade", grade)
                            
                            with col2:
                                stats = analysis.get("statistical_analysis", {})
                                total_requests = stats.get("total_requests_across_all_tests", 0)
                                st.metric("Total Requests", f"{total_requests:,}")
                            
                            with col3:
                                success_rate = stats.get("overall_success_rate", 0)
                                st.metric("Success Rate", f"{success_rate:.1f}%")
                            
                            # Show recommendations
                            ai_insights = analysis.get("ai_insights", {})
                            recommendations = ai_insights.get("recommendations", [])
                            if recommendations:
                                st.subheader("💡 Recommendations")
                                for i, rec in enumerate(recommendations, 1):
                                    st.write(f"{i}. {rec}")
                        
                        # Show full JSON in expander
                        with st.expander("📄 Full Analysis JSON"):
                            st.json(content)
                            
                    elif artifact["name"].endswith(".md"):
                        content = read_text(bucket or BUCKET, artifact["key"])
                        st.markdown(content)
                    else:
                        content = read_text(bucket or BUCKET, artifact["key"])
                        st.text(content)
                        
                except Exception as e:
                    st.error(f"Error loading {artifact['name']}: {str(e)}")
        else:
            st.info("No analysis files found for this session")
            
    except Exception as e:
        st.error(f"Error loading analysis: {str(e)}")

def render_analysis_viewer(session_id: str, bucket: str):
    """
    Helper to show read-only analysis viewer (optional): 
    load and pretty-print perf-pipeline/{session_id}/analysis.json if present
    """
    from s3_utils import read_json, BUCKET
    
    try:
        analysis_key = f"perf-pipeline/{session_id}/analysis/results_analysis.json"
        content = read_json(bucket or BUCKET, analysis_key)
        
        st.subheader("📊 Analysis Reference (Read-only)")
        st.caption("Previous analysis data for reference - no autofill")
        
        with st.expander("View Analysis JSON", expanded=False):
            st.json(content)
            
    except Exception as e:
        # Log the error but don't display it (analysis file is optional)
        import logging
        logging.debug(f"Analysis file not found for session {session_id}: {str(e)}")

def render_workflow_templates(session_id: str, bucket: str):
    """
    Parse workflows from analysis and display as copy-paste JSON templates
    """
    from s3_utils import read_json, BUCKET
    import re
    import json
    
    try:
        analysis_key = f"perf-pipeline/{session_id}/analysis/results_analysis.json"
        # Use the provided bucket or fallback to the known bucket
        bucket_name = bucket or BUCKET
        content = read_json(bucket_name, analysis_key)
        
        # Extract workflows from analysis
        workflows = content.get('workflows', [])
        
        # Debug info
        st.write(f"✅ Successfully loaded analysis from: perf-pipeline/{session_id}/analysis.json")
        st.write(f"📊 Found {len(workflows)} workflows in analysis")
        
        if workflows:
            st.subheader("🔄 Workflow Templates")
            st.caption("Copy-paste JSON templates for generate_test_scenarios")
            
            for i, workflow in enumerate(workflows):
                workflow_name = workflow.get('name', f'Workflow {i+1}')
                steps = workflow.get('steps', [])
                
                if steps:
                    # Parse endpoints from workflow steps
                    workflow_apis = []
                    order = 1
                    
                    # Define HTTP methods to look for
                    http_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
                    
                    for step in steps:
                        # Find all API paths (starting with /) in the step
                        api_paths = re.findall(r'(/[a-zA-Z0-9/_\-{}]+)', step)
                        
                        # Find all HTTP methods in the step
                        found_methods = []
                        for method in http_methods:
                            if method in step.upper():
                                found_methods.append(method)
                        
                        # If we found both methods and paths, pair them up
                        if found_methods and api_paths:
                            # Use the first method found with each path
                            primary_method = found_methods[0]
                            for path in api_paths:
                                # Skip if path looks like a file extension or too short
                                if len(path) > 3 and not path.endswith(('.json', '.xml', '.html')):
                                    workflow_apis.append({
                                        "endpoint": path,
                                        "method": primary_method,
                                        "order": order
                                    })
                                    order += 1
                    
                    if workflow_apis:
                        # Create appropriate NFRs based on workflow type
                        if "purchase" in workflow_name.lower() or "order" in workflow_name.lower():
                            nfrs = {
                                "response_time_p95": "1000ms",
                                "response_time_p99": "2000ms", 
                                "throughput": "50 concurrent users",
                                "availability": "99%",
                                "error_rate": "< 2%"
                            }
                        elif "search" in workflow_name.lower() or "browsing" in workflow_name.lower():
                            nfrs = {
                                "response_time_p95": "500ms",
                                "response_time_p99": "1000ms",
                                "throughput": "100 concurrent users", 
                                "availability": "99%",
                                "error_rate": "< 1%"
                            }
                        elif "registration" in workflow_name.lower() or "profile" in workflow_name.lower():
                            nfrs = {
                                "response_time_p95": "800ms",
                                "response_time_p99": "1500ms",
                                "throughput": "30 concurrent users",
                                "availability": "99%", 
                                "error_rate": "< 2%"
                            }
                        else:
                            nfrs = {
                                "response_time_p95": "600ms",
                                "response_time_p99": "1200ms",
                                "throughput": "60 concurrent users",
                                "availability": "99%",
                                "error_rate": "< 2%"
                            }
                        
                        # Build complete JSON template
                        template = {
                            "workflow_apis": workflow_apis,
                            "nfrs": nfrs,
                            "scenario_types": ["load"]
                        }
                        
                        with st.expander(f"🔄 {workflow_name} ({len(workflow_apis)} steps)", expanded=False):
                            st.caption(workflow.get('description', ''))
                            
                            # Show workflow steps
                            st.write("**Workflow Steps:**")
                            for j, step in enumerate(steps, 1):
                                st.write(f"{j}. {step}")
                            
                            st.write("**Copy-Paste JSON:**")
                            json_str = json.dumps(template, separators=(',', ':'))
                            st.code(json_str, language='json')
                            
                            # Copy button (using st.code with copy functionality)
                            if st.button(f"📋 Copy {workflow_name} JSON", key=f"copy_workflow_{i}"):
                                st.success(f"✅ {workflow_name} JSON ready to copy from code block above!")
            
    except Exception as e:
        # Log the error but don't display it (workflow templates are optional)
        import logging
        logging.debug(f"Workflow templates not available for session {session_id}: {str(e)}")

# Live logs section removed - was causing errors for missing log files