"""
Results Analyzer Module
AI-powered analysis of performance test results with intelligent insights
"""

import json
import logging
import os
import pandas as pd
import numpy as np
from typing import Dict, Any, List
import boto3
from datetime import datetime
import statistics

logger = logging.getLogger(__name__)

def analyze_results(session_id: str, s3_client, bedrock_client) -> Dict[str, Any]:
    """
    Analyze performance test results using AI to generate insights
    
    Args:
        session_id: Session ID linking to test results
        s3_client: AWS S3 client
        bedrock_client: AWS Bedrock client
    
    Returns:
        AI-generated analysis and insights
    """
    try:
        logger.info(f"Analyzing results for session {session_id}")
        
        # Load and process all result files
        results_data = _load_and_process_results(session_id, s3_client)
        
        # Generate statistical analysis
        stats_analysis = _generate_statistical_analysis(results_data)
        
        # Generate AI insights
        ai_insights = _generate_ai_insights(results_data, stats_analysis, bedrock_client)
        
        # Combine analysis
        full_analysis = {
            'session_id': session_id,
            'analysis_timestamp': datetime.utcnow().isoformat(),
            'statistical_analysis': stats_analysis,
            'ai_insights': ai_insights,
            'recommendations': ai_insights.get('recommendations', []),
            'performance_grade': ai_insights.get('performance_grade', 'Unknown'),
            'summary': ai_insights.get('summary', 'Analysis completed')
        }
        
        # Store analysis in S3
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        s3_key = f"perf-pipeline/{session_id}/analysis/results_analysis.json"
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(full_analysis, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Analysis completed and stored at s3://{bucket_name}/{s3_key}")
        
        return {
            'session_id': session_id,
            'status': 'completed',
            'analysis': full_analysis,
            's3_location': f"s3://{bucket_name}/{s3_key}"
        }
        
    except Exception as e:
        logger.error(f"Error analyzing results: {str(e)}")
        return {
            'session_id': session_id,
            'status': 'error',
            'error': str(e)
        }

def _load_and_process_results(session_id: str, s3_client) -> Dict[str, Any]:
    """Load and process all result files from S3"""
    bucket_name = os.environ.get('S3_BUCKET_NAME')
    results_prefix = f"perf-pipeline/{session_id}/results/"
    
    results_data = {}
    
    try:
        # List all result files
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=results_prefix)
        
        if 'Contents' not in response:
            logger.warning(f"No results found for session {session_id}")
            return results_data
        
        for obj in response['Contents']:
            key = obj['Key']
            filename = key.split('/')[-1]
            
            if filename.endswith('.jtl'):
                logger.info(f"Processing result file: {filename}")
                
                # Download and parse JTL file
                file_obj = s3_client.get_object(Bucket=bucket_name, Key=key)
                content = file_obj['Body'].read().decode('utf-8')
                
                # Parse JTL data
                parsed_data = _parse_jtl_data(content, filename)
                results_data[filename] = parsed_data
        
        return results_data
        
    except Exception as e:
        logger.error(f"Error loading results: {str(e)}")
        return results_data

def _parse_jtl_data(content: str, filename: str) -> Dict[str, Any]:
    """Parse JTL file content into structured data"""
    lines = content.strip().split('\n')
    
    if len(lines) < 2:
        return {'error': 'Empty or invalid JTL file', 'filename': filename}
    
    # Parse header
    header = lines[0].split(',')
    
    # Parse data rows
    data_rows = []
    for line in lines[1:]:
        if line.strip():
            row_data = line.split(',')
            if len(row_data) >= len(header):
                data_rows.append(dict(zip(header, row_data)))
    
    if not data_rows:
        return {'error': 'No data rows found', 'filename': filename}
    
    # Calculate metrics
    response_times = []
    success_count = 0
    error_count = 0
    timestamps = []
    
    for row in data_rows:
        try:
            # Response time
            elapsed = int(row.get('elapsed', 0))
            response_times.append(elapsed)
            
            # Success/Error counting
            success = row.get('success', 'false').lower() == 'true'
            if success:
                success_count += 1
            else:
                error_count += 1
            
            # Timestamp for duration calculation
            timestamp = row.get('timeStamp', '')
            if timestamp:
                timestamps.append(timestamp)
                
        except (ValueError, KeyError) as e:
            logger.warning(f"Error parsing row in {filename}: {e}")
            continue
    
    total_requests = len(data_rows)
    
    # Calculate statistics
    metrics = {
        'filename': filename,
        'total_requests': total_requests,
        'successful_requests': success_count,
        'failed_requests': error_count,
        'success_rate': (success_count / total_requests * 100) if total_requests > 0 else 0,
        'error_rate': (error_count / total_requests * 100) if total_requests > 0 else 0,
    }
    
    if response_times:
        metrics.update({
            'avg_response_time': statistics.mean(response_times),
            'min_response_time': min(response_times),
            'max_response_time': max(response_times),
            'median_response_time': statistics.median(response_times),
            'p95_response_time': np.percentile(response_times, 95),
            'p99_response_time': np.percentile(response_times, 99),
        })
    
    # Calculate test duration and throughput
    if len(timestamps) >= 2:
        try:
            start_time = timestamps[0]
            end_time = timestamps[-1]
            
            # Parse timestamps (format: 2025/08/18 21:48:14.644)
            start_dt = datetime.strptime(start_time.split('.')[0], '%Y/%m/%d %H:%M:%S')
            end_dt = datetime.strptime(end_time.split('.')[0], '%Y/%m/%d %H:%M:%S')
            
            duration_seconds = (end_dt - start_dt).total_seconds()
            if duration_seconds > 0:
                metrics['test_duration_seconds'] = duration_seconds
                metrics['throughput_rps'] = total_requests / duration_seconds
            
        except Exception as e:
            logger.warning(f"Error calculating duration for {filename}: {e}")
    
    return metrics

