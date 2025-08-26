FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.11

# Install system dependencies
RUN yum update -y && \
    yum install -y \
    gcc \
    gcc-c++ \
    python3-devel \
    make \
    swig \
    graphviz \
    mesa-libGL \
    libX11 \
    zip \
    unzip \
    tar \
    bzip2 \
    && yum clean all

# Copy requirements first to leverage Docker cache
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install Python packages from requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Verify installations
RUN pip list && python -c "import faiss; import langchain; import langchain_community; import diagrams; import PIL; import mcp; print('All imports successful')"

# Copy function code
COPY . ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD ["lambda_handler.handler"]