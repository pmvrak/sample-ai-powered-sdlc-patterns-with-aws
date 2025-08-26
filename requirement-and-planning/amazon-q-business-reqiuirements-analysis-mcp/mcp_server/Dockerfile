FROM public.ecr.aws/lambda/python:3.11

# Copy requirements file
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install the specified packages
RUN pip install -r requirements.txt

# Copy the necessary files from root directory
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}/
COPY amazon_q_jsonrpc_server.py ${LAMBDA_TASK_ROOT}/
COPY atlassian_integration.py ${LAMBDA_TASK_ROOT}/
# auth_lambda.py removed - using integrated auth
COPY __init__.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler (now in root)
CMD [ "lambda_handler.handler" ]