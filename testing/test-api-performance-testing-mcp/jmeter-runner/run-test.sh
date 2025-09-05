#!/bin/bash

set -e

echo "Starting JMeter Test Runner"
echo "S3_BUCKET: ${S3_BUCKET}"
echo "SESSION_ID: ${SESSION_ID}"
echo "TARGET_HOST: ${TARGET_HOST}"
echo "TARGET_PORT: ${TARGET_PORT}"

# Validate required environment variables
if [ -z "$S3_BUCKET" ] || [ -z "$SESSION_ID" ]; then
    echo "ERROR: S3_BUCKET and SESSION_ID environment variables are required"
    exit 1
fi

# Create directories
mkdir -p /jmeter/plans
mkdir -p /jmeter/results
mkdir -p /jmeter/reports

# Copy JMeter properties to working directory for Java DSL tests
cp ${JMETER_HOME}/bin/jmeter.properties /jmeter/plans/

echo "Downloading test plans from S3..."
aws s3 sync s3://${S3_BUCKET}/perf-pipeline/${SESSION_ID}/plans/ /jmeter/plans/

# Check if any test plans were downloaded
if [ ! "$(ls -A /jmeter/plans/)" ]; then
    echo "ERROR: No test plans found in S3"
    exit 1
fi

echo "Found test plans:"
ls -la /jmeter/plans/

# Function to run JMX test
run_jmx_test() {
    local test_file=$1
    local base_name=$(basename "$test_file" .jmx)
    local result_file="/jmeter/results/${base_name}_results.jtl"
    local report_dir="/jmeter/reports/${base_name}_report"
    
    echo "Running JMX test: $test_file"
    
    # Run JMeter test
    jmeter -n \
        -t "$test_file" \
        -l "$result_file" \
        -e \
        -o "$report_dir" \
        -Jtarget.host="${TARGET_HOST}" \
        -Jtarget.port="${TARGET_PORT}" \
        -Jjmeter.reportgenerator.overall_granularity=60000 \
        -Jjmeter.reportgenerator.graph.responseTimeDistribution.property.set_granularity=100
    
    echo "Test completed: $base_name"
}

# Function to compile and run Java DSL test
run_java_test() {
    local test_file=$1
    local base_name=$(basename "$test_file" .java)
    
    echo "Compiling Java DSL test: $test_file"
    
    # Set classpath for JMeter
    export CLASSPATH="${JMETER_HOME}/lib/*:${JMETER_HOME}/lib/ext/*:/jmeter/plans"
    
    # Compile Java file (handle package structure)
    javac -cp "$CLASSPATH" -d /jmeter/plans "$test_file"
    
    if [ $? -eq 0 ]; then
        echo "Running Java DSL test: $base_name"
        
        # Determine class name with package
        local package_name=""
        if grep -q "package " "$test_file"; then
            package_name=$(grep "package " "$test_file" | sed 's/package //;s/;//' | tr -d ' ')
            class_name="${package_name}.${base_name}"
        else
            class_name="$base_name"
        fi
        
        echo "Executing class: $class_name"
        
        # Debug: Check Java version and available memory
        echo "=== DEBUGGING INFORMATION ==="
        echo "Java version:"
        java -version
        echo ""
        echo "Available memory info:"
        free -h || echo "free command not available"
        cat /proc/meminfo | head -5 || echo "meminfo not available"
        echo ""
        echo "Environment variables:"
        echo "JAVA_OPTS: '${JAVA_OPTS}'"
        echo "CLASSPATH: '${CLASSPATH}'"
        echo "JMETER_HOME: '${JMETER_HOME}'"
        echo ""
        echo "Container limits:"
        cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || echo "cgroup memory limit not available"
        echo ""
        
        # Try with minimal JVM settings first
        echo "=== ATTEMPTING JAVA EXECUTION ==="
        echo "Trying with minimal JVM settings..."
        if [ -z "$JAVA_OPTS" ]; then
            echo "Using default JVM options: -Xms512m -Xmx4g -XX:+UseG1GC"
            echo "Full command: java -cp \"$CLASSPATH\" -Xms512m -Xmx4g -XX:+UseG1GC -Dtarget.host=\"${TARGET_HOST}\" -Dtarget.port=\"${TARGET_PORT}\" -Djmeter.home=\"${JMETER_HOME}\" \"$class_name\""
            java -cp "$CLASSPATH" \
                -Xms512m \
                -Xmx4g \
                -XX:+UseG1GC \
                -Dtarget.host="${TARGET_HOST}" \
                -Dtarget.port="${TARGET_PORT}" \
                -Djmeter.home="${JMETER_HOME}" \
                "$class_name"
        else
            echo "Using custom JAVA_OPTS: $JAVA_OPTS"
            echo "Full command: java -cp \"$CLASSPATH\" $JAVA_OPTS -Dtarget.host=\"${TARGET_HOST}\" -Dtarget.port=\"${TARGET_PORT}\" -Djmeter.home=\"${JMETER_HOME}\" \"$class_name\""
            java -cp "$CLASSPATH" \
                $JAVA_OPTS \
                -Dtarget.host="${TARGET_HOST}" \
                -Dtarget.port="${TARGET_PORT}" \
                -Djmeter.home="${JMETER_HOME}" \
                "$class_name"
        fi
        
        echo "Java DSL test completed: $class_name"
        
        # Move any generated JTL files to results directory
        find /jmeter/plans -name "*.jtl" -exec mv {} /jmeter/results/ \;
        
    else
        echo "ERROR: Failed to compile $test_file"
        return 1
    fi
}

