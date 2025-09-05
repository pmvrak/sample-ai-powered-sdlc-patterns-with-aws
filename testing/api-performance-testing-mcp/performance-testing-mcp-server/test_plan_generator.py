"""
Test Plan Generator Module
Converts scenarios into executable JMeter Java DSL code
"""

import json
import logging
import os
from typing import Dict, Any, List
import boto3

logger = logging.getLogger(__name__)

def generate_plans(session_id: str, output_format: str, s3_client, bedrock_client) -> Dict[str, Any]:
    """
    Generate JMeter test plans from scenarios
    
    Args:
        session_id: Session ID linking to scenarios
        output_format: Format for output (java_dsl, jmx, both)
        s3_client: AWS S3 client
        bedrock_client: AWS Bedrock client
    
    Returns:
        Generated test plans and S3 locations
    """
    try:
        logger.info(f"=== GENERATE_PLANS CALLED ===")
        logger.info(f"Session ID: {session_id}")
        logger.info(f"Output format: {output_format}")
        logger.info(f"S3 client: {type(s3_client)}")
        logger.info(f"Bedrock client: {type(bedrock_client)}")
        
        # Load scenarios
        logger.info("=== LOADING SCENARIOS ===")
        scenarios_data = _load_scenarios(session_id, s3_client)
        logger.info(f"Scenarios loaded successfully, keys: {list(scenarios_data.keys())}")
        
        # Generate test plans
        logger.info("=== GENERATING TEST PLANS ===")
        test_plans = _generate_test_plans_with_bedrock(
            scenarios_data, output_format, bedrock_client
        )
        logger.info(f"Test plans generated: {len(test_plans)} files")
        
        # Store test plans in S3
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        s3_locations = []
        
        for plan_name, plan_content in test_plans.items():
            s3_key = f"perf-pipeline/{session_id}/plans/{plan_name}"
            
            s3_client.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=plan_content,
                ContentType='text/plain' if plan_name.endswith('.java') else 'application/xml'
            )
            
            s3_locations.append(f"s3://{bucket_name}/{s3_key}")
        
        logger.info(f"Test plans generated and stored: {len(test_plans)} files")
        
        return {
            'session_id': session_id,
            'status': 'completed',
            'output_format': output_format,
            'plans_generated': list(test_plans.keys()),
            's3_locations': s3_locations,
            'total_plans': len(test_plans)
        }
        
    except Exception as e:
        logger.error(f"Error generating test plans: {str(e)}")
        return {
            'session_id': session_id,
            'status': 'error',
            'error': str(e)
        }

def _load_scenarios(session_id: str, s3_client) -> Dict[str, Any]:
    """Load scenarios from S3"""
    try:
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        s3_key = f"perf-pipeline/{session_id}/scenarios.json"
        
        logger.info(f"Loading scenarios from S3:")
        logger.info(f"  Bucket: {bucket_name}")
        logger.info(f"  Key: {s3_key}")
        
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        content = response['Body'].read().decode('utf-8')
        
        logger.info(f"Scenarios file loaded, size: {len(content)} characters")
        logger.info(f"Content preview (first 500 chars): {content[:500]}...")
        
        parsed_data = json.loads(content)
        logger.info(f"Parsed scenarios data keys: {list(parsed_data.keys())}")
        
        return parsed_data
        
    except Exception as e:
        logger.warning(f"Failed to load scenarios for session {session_id}, will be handled upstream: {str(e)}")
        logger.debug(f"Exception type: {type(e).__name__}")
        import traceback
        logger.debug(f"Full traceback: {traceback.format_exc()}")
        raise

def _generate_test_plans_with_bedrock(scenarios_data: Dict, output_format: str, bedrock_client) -> Dict[str, str]:
    """Generate test plans using template-based approach with validation"""
    
    # Generate test plans using AI
    raw_test_plans = _generate_test_plans_with_templates(scenarios_data, output_format)
    
    # Validate and fix the generated code
    from code_validator import validate_and_fix_test_plans
    validation_result = validate_and_fix_test_plans(raw_test_plans)
    
    if validation_result['status'] in ['success', 'partial_success']:
        logger.info(f"Code validation: {validation_result['status']}")
        if validation_result['fixes_applied']:
            logger.info(f"Fixes applied: {validation_result['fixes_applied']}")
        return validation_result['validated_plans']
    else:
        logger.error(f"Code validation failed: {validation_result.get('error', 'Unknown error')}")
        # Return original plans as fallback
        return raw_test_plans



