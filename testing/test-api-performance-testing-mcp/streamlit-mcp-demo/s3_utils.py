"""
S3 utilities for reading performance testing artifacts
"""
import os
import io
import json
import pandas as pd
import boto3
from typing import Dict, List, Optional, Any
from botocore.exceptions import ClientError
try:
    # Use secure XML parser to prevent XXE attacks
    import defusedxml.ElementTree as ET
    XML_PARSER_SAFE = True
except ImportError:
    # Secure fallback: disable XML parsing entirely if defusedxml not available
    ET = None
    XML_PARSER_SAFE = False
    import warnings
    warnings.warn(
        "defusedxml not available. XML parsing disabled for security. "
        "Install defusedxml to enable XML JTL parsing: pip install defusedxml", 
        UserWarning
    )
import numpy as np

# Configuration
BUCKET = os.environ.get("ARTIFACT_BUCKET", "")
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"

# S3 client
s3 = boto3.client("s3") if not DEMO_MODE else None

def _prefix(session_id: str, kind: Optional[str] = None) -> str:
    """Build S3 prefix for session artifacts"""
    base = f"perf-pipeline/{session_id}/"
    return base + (f"{kind}/" if kind else "")

def list_artifacts(session_id: str, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List artifacts in S3 for a given session and optional kind
    
    Args:
        session_id: Session identifier
        kind: Optional artifact type (scenarios, plans, results, analysis)
    
    Returns:
        List of artifact metadata dictionaries
    """
    if not BUCKET:
        raise ValueError("ARTIFACT_BUCKET environment variable is required")
    
    if DEMO_MODE:
        return _demo_artifacts(session_id, kind)
    
    try:
        response = s3.list_objects_v2(Bucket=BUCKET, Prefix=_prefix(session_id, kind))
        contents = response.get("Contents", [])
        
        artifacts = []
        for obj in contents:
            # Skip directory markers
            if obj["Key"].endswith("/"):
                continue
                
            artifacts.append({
                "key": obj["Key"],
                "name": obj["Key"].split("/")[-1],  # Just filename
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat()
            })
        
        return artifacts
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            raise ValueError(f"S3 bucket '{BUCKET}' does not exist")
        raise RuntimeError(f"Failed to list artifacts: {str(e)}")

def read_text(bucket: str, key: str) -> str:
    """Read text content from S3 object"""
    if DEMO_MODE:
        return _demo_text_content(key)
    
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        return response["Body"].read().decode("utf-8")
    except ClientError as e:
        raise RuntimeError(f"Failed to read {key}: {str(e)}")

def read_json(bucket: str, key: str) -> Dict[str, Any]:
    """Read and parse JSON content from S3 object"""
    try:
        text_content = read_text(bucket, key)
        return json.loads(text_content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON in {key}: {str(e)}")

def presign(bucket: str, key: str, expires: int = 3600) -> str:
    """Generate presigned URL for S3 object download"""
    if DEMO_MODE:
        return f"https://demo-bucket.s3.amazonaws.com/{key}?demo=true"
    
    try:
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires
        )
    except ClientError as e:
        raise RuntimeError(f"Failed to generate presigned URL: {str(e)}")

def read_jtl_summary(bucket: str, key: str) -> Dict[str, Any]:
    """
    Read JTL file and compute performance summary statistics
    
    Args:
        bucket: S3 bucket name
        key: S3 object key for JTL file
    
    Returns:
        Dictionary with performance metrics
    """
    if DEMO_MODE:
        return _demo_jtl_summary(key)
    
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        
        # Detect format by sampling first 1000 bytes
        sample = body[:1000].decode("utf-8", "ignore")
        
        if "<testResults" in sample or "<httpSample" in sample:
            # XML JTL format
            return _parse_xml_jtl(body)
        else:
            # CSV JTL format
            return _parse_csv_jtl(body)
            
    except ClientError as e:
        raise RuntimeError(f"Failed to read JTL file {key}: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Failed to parse JTL file {key}: {str(e)}")

def _parse_xml_jtl(body: bytes) -> Dict[str, Any]:
    """Parse XML format JTL file"""
    if not XML_PARSER_SAFE or ET is None:
        raise RuntimeError(
            "XML parsing disabled for security. Install defusedxml to enable: pip install defusedxml"
        )
    
    try:
        root = ET.fromstring(body)
        latencies = []
        errors = 0
        
        for sample in root:
            # Get response time (t attribute)
            latency = int(sample.get("t", "0"))
            latencies.append(latency)
            
            # Check success (s attribute, default true)
            if sample.get("s", "true") != "true":
                errors += 1
        
        if not latencies:
            return {"requests": 0, "errors_pct": 0, "p95": None, "p99": None}
        
        arr = pd.Series(latencies)
        return {
            "requests": len(arr),
            "errors_pct": (errors / len(arr)) * 100,
            "p95": float(arr.quantile(0.95)),
            "p99": float(arr.quantile(0.99)),
            "avg": float(arr.mean()),
            "min": float(arr.min()),
            "max": float(arr.max())
        }
        
    except Exception as e:
        if hasattr(e, 'msg'):  # defusedxml ParseError
            raise RuntimeError(f"Invalid XML in JTL file: {str(e)}")
        else:
            raise RuntimeError(f"Failed to parse XML JTL file: {str(e)}")

def _parse_csv_jtl(body: bytes) -> Dict[str, Any]:
    """Parse CSV format JTL file"""
    try:
        df = pd.read_csv(io.BytesIO(body))
        
        if df.empty:
            return {"requests": 0, "errors_pct": 0, "p95": None, "p99": None}
        
        # Find response time column (usually 'elapsed' or 'Elapsed')
        time_col = None
        for col in ["elapsed", "Elapsed", "responseTime", "t"]:
            if col in df.columns:
                time_col = col
                break
        
        if not time_col:
            # Use first numeric column as fallback
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            time_col = numeric_cols[0] if len(numeric_cols) > 0 else df.columns[0]
        
        # Count errors (success column or responseCode)
        errors = 0
        if "success" in df.columns:
            errors = (df["success"] == False).sum()
        elif "responseCode" in df.columns:
            errors = (~df["responseCode"].astype(str).str.startswith("2")).sum()
        
        # Calculate statistics
        times = pd.to_numeric(df[time_col], errors='coerce').dropna()
        
        if times.empty:
            return {"requests": len(df), "errors_pct": 0, "p95": None, "p99": None}
        
        return {
            "requests": len(df),
            "errors_pct": (errors / len(df)) * 100,
            "p95": float(times.quantile(0.95)),
            "p99": float(times.quantile(0.99)),
            "avg": float(times.mean()),
            "min": float(times.min()),
            "max": float(times.max())
        }
        
    except Exception as e:
        raise RuntimeError(f"Failed to parse CSV JTL: {str(e)}")

# tail_logs function removed - live logs feature was removed from UI

def _demo_artifacts(session_id: str, kind: Optional[str]) -> List[Dict[str, Any]]:
    """Generate demo artifacts for DEMO_MODE"""
    all_artifacts = [
        {"key": f"perf-pipeline/{session_id}/scenarios.json", "name": "scenarios.json", "size": 2048, "last_modified": "2025-01-20T10:00:00Z"},
        {"key": f"perf-pipeline/{session_id}/plans/TestPlan01.java", "name": "TestPlan01.java", "size": 4096, "last_modified": "2025-01-20T10:05:00Z"},
        {"key": f"perf-pipeline/{session_id}/plans/TestPlan02.java", "name": "TestPlan02.java", "size": 3584, "last_modified": "2025-01-20T10:05:00Z"},
        {"key": f"perf-pipeline/{session_id}/results/testplan01_results.jtl", "name": "testplan01_results.jtl", "size": 8192, "last_modified": "2025-01-20T10:15:00Z"},
        {"key": f"perf-pipeline/{session_id}/results/testplan02_results.jtl", "name": "testplan02_results.jtl", "size": 7680, "last_modified": "2025-01-20T10:15:00Z"},
        {"key": f"perf-pipeline/{session_id}/analysis/results_analysis.json", "name": "results_analysis.json", "size": 1536, "last_modified": "2025-01-20T10:20:00Z"}
    ]
    
    if kind:
        return [a for a in all_artifacts if f"/{kind}/" in a["key"]]
    return all_artifacts

def _demo_text_content(key: str) -> str:
    """Generate demo text content based on file type"""
    if key.endswith("scenarios.json"):
        return json.dumps({
            "load_test": {"users": 100, "duration": "10m", "ramp_up": "2m"},
            "stress_test": {"users": 500, "duration": "15m", "ramp_up": "5m"}
        }, indent=2)
    elif key.endswith(".java"):
        return """public class TestPlan01 {
    public static void main(String[] args) {
        // Demo JMeter test plan
        System.out.println("Running performance test...");
    }
}"""
    elif key.endswith("results_analysis.json"):
        return json.dumps({
            "performance_grade": "A",
            "summary": "Excellent performance with 99.5% success rate",
            "recommendations": ["Consider increasing load", "Monitor memory usage"]
        }, indent=2)
    else:
        return f"Demo content for {key}"

def _demo_jtl_summary(key: str) -> Dict[str, Any]:
    """Generate demo JTL summary"""
    return {
        "requests": 10000,
        "errors_pct": 0.5,
        "p95": 245.0,
        "p99": 456.0,
        "avg": 123.5,
        "min": 45.0,
        "max": 890.0
    }

# _demo_logs function removed - live logs feature was removed from UI