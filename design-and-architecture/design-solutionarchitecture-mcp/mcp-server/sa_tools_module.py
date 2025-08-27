"""
SA Tools Module - Integrated into MCP Server
Contains functionality from the original SA Tool Lambda
"""

import json
import os
import boto3
from langchain_community.embeddings import BedrockEmbeddings
from langchain_community.vectorstores import FAISS
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Bedrock client with increased retry configuration
from botocore.config import Config

retry_config = Config(
    retries={
        'max_attempts': 10,  # Increased from default 4 to 10
        'mode': 'adaptive'   # Use adaptive retry mode for better handling
    }
)

bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name=os.environ.get("BEDROCK_REGION", "us-east-1"),
    config=retry_config
)

def call_claude_sonnet(prompt):
    """Call Claude 3 Sonnet model with the given prompt"""
    prompt_config = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
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

    # Use the model ID from environment variable or default to Claude 3.7 Sonnet v1 cross-region inference
    modelId = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    accept = "application/json"
    contentType = "application/json"

    try:
        # Apply rate limiting before making the request
        from mcp_server import bedrock_rate_limiter
        bedrock_rate_limiter.wait_if_needed()
        
        response = bedrock_runtime.invoke_model(
            body=body, modelId=modelId, accept=accept, contentType=contentType
        )
        response_body = json.loads(response.get("body").read())
        results = response_body.get("content")[0].get("text")
        return results
    except Exception as e:
        logger.error(f"Error calling Claude model: {str(e)}")
        return f"Error generating response: {str(e)}"

def aws_well_arch_tool(query):
    """
    Use this tool for any AWS related question to help customers understand best practices on building on AWS.
    It will use the relevant context from the AWS Well-Architected Framework to answer the customer's query.
    """
    try:
        # Find docs - Initialize embeddings the same way as the original
        embeddings = BedrockEmbeddings(
            client=bedrock_runtime,
            region_name=os.environ.get("BEDROCK_REGION", "us-east-1"),
            model_id="amazon.titan-embed-text-v1"
        )
        vectorstore_path = os.environ.get("VECTORSTORE_PATH", "/var/task/local_index")
        logger.info(f"Loading vector store from {vectorstore_path}")
        
        # Check if the directory exists
        if os.path.exists(vectorstore_path):
            logger.info(f"Vector store directory exists: {vectorstore_path}")
            # List files in the directory
            files = os.listdir(vectorstore_path)
            logger.info(f"Files in vector store directory: {files}")
        else:
            logger.error(f"Vector store directory does not exist: {vectorstore_path}")
        
        vectorstore = FAISS.load_local(vectorstore_path, embeddings, allow_dangerous_deserialization=True)
        docs = vectorstore.similarity_search(query)
        context = ""

        doc_sources_string = ""
        for doc in docs:
            doc_sources_string += doc.metadata["source"] + "\n"
            context += doc.page_content

        prompt = f"""Use the following pieces of context to answer the question at the end.

        {context}

        Question: {query}
        Answer:"""

        generated_text = call_claude_sonnet(prompt)
        logger.info("Generated response for AWS Well-Architected query")

        resp_string = (
            generated_text
            + "\n Here is some documentation for more details: \n"
            + doc_sources_string
        )
        return resp_string
    except Exception as e:
        logger.error(f"Error in aws_well_arch_tool: {str(e)}")
        return f"Error processing AWS Well-Architected query: {str(e)}"

def code_gen_tool(prompt):
    """
    Use this tool only when you need to generate code based on a customer's request.
    """
    try:
        prompt_ending = " Just return the code, do not provide an explanation."
        generated_text = call_claude_sonnet(prompt + prompt_ending)
        logger.info("Generated code response")
        return generated_text
    except Exception as e:
        logger.error(f"Error in code_gen_tool: {str(e)}")
        return f"Error generating code: {str(e)}"