def _generate_test_plans_with_templates(scenarios_data: Dict, output_format: str) -> Dict[str, str]:
    """Generate test plans using simple AI approach like demo MCP server"""
    
    logger.info("=== STARTING TEST PLAN GENERATION ===")
    logger.info(f"Input scenarios_data keys: {list(scenarios_data.keys())}")
    logger.info(f"Output format requested: {output_format}")
    
    test_plans = {}
    
    # Handle different scenario structures
    scenarios = scenarios_data.get('scenarios', {})
    logger.info(f"Direct scenarios found: {len(scenarios)} items")
    
    # Fix double nesting issue: scenarios.scenarios
    if isinstance(scenarios, dict) and 'scenarios' in scenarios:
        logger.info("Found double-nested scenarios.scenarios structure")
        nested_scenarios = scenarios['scenarios']
        if isinstance(nested_scenarios, list):
            logger.info(f"Converting nested scenarios array with {len(nested_scenarios)} items")
            scenarios = {}
            for i, scenario in enumerate(nested_scenarios):
                scenario_name = scenario.get('name', f'scenario_{i+1}').lower().replace(' ', '_').replace('-', '_')
                scenarios[scenario_name] = scenario
                logger.info(f"Converted nested scenario {i+1}: {scenario_name}")
        else:
            scenarios = nested_scenarios
    
    # If scenarios is empty, try load_scenarios array
    if not scenarios and 'load_scenarios' in scenarios_data:
        logger.info("No direct scenarios, checking load_scenarios array")
        load_scenarios = scenarios_data['load_scenarios']
        logger.info(f"load_scenarios type: {type(load_scenarios)}, length: {len(load_scenarios) if isinstance(load_scenarios, list) else 'N/A'}")
        
        if isinstance(load_scenarios, list):
            # Convert array to dictionary
            scenarios = {}
            for i, scenario in enumerate(load_scenarios):
                scenario_name = scenario.get('name', f'scenario_{i+1}').lower().replace(' ', '_')
                scenarios[scenario_name] = scenario
                logger.info(f"Converted scenario {i+1}: {scenario_name}")
    
    # Check for *_test_scenarios pattern (like stress_test_scenarios)
    if not scenarios:
        logger.info("No direct scenarios, checking for *_test_scenarios pattern")
        for key in scenarios_data.keys():
            if key.endswith('_test_scenarios') or key.endswith('_scenarios'):
                logger.info(f"Found {key} pattern")
                scenario_data = scenarios_data[key]
                logger.info(f"{key} type: {type(scenario_data)}")
                
                # Handle nested scenarios array
                if isinstance(scenario_data, dict) and 'scenarios' in scenario_data:
                    scenario_list = scenario_data['scenarios']
                    logger.info(f"{key}.scenarios type: {type(scenario_list)}, length: {len(scenario_list) if isinstance(scenario_list, list) else 'N/A'}")
                    
                    if isinstance(scenario_list, list):
                        scenarios = {}
                        for i, scenario in enumerate(scenario_list):
                            scenario_name = scenario.get('name', f'scenario_{i+1}').lower().replace(' ', '_').replace('-', '_')
                            scenarios[scenario_name] = scenario
                            logger.info(f"Converted {key} scenario {i+1}: {scenario_name}")
                        break
                elif isinstance(scenario_data, list):
                    # Direct array
                    scenarios = {}
                    for i, scenario in enumerate(scenario_data):
                        scenario_name = scenario.get('name', f'scenario_{i+1}').lower().replace(' ', '_').replace('-', '_')
                        scenarios[scenario_name] = scenario
                        logger.info(f"Converted {key} scenario {i+1}: {scenario_name}")
                    break
    
    # Check for scenario type-based structure (stress, load, etc.)
    if not scenarios:
        logger.info("No *_test_scenarios found, checking for type-based structure")
        for scenario_type in ['stress', 'load', 'spike', 'volume', 'endurance']:
            if scenario_type in scenarios_data:
                logger.info(f"Found {scenario_type} scenario type")
                type_data = scenarios_data[scenario_type]
                logger.info(f"{scenario_type} data type: {type(type_data)}, keys: {list(type_data.keys()) if isinstance(type_data, dict) else 'N/A'}")
                
                if isinstance(type_data, dict) and 'scenarios' in type_data:
                    scenario_list = type_data['scenarios']
                    logger.info(f"{scenario_type}.scenarios type: {type(scenario_list)}, length: {len(scenario_list) if isinstance(scenario_list, list) else 'N/A'}")
                    
                    if isinstance(scenario_list, list):
                        # Convert array to dictionary
                        scenarios = {}
                        for i, scenario in enumerate(scenario_list):
                            scenario_name = scenario.get('name', f'{scenario_type}_scenario_{i+1}').lower().replace(' ', '_')
                            scenarios[scenario_name] = scenario
                            logger.info(f"Converted {scenario_type} scenario {i+1}: {scenario_name}")
                        break
    
    # Check for *_test_scenarios pattern (like stress_test_scenarios)
    if not scenarios:
        logger.info("No type-based scenarios, checking for *_test_scenarios pattern")
        for key in scenarios_data.keys():
            if key.endswith('_test_scenarios') or key.endswith('_scenarios'):
                logger.info(f"Found {key} pattern")
                scenario_list = scenarios_data[key]
                logger.info(f"{key} type: {type(scenario_list)}, length: {len(scenario_list) if isinstance(scenario_list, list) else 'N/A'}")
                
                if isinstance(scenario_list, list):
                    # Convert array to dictionary
                    scenarios = {}
                    for i, scenario in enumerate(scenario_list):
                        scenario_name = scenario.get('name', f'scenario_{i+1}').lower().replace(' ', '_')
                        scenarios[scenario_name] = scenario
                        logger.info(f"Converted {key} scenario {i+1}: {scenario_name}")
                    break
    
    logger.info(f"Final scenarios count: {len(scenarios)}")
    logger.info(f"Scenario names: {list(scenarios.keys())}")
    
    # FAULT-PROOF FALLBACK: Search for ANY array of objects that look like scenarios
    if not scenarios:
        logger.warning("Using fault-proof fallback: searching for any scenario-like structures")
        
        def find_scenarios_recursively(data, path=""):
            """Recursively search for arrays that look like scenarios"""
            found_scenarios = {}
            
            if isinstance(data, dict):
                for key, value in data.items():
                    current_path = f"{path}.{key}" if path else key
                    
                    # Check if this is an array of scenario-like objects
                    if isinstance(value, list) and len(value) > 0:
                        # Check if items look like scenarios (have name, config, etc.)
                        first_item = value[0]
                        if isinstance(first_item, dict):
                            scenario_indicators = ['name', 'test_configuration', 'configuration', 'users', 'duration', 'workflow']
                            if any(indicator in str(first_item).lower() for indicator in scenario_indicators):
                                logger.info(f"Found scenario-like array at {current_path} with {len(value)} items")
                                for i, scenario in enumerate(value):
                                    if isinstance(scenario, dict):
                                        scenario_name = scenario.get('name', f'scenario_{i+1}').lower().replace(' ', '_').replace('-', '_')
                                        found_scenarios[scenario_name] = scenario
                                        logger.info(f"Extracted scenario: {scenario_name}")
                                return found_scenarios
                    
                    # Recurse into nested objects
                    elif isinstance(value, dict):
                        nested_result = find_scenarios_recursively(value, current_path)
                        if nested_result:
                            return nested_result
            
            return found_scenarios
        
        scenarios = find_scenarios_recursively(scenarios_data)
        logger.info(f"Fault-proof fallback found {len(scenarios)} scenarios")
    
    if not scenarios:
        logger.error("❌ NO SCENARIOS FOUND IN ANY EXPECTED STRUCTURE")
        logger.error(f"Available top-level keys: {list(scenarios_data.keys())}")
        for key, value in scenarios_data.items():
            logger.error(f"  {key}: {type(value)} - {list(value.keys()) if isinstance(value, dict) else str(value)[:100]}")
        return {}
    
    # Generate test plans for each scenario using simple prompts like demo MCP server
    for scenario_name, scenario_config in scenarios.items():
        logger.info(f"\n=== PROCESSING SCENARIO: {scenario_name} ===")
        logger.info(f"Scenario config keys: {list(scenario_config.keys())}")
        
        # Fixed format: Always use "TestPlan" + number for consistency
        plan_number = len(test_plans) + 1
        class_name = f"TestPlan{plan_number:02d}"  # TestPlan01, TestPlan02, etc.
        filename = f"{class_name}.java"
        logger.info(f"Generating {filename} (class: {class_name})")
        
        # Simple prompt with key scenario details
        config = scenario_config.get('test_configuration', scenario_config.get('configuration', {}))
        
        # Handle different workflow structures
        workflow_steps = []
        if 'workflow_execution' in scenario_config and 'sequence' in scenario_config['workflow_execution']:
            workflow_steps = scenario_config['workflow_execution']['sequence']
        elif 'specific_endpoints' in scenario_config:
            workflow_steps = scenario_config['specific_endpoints']
        elif 'workflow_steps' in scenario_config:
            workflow_steps = scenario_config['workflow_steps']
        
        logger.info(f"Config found: {config}")
        logger.info(f"Workflow steps count: {len(workflow_steps)}")
        
        # Let AI understand the entire scenario instead of extracting parameters
        scenario_json = json.dumps(scenario_config, indent=2)
        logger.info(f"Sending complete scenario to AI: {len(scenario_json)} characters")
        
        simple_prompt = f"""Generate a JMeter Java DSL test plan from this complete scenario specification:

SCENARIO DATA:
{scenario_json}

REQUIREMENTS:
- Class name MUST be: {class_name}
- Analyze the scenario data to understand the load pattern, user counts, timing, and endpoints
- Follow the exact load pattern specified (step incremental, spike, constant, etc.)
- Use all endpoints from the workflow_execution.sequence if present
- Handle the timing as specified in the scenario (total_duration, step durations, etc.)
- Include proper ramp-up periods as specified
- DO NOT use default values like 10 users, 120 seconds, or /health endpoints
- Extract the actual values from the scenario data provided above

Use this EXACT JMeter 5.6 Traditional API template (PROVEN TO WORK):
```java
import org.apache.jmeter.testelement.TestPlan;
import org.apache.jmeter.threads.ThreadGroup;
import org.apache.jmeter.control.LoopController;
import org.apache.jmeter.protocol.http.sampler.HTTPSamplerProxy;
import org.apache.jmeter.reporters.ResultCollector;
import org.apache.jmeter.util.JMeterUtils;
import org.apache.jmeter.engine.StandardJMeterEngine;
import org.apache.jorphan.collections.ListedHashTree;

public class {class_name} {{
    public static void main(String[] args) throws Exception {{
        // Initialize JMeter
        JMeterUtils.loadJMeterProperties("jmeter.properties");
        JMeterUtils.initLocale();
        
        String targetHost = System.getProperty("target.host", "localhost");
        String targetPort = System.getProperty("target.port", "8080");
        
        // Create test plan using traditional JMeter API
        TestPlan testPlan = new TestPlan("EXTRACT_SCENARIO_NAME");
        testPlan.setComment("EXTRACT_SCENARIO_DESCRIPTION");
        
        ThreadGroup threadGroup = new ThreadGroup();
        threadGroup.setName("Load Test Users");
        threadGroup.setNumThreads(EXTRACT_USER_COUNT); // Get from scenario
        threadGroup.setRampUp(EXTRACT_RAMPUP_SECONDS); // Get from scenario in seconds
        threadGroup.setScheduler(true);
        threadGroup.setDuration(EXTRACT_DURATION_SECONDS); // Get from scenario in seconds
        
        // Create and set LoopController - CRITICAL for fixing main_controller error
        LoopController loopController = new LoopController();
        loopController.setLoops(-1); // Infinite loops (controlled by duration)
        threadGroup.setSamplerController(loopController);
        
        // Create HTTP samplers for each endpoint
        HTTPSamplerProxy sampler1 = new HTTPSamplerProxy();
        sampler1.setDomain(targetHost);
        sampler1.setPort(Integer.parseInt(targetPort));
        sampler1.setPath("EXTRACT_FIRST_ENDPOINT_PATH");
        sampler1.setMethod("EXTRACT_FIRST_ENDPOINT_METHOD");
        sampler1.setName("EXTRACT_FIRST_ENDPOINT_NAME");
        sampler1.setUseKeepAlive(true);
        sampler1.setFollowRedirects(true);
        
        // Add result collector
        ResultCollector collector = new ResultCollector();
        collector.setFilename("EXTRACT_SCENARIO_NAME_results.jtl");
        
        // Build test tree
        ListedHashTree testPlanTree = new ListedHashTree();
        testPlanTree.add(testPlan);
        testPlanTree.add(testPlan, threadGroup);
        testPlanTree.add(threadGroup, sampler1);
        testPlanTree.add(threadGroup, collector);
        
        // Add more samplers for other endpoints from scenario workflow
        
        // Run test
        StandardJMeterEngine jmeter = new StandardJMeterEngine();
        jmeter.configure(testPlanTree);
        jmeter.run();
        
        System.out.println("Test completed successfully");
    }}
}}
```

CRITICAL CONSTRAINTS:
- Use ONLY the JMeter 5.6 Traditional API template above - DO NOT modify imports or structure
- DO NOT add timers, assertions, CSV data sets, or any complex features beyond basic HTTP samplers
- DO NOT use these INVALID methods that will cause compilation errors:
  * DurationAssertion.setDuration() - DOES NOT EXIST (use setAllowedDuration() if needed)
  * ConstantTimer.setDelay(int) - WRONG TYPE (expects String, use setDelay("1000"))
  * CSVDataSet.SHARE_MODE_ALL - DOES NOT EXIST (use string values)
  * setDelayedStart() - DOES NOT EXIST in JMeter 5.6
  * ThreadGroup.setAllowedDuration() - DOES NOT EXIST (use setDuration() for ThreadGroup)
- MUST use threadGroup.setSamplerController(loopController) to fix main_controller error
- STICK TO THE TEMPLATE - only add more HTTPSamplerProxy objects, nothing else
- ONLY replace the EXTRACT_* placeholders with actual values from scenario:
  * EXTRACT_SCENARIO_NAME -> scenario name from JSON
  * EXTRACT_SCENARIO_DESCRIPTION -> scenario description from JSON  
  * EXTRACT_USER_COUNT -> user count as integer from scenario
  * EXTRACT_RAMPUP_SECONDS -> ramp-up time converted to seconds as integer
  * EXTRACT_DURATION_SECONDS -> total duration converted to seconds as integer
  * EXTRACT_FIRST_ENDPOINT_PATH -> first endpoint path from workflow
  * EXTRACT_FIRST_ENDPOINT_METHOD -> first endpoint method from workflow
  * EXTRACT_FIRST_ENDPOINT_NAME -> descriptive name for first endpoint
- Add more HTTPSamplerProxy objects and testPlanTree.add(threadGroup, sampler) calls for additional endpoints
- Return ONLY the complete working Java code, no explanations or markdown"""

        logger.info(f"Prompt length: {len(simple_prompt)} characters")
        logger.info(f"📝 === FULL PROMPT TO AI START === 📝")
        logger.info("=" * 80)
        logger.info(simple_prompt)
        logger.info("=" * 80)
        logger.info(f"📝 === FULL PROMPT TO AI END === 📝")
        
        logger.info("🤖 === CALLING BEDROCK AI === 🤖")
        
        ai_response = _call_claude_simple(simple_prompt)
        
        logger.info("🎉 === AI RESPONSE RECEIVED === 🎉")
        logger.info(f"📏 AI Response length: {len(ai_response)} characters")
        logger.info(f"📝 === FULL AI RESPONSE START === 📝")
        logger.info("=" * 80)
        logger.info(ai_response)
        logger.info("=" * 80)
        logger.info(f"📝 FULL AI RESPONSE END")
        logger.info(f"📝 === FULL AI RESPONSE END === 📝")
        # Basic validation
        logger.info("🔍 === VALIDATING AI RESPONSE === 🔍")
        
        # Check for common issues
        import re
        user_matches = re.findall(r'setNumThreads\((\d+)\)', ai_response)
        logger.info(f"🔢 Found setNumThreads values: {user_matches}")
        
        duration_matches = re.findall(r'setDuration\((\d+)\)', ai_response)
        logger.info(f"⏱️ Found setDuration values: {duration_matches}")
        
        rampup_matches = re.findall(r'setRampUp\((\d+)\)', ai_response)
        logger.info(f"📈 Found setRampUp values: {rampup_matches}")
        
        # Check for default values that indicate AI didn't parse scenario
        if "10" in user_matches:
            logger.warning("⚠️ AI may have used default 10 users")
        if "120" in duration_matches:
            logger.warning("⚠️ AI may have used default 120 seconds duration")
        if "30" in rampup_matches:
            logger.warning("⚠️ AI may have used default 30 seconds ramp-up")
        
        # Check endpoints
        if "/health" in ai_response:
            logger.warning("⚠️ AI used /health endpoint - may not have parsed scenario endpoints")
        else:
            logger.info("✅ AI avoided /health endpoint")
        
        # Count samplers
        sampler_count = ai_response.count("HTTPSamplerProxy sampler")
        logger.info(f"🔗 Number of samplers created: {sampler_count}")
        
        test_plans[filename] = ai_response
        logger.info(f"🎯 === AI SUCCESS: {filename} for {scenario_name} === 🎯")
    
    return test_plans