def _generate_statistical_analysis(results_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate statistical analysis across all test results"""
    
    if not results_data:
        return {'error': 'No results data available'}
    
    analysis = {
        'test_plans_analyzed': len(results_data),
        'total_requests_across_all_tests': 0,
        'overall_success_rate': 0,
        'test_plan_summaries': {}
    }
    
    total_requests = 0
    total_successful = 0
    
    for filename, data in results_data.items():
        if 'error' in data:
            continue
            
        test_name = filename.replace('.jtl', '').replace('_', ' ').title()
        
        plan_summary = {
            'requests': data.get('total_requests', 0),
            'success_rate': data.get('success_rate', 0),
            'avg_response_time': data.get('avg_response_time', 0),
            'throughput': data.get('throughput_rps', 0),
            'p95_response_time': data.get('p95_response_time', 0)
        }
        
        analysis['test_plan_summaries'][test_name] = plan_summary
        
        total_requests += data.get('total_requests', 0)
        total_successful += data.get('successful_requests', 0)
    
    analysis['total_requests_across_all_tests'] = total_requests
    analysis['overall_success_rate'] = (total_successful / total_requests * 100) if total_requests > 0 else 0
    
    return analysis

def _generate_ai_insights(results_data: Dict[str, Any], stats_analysis: Dict[str, Any], bedrock_client) -> Dict[str, Any]:
    """Generate AI-powered insights from the performance test results"""
    
    system_prompt = """You are an expert performance testing analyst with deep knowledge of JMeter, load testing, and system performance optimization. 

Analyze the provided performance test results and provide:
1. Executive Summary (2-3 sentences)
2. Performance Grade (A-F scale)
3. Key Findings (3-5 bullet points)
4. Recommendations (3-5 actionable items)
5. Risk Assessment (High/Medium/Low with explanation)
6. Bottleneck Analysis
7. Scalability Assessment

Be specific, actionable, and focus on business impact. Use performance testing best practices."""

    user_prompt = f"""Analyze these performance test results:

STATISTICAL ANALYSIS:
{json.dumps(stats_analysis, indent=2)}

DETAILED METRICS PER TEST:
{json.dumps(results_data, indent=2)}

Provide a comprehensive analysis with specific insights about:
- System performance under different load conditions
- Response time patterns and outliers
- Error rates and reliability
- Throughput capabilities
- Scalability indicators
- Performance bottlenecks
- Recommendations for optimization

Format your response as JSON with the structure:
{{
    "executive_summary": "...",
    "performance_grade": "A/B/C/D/F",
    "key_findings": ["finding1", "finding2", ...],
    "recommendations": ["rec1", "rec2", ...],
    "risk_assessment": {{
        "level": "High/Medium/Low",
        "explanation": "..."
    }},
    "bottleneck_analysis": "...",
    "scalability_assessment": "...",
    "summary": "One sentence overall assessment"
}}"""

    try:
        prompt_config = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_prompt}]
                }
            ]
        }
        
        body = json.dumps(prompt_config)
        model_id = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
        
        response = bedrock_client.invoke_model(
            body=body,
            modelId=model_id,
            accept="application/json",
            contentType="application/json"
        )
        
        response_body = json.loads(response.get("body").read())
        content = response_body.get("content")
        
        if not content or len(content) == 0:
            logger.error("No content in Bedrock response")
            return _create_fallback_insights(stats_analysis)
        
        result_text = content[0].get("text")
        
        if not result_text:
            logger.error("No text in Bedrock response content")
            return _create_fallback_insights(stats_analysis)
        
        # Clean up markdown formatting if present
        cleaned_text = result_text.strip()
        if cleaned_text.startswith('```json'):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith('```'):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith('```'):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()
        
        # Try to parse as JSON
        try:
            parsed_result = json.loads(cleaned_text)
            return parsed_result
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Bedrock response as JSON: {e}")
            return _create_fallback_insights(stats_analysis)
            
    except Exception as e:
        logger.error(f"Error calling Bedrock for insights: {str(e)}")
        return _create_fallback_insights(stats_analysis)

def _create_fallback_insights(stats_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Create fallback insights when AI analysis fails"""
    
    total_requests = stats_analysis.get('total_requests_across_all_tests', 0)
    success_rate = stats_analysis.get('overall_success_rate', 0)
    
    # Determine grade based on success rate
    if success_rate >= 99:
        grade = "A"
    elif success_rate >= 95:
        grade = "B"
    elif success_rate >= 90:
        grade = "C"
    elif success_rate >= 80:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "executive_summary": f"Performance testing completed with {total_requests:,} total requests across {stats_analysis.get('test_plans_analyzed', 0)} test plans. Overall success rate: {success_rate:.1f}%.",
        "performance_grade": grade,
        "key_findings": [
            f"Processed {total_requests:,} requests across all test scenarios",
            f"Achieved {success_rate:.1f}% success rate",
            "System demonstrated basic functionality under load"
        ],
        "recommendations": [
            "Review detailed metrics for optimization opportunities",
            "Consider increasing load to find system limits",
            "Monitor system resources during peak load"
        ],
        "risk_assessment": {
            "level": "Low" if success_rate > 95 else "Medium" if success_rate > 90 else "High",
            "explanation": f"Based on {success_rate:.1f}% success rate across all tests"
        },
        "bottleneck_analysis": "Detailed analysis requires AI processing - check individual test metrics",
        "scalability_assessment": "System handled current load levels - recommend stress testing for limits",
        "summary": f"System achieved {success_rate:.1f}% success rate across {total_requests:,} requests"
    }