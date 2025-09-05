FROM public.ecr.aws/lambda/python:3.11

# Install system dependencies
RUN yum update -y && \
    yum install -y gcc gcc-c++ && \
    yum clean all

# Copy requirements and install Python dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler (function_name.handler_method)
CMD ["lambda_handler.handler"]