def _call_claude_simple(prompt: str) -> str:
    """Simple Claude call exactly like demo MCP server"""
    import boto3
    from botocore.config import Config
    
    logger.info("=== INITIALIZING BEDROCK CLIENT ===")
    
    # Initialize bedrock client with retry config like demo MCP server
    retry_config = Config(
        retries={
            'max_attempts': 10,
            'mode': 'adaptive'
        }
    )
    
    bedrock_region = os.environ.get("BEDROCK_REGION", "us-east-1")
    logger.info(f"Bedrock region: {bedrock_region}")
    
    bedrock_runtime = boto3.client(
        service_name="bedrock-runtime",
        region_name=bedrock_region,
        config=retry_config
    )
    logger.info("✅ Bedrock client initialized")
    
    modelId = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    logger.info(f"Using model: {modelId}")
    
    prompt_config = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,  # Match demo MCP server
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }

    body = json.dumps(prompt_config)
    logger.info(f"Request body length: {len(body)} characters")
    logger.info(f"Max tokens: {prompt_config['max_tokens']}")

    try:
        logger.info("🚀 === INVOKING BEDROCK MODEL === 🚀")
        logger.info(f"📤 Request body preview (first 500 chars): {body[:500]}...")
        
        response = bedrock_runtime.invoke_model(
            body=body, 
            modelId=modelId, 
            accept="application/json", 
            contentType="application/json"
        )
        logger.info("✅ Bedrock model invoked successfully")
        
        response_body = json.loads(response.get("body").read())
        logger.info(f"📥 Response body keys: {list(response_body.keys())}")
        logger.info(f"📥 === FULL BEDROCK RESPONSE BODY START === 📥")
        logger.info("=" * 80)
        logger.info(json.dumps(response_body, indent=2))
        logger.info("=" * 80)
        logger.info(f"📥 === FULL BEDROCK RESPONSE BODY END === 📥")
        
        content_list = response_body.get("content", [])
        logger.info(f"📋 Content list type: {type(content_list)}, length: {len(content_list) if isinstance(content_list, list) else 'N/A'}")
        
        if content_list and isinstance(content_list, list) and len(content_list) > 0:
            raw_text = content_list[0].get("text", "")
            logger.info(f"📏 Raw response text length: {len(raw_text)} characters")
            logger.info(f"📝 RAW CLAUDE RESPONSE START:")
            logger.info("=" * 80)
            logger.info(raw_text)
            logger.info("=" * 80)
            logger.info(f"📝 RAW CLAUDE RESPONSE END")
        else:
            logger.warning(f"❌ Invalid response format - content_list: {content_list}")
            raise Exception("Invalid response format from Claude")
        
        # Strip markdown code blocks like demo MCP server
        cleaned_text = _strip_markdown_code_blocks(raw_text)
        logger.info(f"🧹 Cleaned text length: {len(cleaned_text)} characters")
        logger.info(f"📝 CLEANED CLAUDE RESPONSE START:")
        logger.info("=" * 80)
        logger.info(cleaned_text)
        logger.info("=" * 80)
        logger.info(f"📝 CLEANED CLAUDE RESPONSE END")
        
        return cleaned_text
        
    except Exception as e:
        logger.warning(f"Failed to call Claude, will be handled upstream: {str(e)}")
        logger.debug(f"Exception type: {type(e).__name__}")
        import traceback
        logger.debug(f"Full traceback: {traceback.format_exc()}")
        raise