# Run specific test file if PLAN_NAME is specified, otherwise run all
cd /jmeter/plans

if [ -n "$PLAN_NAME" ]; then
    echo "Running specific test plan: $PLAN_NAME"
    
    # Check for JMX file
    if [ -f "${PLAN_NAME}.jmx" ]; then
        run_jmx_test "${PLAN_NAME}.jmx"
    # Check for Java file
    elif [ -f "${PLAN_NAME}.java" ]; then
        run_java_test "${PLAN_NAME}.java"
    # Check for file with extension already included
    elif [ -f "$PLAN_NAME" ]; then
        if [[ "$PLAN_NAME" == *.jmx ]]; then
            run_jmx_test "$PLAN_NAME"
        elif [[ "$PLAN_NAME" == *.java ]]; then
            run_java_test "$PLAN_NAME"
        fi
    else
        echo "ERROR: Test plan file not found: $PLAN_NAME"
        exit 1
    fi
else
    echo "Running all test plans..."
    
    for file in *.jmx; do
        if [ -f "$file" ]; then
            run_jmx_test "$file"
        fi
    done

    for file in *.java; do
        if [ -f "$file" ]; then
            run_java_test "$file"
        fi
    done
fi

# Generate summary report
echo "Generating test summary..."
cat > /jmeter/results/test_summary.json << EOF
{
    "session_id": "${SESSION_ID}",
    "execution_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "target": "${TARGET_HOST}:${TARGET_PORT}",
    "results_files": [
EOF

# Add results files to summary
first=true
for file in /jmeter/results/*.jtl; do
    if [ -f "$file" ]; then
        if [ "$first" = true ]; then
            first=false
        else
            echo "," >> /jmeter/results/test_summary.json
        fi
        echo "        \"$(basename "$file")\"" >> /jmeter/results/test_summary.json
    fi
done

cat >> /jmeter/results/test_summary.json << EOF
    ],
    "reports_generated": [
EOF

# Add report directories to summary
first=true
for dir in /jmeter/reports/*/; do
    if [ -d "$dir" ]; then
        if [ "$first" = true ]; then
            first=false
        else
            echo "," >> /jmeter/results/test_summary.json
        fi
        echo "        \"$(basename "$dir")\"" >> /jmeter/results/test_summary.json
    fi
done

cat >> /jmeter/results/test_summary.json << EOF
    ]
}
EOF

echo "Uploading results to S3..."
aws s3 sync /jmeter/results/ s3://${S3_BUCKET}/perf-pipeline/${SESSION_ID}/results/
aws s3 sync /jmeter/reports/ s3://${S3_BUCKET}/perf-pipeline/${SESSION_ID}/reports/

# Create execution status file
cat > /jmeter/results/execution_status.json << EOF
{
    "session_id": "${SESSION_ID}",
    "plan_name": "${PLAN_NAME:-all_plans}",
    "status": "completed",
    "completion_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "target": "${TARGET_HOST}:${TARGET_PORT}",
    "task_id": "${HOSTNAME}",
    "results_uploaded": true
}
EOF

echo "JMeter test execution completed successfully!"
echo "Plan executed: ${PLAN_NAME:-all_plans}"
echo "Results uploaded to: s3://${S3_BUCKET}/perf-pipeline/${SESSION_ID}/results/"
echo "Reports uploaded to: s3://${S3_BUCKET}/perf-pipeline/${SESSION_ID}/reports/"
echo "Status file created: execution_status.json"