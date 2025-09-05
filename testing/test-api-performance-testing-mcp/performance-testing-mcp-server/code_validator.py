"""
Code Validator Module
Validates and corrects generated JMeter test plans by compiling them
"""

import json
import logging
import os
import re
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

def validate_and_fix_test_plans(test_plans: Dict[str, str]) -> Dict[str, Any]:
    """
    Validate and fix generated test plans using pattern-based validation
    Focuses on the top 4 common AI errors without full compilation
    
    Args:
        test_plans: Dictionary of filename -> code content
    
    Returns:
        Validation results with fixed code
    """
    try:
        logger.info(f"Validating {len(test_plans)} test plans")
        
        validation_results = {
            'status': 'success',
            'total_plans': len(test_plans),
            'validated_plans': {},
            'validation_errors': [],
            'fixes_applied': []
        }
        
        for filename, code_content in test_plans.items():
            logger.info(f"Validating {filename}")
            
            # Fix common AI issues
            fixed_code, fixes = _fix_common_issues(filename, code_content)
            
            # Validate the fixed code
            validation_issues = _validate_java_syntax(filename, fixed_code)
            
            if not validation_issues:
                validation_results['validated_plans'][filename] = fixed_code
                if fixes:
                    validation_results['fixes_applied'].extend([f"{filename}: {fix}" for fix in fixes])
                logger.info(f"✅ {filename} validated successfully")
            else:
                # Try additional fixes for validation issues
                auto_fixed_code, auto_fixes = _auto_fix_validation_issues(
                    filename, fixed_code, validation_issues
                )
                
                if auto_fixed_code:
                    # Re-validate after auto-fix
                    retry_issues = _validate_java_syntax(filename, auto_fixed_code)
                    if not retry_issues:
                        validation_results['validated_plans'][filename] = auto_fixed_code
                        validation_results['fixes_applied'].extend([f"{filename}: {fix}" for fix in fixes + auto_fixes])
                        logger.info(f"✅ {filename} auto-fixed and validated")
                    else:
                        validation_results['validation_errors'].append({
                            'filename': filename,
                            'issues': retry_issues
                        })
                        logger.error(f"❌ {filename} failed validation after auto-fix")
                else:
                    validation_results['validation_errors'].append({
                        'filename': filename,
                        'issues': validation_issues
                    })
                    logger.error(f"❌ {filename} failed validation")
        
        # Update status based on results
        if validation_results['validation_errors']:
            validation_results['status'] = 'partial_success' if validation_results['validated_plans'] else 'failed'
        
        logger.info(f"Validation complete: {len(validation_results['validated_plans'])}/{len(test_plans)} plans validated")
        return validation_results
        
    except Exception as e:
        logger.error(f"Error in code validation: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'total_plans': len(test_plans),
            'validated_plans': {},
            'validation_errors': [],
            'fixes_applied': []
        }

def _fix_common_issues(filename: str, code_content: str) -> Tuple[str, List[str]]:
    """Fix common issues in generated code"""
    fixes_applied = []
    fixed_code = code_content
    
    # Extract expected class name from filename
    expected_class_name = filename.replace('.java', '').replace('-', '').replace('_', '')
    
    # Fix 1: Ensure class name matches filename
    class_pattern = r'class\s+(\w+)\s*\{'
    class_match = re.search(class_pattern, fixed_code)
    
    if class_match:
        current_class_name = class_match.group(1)
        if current_class_name.lower() != expected_class_name.lower():
            fixed_code = re.sub(
                class_pattern, 
                f'class {expected_class_name} {{', 
                fixed_code
            )
            fixes_applied.append(f"Fixed class name: {current_class_name} -> {expected_class_name}")
    
    # Fix 2: Add missing imports
    required_imports = [
        'import org.apache.jmeter.testelement.TestPlan;',
        'import org.apache.jmeter.threads.ThreadGroup;',
        'import org.apache.jmeter.control.LoopController;',
        'import org.apache.jmeter.protocol.http.sampler.HTTPSamplerProxy;',
        'import org.apache.jmeter.reporters.ResultCollector;',
        'import org.apache.jmeter.util.JMeterUtils;',
        'import org.apache.jmeter.engine.StandardJMeterEngine;',
        'import org.apache.jorphan.collections.ListedHashTree;'
    ]
    
    for import_stmt in required_imports:
        if import_stmt not in fixed_code:
            # Add import at the beginning
            fixed_code = import_stmt + '\n' + fixed_code
            fixes_applied.append(f"Added missing import: {import_stmt}")
    
    # Fix 3: Ensure public class
    if 'public class' not in fixed_code and 'class ' in fixed_code:
        fixed_code = fixed_code.replace('class ', 'public class ')
        fixes_applied.append("Made class public")
    
    # Fix 4: Fix common JMeter API issues
    api_fixes = [
        # Fix DurationAssertion API
        (r'\.setDuration\((\d+)\);', r'.setAllowedDuration(\1);'),
        # Fix ConstantTimer API - convert int to string
        (r'\.setDelay\((\d+)\);', r'.setDelay("\1");'),
        # Fix CSVDataSet share mode
        (r'CSVDataSet\.SHARE_MODE_ALL', r'"shareMode.all"'),
        # Fix ThreadGroup setAllowedDuration -> setDuration
        (r'threadGroup\.setAllowedDuration\((\d+)\);', r'threadGroup.setDuration(\1);'),
        # Fix ThreadGroup duration (ensure scheduler is set)
        (r'threadGroup\.setDuration\((\d+)\);', r'threadGroup.setScheduler(true);\n        threadGroup.setDuration(\1);'),
        # Fix LoopController
        (r'loopController\.setLoops\(-1\);', r'loopController.setLoops(-1); // Infinite loops with scheduler'),
    ]
    
    for pattern, replacement in api_fixes:
        if re.search(pattern, fixed_code):
            fixed_code = re.sub(pattern, replacement, fixed_code)
            fixes_applied.append(f"Fixed JMeter API usage: {pattern}")
    
    return fixed_code, fixes_applied

