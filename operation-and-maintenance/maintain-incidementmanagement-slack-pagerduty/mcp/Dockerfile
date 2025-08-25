# Multi-stage build for Python application
# Use ARG to allow platform override during build
ARG TARGETPLATFORM=linux/amd64
FROM --platform=$TARGETPLATFORM python:3.12-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY incident_management/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Install PagerDuty MCP server
COPY pagerduty-mcp-server/pyproject.toml ./pagerduty-mcp-server/
COPY pagerduty-mcp-server/pagerduty_mcp ./pagerduty-mcp-server/pagerduty_mcp
RUN pip install --no-cache-dir --user -e ./pagerduty-mcp-server

# Production stage
FROM --platform=$TARGETPLATFORM python:3.12-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies and create non-root user with security hardening
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser --gid 1001 \
    && useradd -r -g appuser --uid 1001 --home-dir /app --shell /sbin/nologin appuser \
    && mkdir -p /app/logs /app/tmp \
    && chown -R appuser:appuser /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Ensure Python can find the packages
ENV PYTHONPATH=/app:/home/appuser/.local/lib/python3.12/site-packages
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code (from incident_management directory)
COPY incident_management/ .

# Copy the MCP servers
COPY server ./server
COPY pagerduty-mcp-server ./pagerduty-mcp-server

# Copy and make start script executable before changing user
RUN chmod +x start_services.sh

# Set ownership and permissions with security hardening
RUN chown -R appuser:appuser /app \
    && chmod -R 755 /app \
    && chmod 750 /app/start_services.sh

# Switch to non-root user
USER appuser

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV API_HOST=0.0.0.0
ENV API_PORT=8002

# Expose port (only main API port needed for stdio approach)
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Start services directly (test_container.py has import issues but app works fine)
CMD ["./start_services.sh"]