# Removed complex extraction functions - now letting AI handle everything

def _parse_time_to_seconds(time_str: str) -> int:
    """Parse time strings like '45 minutes', '10 seconds' to seconds"""
    if isinstance(time_str, int):
        return time_str
    
    time_str = str(time_str).lower().strip()
    
    if 'minute' in time_str:
        return int(time_str.split()[0]) * 60
    elif 'second' in time_str:
        return int(time_str.split()[0])
    elif 'hour' in time_str:
        return int(time_str.split()[0]) * 3600
    else:
        # Try to parse as number (assume seconds)
        try:
            return int(float(time_str))
        except:
            return 120  # Default fallback



# Fallback functions removed - using AI only



def _strip_markdown_code_blocks(text: str) -> str:
    """Strip markdown code blocks from AI response"""
    if not text:
        logger.info("Empty text provided to _strip_markdown_code_blocks")
        return text
    
    logger.info(f"=== STRIPPING MARKDOWN ===")
    logger.info(f"Input text length: {len(text)}")
    logger.info(f"Starts with: '{text[:50]}...'")
    logger.info(f"Ends with: '...{text[-50:]}'")
    
    # Remove ```java and ``` markers
    text = text.strip()
    
    # Check if it starts with a code block
    if text.startswith('```java'):
        logger.info("Found ```java opening marker")
        # Find the end of the opening marker
        start_idx = text.find('\n')
        if start_idx != -1:
            text = text[start_idx + 1:]
            logger.info(f"Removed ```java marker, new length: {len(text)}")
    elif text.startswith('```'):
        logger.info("Found generic ``` opening marker")
        # Generic code block
        start_idx = text.find('\n')
        if start_idx != -1:
            text = text[start_idx + 1:]
            logger.info(f"Removed ``` marker, new length: {len(text)}")
    
    # Remove closing ```
    if text.endswith('```'):
        logger.info("Found closing ``` marker")
        text = text[:-3].rstrip()
        logger.info(f"Removed closing marker, final length: {len(text)}")
    
    logger.info(f"Final cleaned text starts with: '{text[:50]}...'")
    return text