def _validate_java_syntax(filename: str, code_content: str) -> List[str]:
    """Validate Java syntax using pattern matching (no compilation needed)"""
    issues = []
    
    # Check 1: Class declaration exists
    if not re.search(r'(public\s+)?class\s+\w+\s*\{', code_content):
        issues.append("No class declaration found")
    
    # Check 2: Main method exists
    if not re.search(r'public\s+static\s+void\s+main\s*\(\s*String\[\]\s+\w+\s*\)', code_content):
        issues.append("No main method found")
    
    # Check 3: Basic bracket matching
    open_braces = code_content.count('{')
    close_braces = code_content.count('}')
    if open_braces != close_braces:
        issues.append(f"Unmatched braces: {open_braces} open, {close_braces} close")
    
    # Check 4: Basic parentheses matching
    open_parens = code_content.count('(')
    close_parens = code_content.count(')')
    if open_parens != close_parens:
        issues.append(f"Unmatched parentheses: {open_parens} open, {close_parens} close")
    
    # Check 5: Required imports present
    required_imports = [
        'org.apache.jmeter.testelement.TestPlan',
        'org.apache.jmeter.threads.ThreadGroup',
        'org.apache.jmeter.util.JMeterUtils',
        'org.apache.jmeter.engine.StandardJMeterEngine'
    ]
    
    for required_import in required_imports:
        if required_import not in code_content:
            issues.append(f"Missing required import: {required_import}")
    
    return issues

def _auto_fix_validation_issues(filename: str, code_content: str, issues: List[str]) -> Tuple[str, List[str]]:
    """Attempt to automatically fix validation issues"""
    fixes_applied = []
    fixed_code = code_content
    
    for issue in issues:
        # Fix missing imports
        if "Missing required import:" in issue:
            import_class = issue.replace("Missing required import: ", "")
            import_stmt = f"import {import_class};"
            if import_stmt not in fixed_code:
                fixed_code = import_stmt + '\n' + fixed_code
                fixes_applied.append(f"Added missing import: {import_class}")
        
        # Fix missing public class
        if "No class declaration found" in issue:
            # Try to find and fix class declaration
            class_match = re.search(r'class\s+(\w+)\s*\{', fixed_code)
            if class_match:
                fixed_code = re.sub(r'class\s+(\w+)\s*\{', r'public class \1 {', fixed_code)
                fixes_applied.append("Made class public")
    
    if fixes_applied:
        return fixed_code, fixes_applied
    else:
        return None, []

def _create_fallback_test_plan(filename: str) -> str:
    """Create a simple fallback test plan that compiles"""
    class_name = filename.replace('.java', '').replace('-', '').replace('_', '')
    
    return f'''import org.apache.jmeter.testelement.TestPlan;
import org.apache.jmeter.threads.ThreadGroup;
import org.apache.jmeter.control.LoopController;
import org.apache.jmeter.protocol.http.sampler.HTTPSamplerProxy;
import org.apache.jmeter.reporters.ResultCollector;
import org.apache.jmeter.util.JMeterUtils;
import org.apache.jmeter.engine.StandardJMeterEngine;
import org.apache.jorphan.collections.ListedHashTree;

public class {class_name} {{
    public static void main(String[] args) throws Exception {{
        JMeterUtils.loadJMeterProperties("jmeter.properties");
        JMeterUtils.initLocale();
        
        String targetHost = System.getProperty("target.host", "localhost");
        String targetPort = System.getProperty("target.port", "8080");
        
        ListedHashTree testPlanTree = new ListedHashTree();
        TestPlan testPlan = new TestPlan("Fallback Test");
        ThreadGroup threadGroup = new ThreadGroup();
        threadGroup.setNumThreads(5);
        threadGroup.setRampUp(10);
        
        LoopController loopController = new LoopController();
        loopController.setLoops(2);
        threadGroup.setSamplerController(loopController);
        
        HTTPSamplerProxy sampler = new HTTPSamplerProxy();
        sampler.setDomain(targetHost);
        sampler.setPort(Integer.parseInt(targetPort));
        sampler.setPath("/health");
        sampler.setMethod("GET");
        
        ResultCollector collector = new ResultCollector();
        collector.setFilename("{class_name.lower()}-results.jtl");
        
        testPlanTree.add(testPlan);
        testPlanTree.add(testPlan, threadGroup);
        testPlanTree.add(threadGroup, sampler);
        testPlanTree.add(threadGroup, collector);
        
        StandardJMeterEngine engine = new StandardJMeterEngine();
        engine.configure(testPlanTree);
        engine.run();
        Thread.sleep(15000);
        
        System.out.println("Test completed! Check {class_name.lower()}-results.jtl for results.");
    }}
}}'''