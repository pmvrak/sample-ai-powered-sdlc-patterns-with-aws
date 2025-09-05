"""
Form renderer + merge + validation for tool arguments
"""
import json
import streamlit as st
from typing import Dict, Any, List
from tool_arg_specs import TOOL_SPECS
from s3_utils import read_json

def _assign_path(obj: Dict[str, Any], dotted: str, value):
    """Assign value to nested dict using dotted path"""
    cur = obj
    parts = dotted.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value

def render_and_collect(tool: str) -> tuple[Dict[str, Any], List[str]]:
    """
    Render form inputs for a tool and collect values with validation
    
    Args:
        tool: Tool name from TOOL_SPECS
    
    Returns:
        Tuple of (form_values_dict, missing_required_labels)
    """
    spec = TOOL_SPECS.get(tool, {"fields": []})
    
    if spec.get("help"):
        st.caption(spec["help"])
    
    form_vals: Dict[str, Any] = {}
    missing: List[str] = []
    
    # Special handling for generate_test_scenarios auto-populate
    auto_populate = False
    analysis_session_id = ""
    
    if tool == "generate_test_scenarios":
        # Show auto-populate checkbox first
        auto_populate = st.checkbox(
            "Auto-populate from Analysis", 
            value=False, 
            key=f"{tool}:_auto_populate",
            help="Load workflow_apis and NFRs from analysis.json"
        )
        
        if auto_populate:
            analysis_session_id = st.text_input(
                "Analysis Session ID", 
                value="demo-001", 
                placeholder="demo-001",
                key=f"{tool}:_analysis_session_id",
                help="Session ID to load analysis from (e.g., demo-001)"
            )
            
            # Load workflows for selection
            selected_workflow = None
            if analysis_session_id:
                try:
                    from s3_utils import BUCKET
                    bucket_name = BUCKET
                    analysis_key = f"perf-pipeline/{analysis_session_id}/analysis.json"
                    content = read_json(bucket_name, analysis_key)
                    
                    workflows = content.get('workflows', [])
                    if workflows:
                        workflow_names = [w.get('name', f'Workflow {i+1}') for i, w in enumerate(workflows)]
                        selected_workflow_name = st.selectbox(
                            "Select Workflow to Auto-populate",
                            options=workflow_names,
                            key=f"{tool}:_workflow_selector",
                            help="Choose which workflow to use for auto-population"
                        )
                        
                        # Find the selected workflow
                        for w in workflows:
                            if w.get('name', '') == selected_workflow_name:
                                selected_workflow = w
                                break
                        
                        if not selected_workflow:
                            selected_workflow = workflows[0]  # Fallback to first
                            
                    else:
                        st.warning("No workflows found in analysis file")
                        
                except Exception as e:
                    st.error(f"Failed to load workflows: {str(e)}")
    
    # Process regular fields
    for f in spec["fields"]:
        # Skip internal auto-populate fields
        if f["name"].startswith("_"):
            continue
            
        t = f.get("type", "str")
        label = f.get("label", f["name"])
        key = f"{tool}:{f['name']}"
        default = f.get("default")
        placeholder = f.get("placeholder", "")
        required = bool(f.get("required", False))
        
        # Auto-populate workflow_apis and nfrs if enabled
        if tool == "generate_test_scenarios" and auto_populate and selected_workflow:
            if f["name"] == "workflow_apis":
                # Auto-populate workflow_apis from selected workflow
                steps = selected_workflow.get('steps', [])
                workflow_apis = []
                order = 1
                
                import re
                
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
                    default = workflow_apis
                    st.success(f"✅ Auto-populated {len(workflow_apis)} APIs from {selected_workflow.get('name', 'workflow')}")
            
            elif f["name"] == "nfrs":
                # Auto-populate NFRs with smart defaults based on selected workflow
                workflow_name = selected_workflow.get('name', '').lower()
                if "purchase" in workflow_name or "order" in workflow_name or "checkout" in workflow_name or "payment" in workflow_name:
                    nfrs = {
                        "response_time_p95": "1000ms",
                        "response_time_p99": "2000ms", 
                        "throughput": "50 concurrent users",
                        "availability": "99%",
                        "error_rate": "< 2%"
                    }
                elif "search" in workflow_name or "browsing" in workflow_name or "product" in workflow_name:
                    nfrs = {
                        "response_time_p95": "500ms",
                        "response_time_p99": "1000ms",
                        "throughput": "100 concurrent users", 
                        "availability": "99%",
                        "error_rate": "< 1%"
                    }
                elif "registration" in workflow_name or "login" in workflow_name or "user" in workflow_name:
                    nfrs = {
                        "response_time_p95": "800ms",
                        "response_time_p99": "1500ms",
                        "throughput": "30 concurrent users",
                        "availability": "99%", 
                        "error_rate": "< 2%"
                    }
                elif "cart" in workflow_name or "shopping" in workflow_name:
                    nfrs = {
                        "response_time_p95": "600ms",
                        "response_time_p99": "1200ms",
                        "throughput": "75 concurrent users",
                        "availability": "99%",
                        "error_rate": "< 1.5%"
                    }
                else:
                    nfrs = {
                        "response_time_p95": "600ms",
                        "response_time_p99": "1200ms",
                        "throughput": "60 concurrent users",
                        "availability": "99%",
                        "error_rate": "< 2%"
                    }
                default = nfrs
                st.success(f"✅ Auto-populated NFRs for {selected_workflow.get('name', 'workflow')}")
        
        if t == "str":
            v = st.text_input(label, value=default or "", placeholder=placeholder, key=key)
        elif t == "int":
            v = int(st.number_input(label, value=int(default or 0), step=1, key=key))
        elif t == "select":
            opts = f.get("options", [])
            idx = opts.index(default) if default in opts else 0
            v = st.selectbox(label, options=opts, index=idx if opts else 0, key=key) if opts else default
        elif t == "multiselect":
            opts = f.get("options", [])
            v = st.multiselect(label, options=opts, default=f.get("default", []), key=key)
        elif t == "bool":
            v = st.checkbox(label, value=bool(default), key=key)
        elif t == "json":
            raw = st.text_area(
                label, 
                value=json.dumps(default, indent=2) if isinstance(default, (dict, list)) else "", 
                placeholder=placeholder, 
                key=key, 
                height=140
            )
            try:
                if raw.strip():
                    # Basic security: limit JSON size and validate structure
                    if len(raw) > 10000:  # 10KB limit
                        st.error(f"{label}: JSON too large (max 10KB)")
                        v = None
                    else:
                        v = json.loads(raw)
                        # Ensure it's a simple dict/list, not complex objects
                        if not isinstance(v, (dict, list, str, int, float, bool, type(None))):
                            st.error(f"{label}: Invalid JSON structure")
                            v = None
                else:
                    v = None
            except Exception:
                st.error(f"{label}: invalid JSON")
                v = None
        else:
            v = st.text_input(label, value=default or "", key=key)
        
        if required and (v in ("", None, [], {})):
            missing.append(label)
        if v not in ("", None, [], {}):
            _assign_path(form_vals, f["name"], v)

    
    st.divider()
    
    # Collapsible overrides section
    with st.expander("🔧 Optional overrides (priority: Raw > Upload > S3 > Form)", expanded=False):
        s3arg = st.text_input("Load args from s3://bucket/key.json", key=f"s3_{tool}")
        uploaded = st.file_uploader("Or upload JSON", type=["json"], key=f"upload_{tool}")
        raw_json = st.text_area("Raw JSON override", height=160, key=f"raw_{tool}")
    
    merged = dict(form_vals)
    
    # S3 override
    if s3arg.strip().startswith("s3://"):
        try:
            bkt, key = s3arg.replace("s3://", "").split("/", 1)
            merged |= read_json(bkt, key)
        except Exception as e:
            st.warning(f"S3 args not loaded: {e}")
    
    # Upload override
    if uploaded:
        try:
            merged |= json.load(uploaded)
        except Exception as e:
            st.warning(f"Uploaded JSON invalid: {e}")
    
    # Raw JSON override
    if raw_json.strip():
        try:
            # Basic security: limit JSON size
            if len(raw_json) > 10000:  # 10KB limit
                st.error("Raw JSON too large (max 10KB)")
            else:
                parsed = json.loads(raw_json)
                if isinstance(parsed, dict):
                    merged |= parsed
                else:
                    st.error("Raw JSON must be an object")
        except Exception as e:
            st.error(f"Raw JSON invalid: {e}")
    
    return merged, missing