def _generate_jmx_fallback(scenario_name: str, scenario_config: Dict) -> str:
    """Generate basic JMX file as fallback"""
    
    users = scenario_config.get('users', 100)
    ramp_up = scenario_config.get('ramp_up_time', '5m')
    duration = scenario_config.get('duration', '10m')
    
    ramp_up_seconds = _time_to_seconds(ramp_up)
    duration_seconds = _time_to_seconds(duration)
    
    jmx_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="{scenario_name.title()} Test Plan">
      <stringProp name="TestPlan.comments">Generated test plan for {scenario_name}</stringProp>
      <boolProp name="TestPlan.functional_mode">false</boolProp>
      <boolProp name="TestPlan.serialize_threadgroups">false</boolProp>
      <elementProp name="TestPlan.arguments" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables">
        <collectionProp name="Arguments.arguments"/>
      </elementProp>
      <stringProp name="TestPlan.user_define_classpath"></stringProp>
    </TestPlan>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="{scenario_name.title()} Thread Group">
        <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
        <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlGui" testclass="LoopController" testname="Loop Controller">
          <boolProp name="LoopController.continue_forever">false</boolProp>
          <intProp name="LoopController.loops">-1</intProp>
        </elementProp>
        <stringProp name="ThreadGroup.num_threads">{users}</stringProp>
        <stringProp name="ThreadGroup.ramp_time">{ramp_up_seconds}</stringProp>
        <boolProp name="ThreadGroup.scheduler">true</boolProp>
        <stringProp name="ThreadGroup.duration">{duration_seconds}</stringProp>
        <stringProp name="ThreadGroup.delay"></stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="HTTP Request">
          <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="User Defined Variables">
            <collectionProp name="Arguments.arguments"/>
          </elementProp>
          <stringProp name="HTTPSampler.domain">${{__P(target.host,localhost)}}</stringProp>
          <stringProp name="HTTPSampler.port">${{__P(target.port,8080)}}</stringProp>
          <stringProp name="HTTPSampler.protocol">http</stringProp>
          <stringProp name="HTTPSampler.contentEncoding"></stringProp>
          <stringProp name="HTTPSampler.path">/api/test</stringProp>
          <stringProp name="HTTPSampler.method">GET</stringProp>
          <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
          <boolProp name="HTTPSampler.auto_redirects">false</boolProp>
          <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
          <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
          <stringProp name="HTTPSampler.embedded_url_re"></stringProp>
          <stringProp name="HTTPSampler.connect_timeout"></stringProp>
          <stringProp name="HTTPSampler.response_timeout"></stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
        <ResultCollector guiclass="ViewResultsFullVisualizer" testclass="ResultCollector" testname="View Results Tree">
          <boolProp name="ResultCollector.error_logging">false</boolProp>
          <objProp>
            <name>saveConfig</name>
            <value class="SampleSaveConfiguration">
              <time>true</time>
              <latency>true</latency>
              <timestamp>true</timestamp>
              <success>true</success>
              <label>true</label>
              <code>true</code>
              <message>true</message>
              <threadName>true</threadName>
              <dataType>true</dataType>
              <encoding>false</encoding>
              <assertions>true</assertions>
              <subresults>true</subresults>
              <responseData>false</responseData>
              <samplerData>false</samplerData>
              <xml>false</xml>
              <fieldNames>true</fieldNames>
              <responseHeaders>false</responseHeaders>
              <requestHeaders>false</requestHeaders>
              <responseDataOnError>false</responseDataOnError>
              <saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>
              <assertionsResultsToSave>0</assertionsResultsToSave>
              <bytes>true</bytes>
              <sentBytes>true</sentBytes>
              <url>true</url>
              <threadCounts>true</threadCounts>
              <idleTime>true</idleTime>
              <connectTime>true</connectTime>
            </value>
          </objProp>
          <stringProp name="filename"></stringProp>
        </ResultCollector>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>'''
    
    return jmx_content

def _time_to_seconds(time_str: str) -> int:
    """Convert time string to seconds"""
    if not time_str:
        return 300  # Default 5 minutes
    
    time_str = time_str.lower().strip()
    
    if time_str.endswith('s'):
        return int(time_str[:-1])
    elif time_str.endswith('m'):
        return int(time_str[:-1]) * 60
    elif time_str.endswith('h'):
        return int(time_str[:-1]) * 3600
    else:
        # Assume seconds if no unit
        try:
            return int(time_str)
        except ValueError:
            return 300