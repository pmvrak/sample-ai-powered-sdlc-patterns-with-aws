"""
Streamlit MCP Demo App
A web interface for the AI-powered performance testing MCP server
"""
import streamlit as st
import json
import time
import os
from typing import Dict, Any, Optional

# Import our modules
import mcp_client
import s3_utils
import ui_components
import app_args
from tool_arg_specs import TOOL_SPECS

# Page configuration
st.set_page_config(
    page_title="Performance Test Runner",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

def check_environment():
    """Check required environment variables and show helpful errors"""
    required_vars = ["MCP_FUNCTION_URL", "AWS_REGION", "ARTIFACT_BUCKET"]
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars and not os.environ.get("DEMO_MODE", "").lower() == "true":
        st.error("❌ Missing required environment variables:")
        for var in missing_vars:
            st.code(f"export {var}=<your-value>")
        st.info("💡 Set DEMO_MODE=true to run with demo data")
        st.stop()

def initialize_session_state():
    """Initialize Streamlit session state variables"""
    defaults = {
        "session_id": "demo-001",
        "current_tool": "",
        "last_request": None,
        "last_response": None,
        "run_status": "Idle",
        "auto_refresh_logs": False,
        "last_refresh": 0
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

def render_sidebar():
    """Render the sidebar with session configuration and tool selection"""
    st.sidebar.title("🚀 Performance Test Runner")
    
    # Session configuration
    st.sidebar.subheader("📋 Session Configuration")
    
    # Session ID input
    new_session_id = st.sidebar.text_input(
        "Session ID:",
        value=st.session_state.session_id,
        help="Unique identifier for this test session"
    )
    
    # Update session state if changed
    if new_session_id != st.session_state.session_id:
        st.session_state.session_id = new_session_id
        st.rerun()
    
    st.sidebar.divider()
    
    # Tool selection
    st.sidebar.subheader("🛠️ Tool Selection")
    
    tool_options = list(TOOL_SPECS.keys())
    tool_names = [
        "🏗️ Analyze Architecture",
        "📋 Generate Scenarios", 
        "⚙️ Generate Test Plans",
        "✅ Validate Test Plans",
        "🚀 Execute Tests",
        "📦 Get Artifacts",
        "🧠 Analyze Results"
    ]
    
    selected_tool = st.sidebar.selectbox(
        "Select Tool:",
        options=tool_options,
        format_func=lambda x: tool_names[tool_options.index(x)],
        key="tool_select"
    )
    
    st.sidebar.divider()
    
    # Document viewer section
    st.sidebar.subheader("📄 Document Viewer")
    
    doc_s3_path = st.sidebar.text_input(
        "S3 Document Path:",
        placeholder="s3://bucket/path/document.json",
        help="Enter S3 path to preview document contents"
    )
    
    if doc_s3_path and doc_s3_path.startswith("s3://"):
        if st.sidebar.button("👀 Preview Document", key="preview_doc"):
            try:
                # Parse S3 path
                s3_path_clean = doc_s3_path.replace("s3://", "")
                path_parts = s3_path_clean.split("/", 1)
                if len(path_parts) >= 2:
                    bucket = path_parts[0]
                    key = path_parts[1]
                    
                    # Read document
                    import s3_utils
                    content = s3_utils.read_text(bucket, key)
                    
                    # Store in session state for display
                    st.session_state.preview_doc_content = content
                    st.session_state.preview_doc_path = doc_s3_path
                    
                    st.sidebar.success("✅ Document loaded!")
                else:
                    st.sidebar.error("❌ Invalid S3 path format")
            except Exception as e:
                st.sidebar.error(f"❌ Error loading document: {str(e)}")
    
    st.sidebar.divider()
    
    # Tool arguments form
    st.sidebar.subheader("📝 Tool Arguments")
    
    tool_args, missing = app_args.render_and_collect(selected_tool)
    
    # Inject session_id if user didn't provide it in overrides
    final_args = {"session_id": st.session_state.session_id, **tool_args}
    
    # Validate required fields
    req_names = [f["name"] for f in TOOL_SPECS[selected_tool]["fields"] if f.get("required")]
    missing_now = [lbl for lbl in missing if not any(n in final_args for n in req_names)]
    
    if missing_now:
        st.sidebar.error(f"Missing required: {', '.join(missing_now)}")
    else:
        if st.sidebar.button("Run Tool", use_container_width=True, disabled=(st.session_state.run_status == "Running")):
            execute_tool(selected_tool, final_args)

def execute_tool(tool_name: str, arguments: Dict[str, Any]):
    """Execute an MCP tool with the given arguments"""
    
    # Update session state
    st.session_state.current_tool = tool_name
    st.session_state.run_status = "Running"
    
    try:
        # Store request for display
        st.session_state.last_request = {
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        # Show spinner and execute
        with st.spinner(f"Executing {tool_name}..."):
            response = mcp_client.sign_and_post(tool_name, arguments)
        
        # Store response and update status
        st.session_state.last_response = response
        st.session_state.run_status = "OK"
        
        # Show success message
        st.success(f"✅ {tool_name} completed successfully!")
        
        # Add debugging for generate_test_plans
        if tool_name == "generate_test_plans":
            with st.expander("🔍 Debug Response Details", expanded=False):
                st.write("**Raw Response:**")
                st.json(response)
                
                # Parse and show the actual result
                if 'result' in response and 'content' in response['result']:
                    content = response['result']['content']
                    if content and len(content) > 0:
                        text_content = content[0].get('text', '')
                        try:
                            parsed_content = json.loads(text_content)
                            st.write("**Parsed Content:**")
                            st.json(parsed_content)
                            
                            # Highlight key metrics
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Status", parsed_content.get('status', 'unknown'))
                            with col2:
                                st.metric("Total Plans", parsed_content.get('total_plans', 0))
                            with col3:
                                plans_count = len(parsed_content.get('plans_generated', []))
                                st.metric("Files Generated", plans_count)
                                
                            if parsed_content.get('total_plans', 0) == 0:
                                st.warning("⚠️ No test plans were generated! Check the scenarios and MCP server logs.")
                                
                        except json.JSONDecodeError:
                            st.error(f"Could not parse response content as JSON")
                            st.code(text_content)
        
        # Auto-refresh the current tab
        st.rerun()
        
    except Exception as e:
        st.session_state.last_response = {"error": str(e)}
        st.session_state.run_status = "Failed"
        st.error(f"❌ {tool_name} failed: {str(e)}")

def render_main_content():
    """Render the main content area"""
    
    # Document Preview Section (if document is loaded)
    if hasattr(st.session_state, 'preview_doc_content') and st.session_state.preview_doc_content:
        st.subheader("📄 Document Preview")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.caption(f"**Path:** {st.session_state.preview_doc_path}")
        with col2:
            if st.button("❌ Clear Preview", key="clear_preview"):
                del st.session_state.preview_doc_content
                del st.session_state.preview_doc_path
                st.rerun()
        
        # Determine content type and display appropriately
        try:
            if st.session_state.preview_doc_path.endswith(('.json', '.JSON')):
                # Try to parse and display as JSON
                import json
                parsed_json = json.loads(st.session_state.preview_doc_content)
                st.json(parsed_json)
            elif st.session_state.preview_doc_path.endswith(('.md', '.MD')):
                # Display as markdown
                st.markdown(st.session_state.preview_doc_content)
            elif st.session_state.preview_doc_path.endswith(('.yaml', '.yml', '.YAML', '.YML')):
                # Display as YAML code
                st.code(st.session_state.preview_doc_content, language='yaml')
            else:
                # Display as plain text
                st.text_area(
                    "Document Content:",
                    value=st.session_state.preview_doc_content,
                    height=300,
                    key="doc_preview_text"
                )
        except json.JSONDecodeError:
            # If JSON parsing fails, show as text
            st.text_area(
                "Document Content:",
                value=st.session_state.preview_doc_content,
                height=300,
                key="doc_preview_text_fallback"
            )
        
        st.divider()
    
    # Run Inspector
    ui_components.render_run_inspector(
        st.session_state.current_tool,
        st.session_state.run_status,
        st.session_state.last_request,
        st.session_state.last_response
    )
    
    # Live Logs Section removed - was causing errors for missing log files
    
    # Get bucket for artifact access
    bucket = os.environ.get("ARTIFACT_BUCKET", "")
    
    # Tabs for artifacts
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Scenarios", "⚙️ Plans", "📊 Results", "🧠 Analysis"])
    
    with tab1:
        ui_components.render_scenarios_tab(st.session_state.session_id, bucket)
    
    with tab2:
        ui_components.render_plans_tab(st.session_state.session_id, bucket)
    
    with tab3:
        ui_components.render_results_tab(st.session_state.session_id, bucket)
    
    with tab4:
        ui_components.render_analysis_tab(st.session_state.session_id, bucket)
        
        # Add workflow templates section
        ui_components.render_workflow_templates(st.session_state.session_id, bucket)

def main():
    """Main application entry point"""
    
    # Check environment
    check_environment()
    
    # Initialize session state
    initialize_session_state()
    
    # Show demo mode banner if enabled
    if os.environ.get("DEMO_MODE", "").lower() == "true":
        st.info("🎭 **Demo Mode Active** - Using simulated data instead of real MCP calls")
    
    # Render sidebar
    render_sidebar()
    
    # Render main content
    render_main_content()
    
    # Footer
    st.markdown("---")
    st.markdown(
        "🚀 **Performance Test Runner** - AI-powered performance testing with MCP | "
        f"Session: `{st.session_state.session_id}` | "
        f"Status: {st.session_state.run_status}"
    )

if __name__ == "__main__":
    main()