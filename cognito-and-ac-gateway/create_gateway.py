#!/usr/bin/env python3
"""
AgentCore Gateway Creation Script

Creates an AgentCore Gateway with OAuth authentication using existing Amazon Cognito setup.
Also creates a sample Lambda function and registers it as a Gateway target.

Prerequisites:
1. Run setup-cognito.py to create Cognito User Pool and Client
2. Add the output credentials to .env file
3. Run this script to create Lambda, Gateway, and Target

Required environment variables in .env:
- COGNITO_USER_POOL_ID: Cognito User Pool ID
- COGNITO_APP_CLIENT_ID: Cognito App Client ID
- COGNITO_APP_CLIENT_SECRET: Cognito App Client Secret (optional)
- AWS_DEFAULT_REGION: AWS region (default: us-west-2)
"""

import os
import boto3
import json
import time
import zipfile
import io
from dotenv import load_dotenv
from botocore.exceptions import ClientError
import botocore

# Load environment variables from current directory
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(env_path)

print(f"Loading .env from: {os.path.abspath(env_path)}")

# Configuration (hardcoded)
GATEWAY_NAME = "sample-agentcore-gateway"
LAMBDA_FUNCTION_NAME = "agentcore-gateway-lambda"
LAMBDA_IAM_ROLE_NAME = "agentcore-gateway-lambda-role"


class GatewayCreator:
    """Creates and manages AgentCore Gateway with OAuth authentication"""

    def __init__(self, region: str = None):
        """
        Initialize Gateway Creator

        Args:
            region: AWS region (defaults to AWS_DEFAULT_REGION or us-west-2)
        """
        self.region = region or os.getenv('AWS_DEFAULT_REGION', 'us-west-2')
        self.gateway_client = boto3.client('bedrock-agentcore-control', region_name=self.region)
        self.iam_client = boto3.client('iam', region_name=self.region)
        self.lambda_client = boto3.client('lambda', region_name=self.region)
        self.sts_client = boto3.client('sts', region_name=self.region)

        # Load Cognito settings from environment (required)
        self.user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        self.client_id = os.getenv('COGNITO_APP_CLIENT_ID')
        self.client_secret = os.getenv('COGNITO_APP_CLIENT_SECRET')

        print(f"Loaded environment variables:")
        print(f"  COGNITO_USER_POOL_ID: {self.user_pool_id}")
        print(f"  COGNITO_APP_CLIENT_ID: {self.client_id}")
        print(f"  AWS_DEFAULT_REGION: {self.region}")

        if not self.user_pool_id or not self.client_id:
            raise ValueError(
                "COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID are required in .env file.\n"
                "Please run setup-cognito.py first and add the credentials to .env"
            )

        # Generate discovery URL
        self.discovery_url = f'https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}/.well-known/openid-configuration'

        # Get account ID
        self.account_id = self.sts_client.get_caller_identity()["Account"]

    def create_lambda_function_code(self) -> bytes:
        """
        Create Lambda function code as a zip file in memory

        Returns:
            bytes: Zip file contents
        """
        # Lambda function code
        lambda_code = '''
import json
from datetime import datetime, timezone

def lambda_handler(event, context):
    """
    Lambda function for AgentCore Gateway
    Returns current time in multiple formats

    Args:
        event: Contains the tool arguments
        context: Contains bedrockAgentCoreToolName in client_context.custom
    """
    # Get tool name from context
    toolName = context.client_context.custom['bedrockAgentCoreToolName']
    print(f"Context: {context.client_context}")
    print(f"Event: {event}")
    print(f"Original toolName: {toolName}")

    # Handle delimiter if present
    delimiter = "___"
    if delimiter in toolName:
        toolName = toolName[toolName.index(delimiter) + len(delimiter):]
    print(f"Converted toolName: {toolName}")

    if toolName == 'get_current_time_tool':
        # Get current time
        now = datetime.now(timezone.utc)

        # Optional timezone parameter from event
        timezone_str = event.get('timezone', 'UTC') if isinstance(event, dict) else 'UTC'

        # Return formatted time information
        result = {
            'timestamp': now.isoformat(),
            'unix_timestamp': int(now.timestamp()),
            'formatted': now.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'timezone': timezone_str,
            'message': 'Current time retrieved successfully'
        }

        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': f'Unknown tool: {toolName}'
            })
        }
'''

        # Create zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('lambda_function.py', lambda_code)

        return zip_buffer.getvalue()

    def create_lambda_iam_role(self, role_name: str) -> str:
        """
        Create IAM role for Lambda function

        Args:
            role_name: Name for the IAM role

        Returns:
            str: Role ARN
        """
        try:
            # Trust policy for Lambda
            assume_role_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "lambda.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }

            # Create role
            try:
                print(f"Creating Lambda IAM role: {role_name}")
                response = self.iam_client.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(assume_role_policy),
                    Description="IAM role for AgentCore Gateway Lambda function"
                )
                role_arn = response['Role']['Arn']
                print(f"Role created: {role_arn}")

            except self.iam_client.exceptions.EntityAlreadyExistsException:
                print(f"Role {role_name} already exists")
                response = self.iam_client.get_role(RoleName=role_name)
                role_arn = response['Role']['Arn']

            # Attach basic execution policy
            print("Attaching AWSLambdaBasicExecutionRole policy")
            try:
                self.iam_client.attach_role_policy(
                    RoleName=role_name,
                    PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
                )
            except Exception as e:
                print(f"Policy might already be attached: {e}")

            # Wait for role propagation
            print("Waiting for role to propagate (this may take up to 10 seconds)...")
            time.sleep(10)

            return role_arn

        except ClientError as e:
            print(f"❌ Error creating Lambda IAM role: {e}")
            raise

    def create_lambda_function(self, function_name: str, role_arn: str) -> str:
        """
        Create Lambda function (based on create_gateway_lambda from utils)

        Args:
            function_name: Name for the Lambda function
            role_arn: IAM role ARN

        Returns:
            str: Lambda function ARN
        """
        try:
            # Create Lambda function code
            print("Creating Lambda function code...")
            lambda_code = self.create_lambda_function_code()

            # Create Lambda function
            try:
                print(f"Creating Lambda function: {function_name}")
                response = self.lambda_client.create_function(
                    FunctionName=function_name,
                    Role=role_arn,
                    Runtime='python3.12',
                    Handler='lambda_function.lambda_handler',
                    Code={'ZipFile': lambda_code},
                    Description='Lambda function for Bedrock AgentCore Gateway',
                    PackageType='Zip'
                )
                lambda_arn = response['FunctionArn']
                print(f"✅ Lambda function created: {lambda_arn}")

            except self.lambda_client.exceptions.ResourceConflictException:
                print(f"Lambda function {function_name} already exists")
                response = self.lambda_client.get_function(FunctionName=function_name)
                lambda_arn = response['Configuration']['FunctionArn']
                print(f"Using existing Lambda: {lambda_arn}")

            return lambda_arn

        except ClientError as e:
            print(f"❌ Error creating Lambda function: {e}")
            raise

    def create_gateway_iam_role(self, role_name: str) -> dict:
        """
        Create IAM role for Gateway (based on create_agentcore_gateway_role from utils)

        Args:
            role_name: Name for the IAM role

        Returns:
            dict: Role information
        """
        try:
            # Trust policy (AssumeRolePolicyDocument)
            assume_role_policy_document = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "AssumeRolePolicy",
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "bedrock-agentcore.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole",
                        "Condition": {
                            "StringEquals": {
                                "aws:SourceAccount": f"{self.account_id}"
                            },
                            "ArnLike": {
                                "aws:SourceArn": f"arn:aws:bedrock-agentcore:{self.region}:{self.account_id}:*"
                            }
                        }
                    }
                ]
            }

            # Role policy with comprehensive permissions
            role_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "VisualEditor0",
                        "Effect": "Allow",
                        "Action": [
                            "bedrock-agentcore:*",
                            "bedrock:*",
                            "agent-credential-provider:*",
                            "iam:PassRole",
                            "secretsmanager:GetSecretValue",
                            "lambda:InvokeFunction"
                        ],
                        "Resource": "*"
                    }
                ]
            }

            assume_role_policy_json = json.dumps(assume_role_policy_document)
            role_policy_json = json.dumps(role_policy)

            # Create IAM Role
            try:
                print(f"Creating Gateway IAM role: {role_name}")
                agentcore_iam_role = self.iam_client.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=assume_role_policy_json,
                    Description="Role for AgentCore Gateway"
                )

                # Pause to make sure role is created and propagated
                print("Waiting for role to propagate...")
                time.sleep(10)

            except self.iam_client.exceptions.EntityAlreadyExistsException:
                print(f"Role {role_name} already exists, reusing it")

                # Get existing role
                agentcore_iam_role = self.iam_client.get_role(RoleName=role_name)

                # Update trust policy if needed
                try:
                    self.iam_client.update_assume_role_policy(
                        RoleName=role_name,
                        PolicyDocument=assume_role_policy_json
                    )
                    print(f"  Updated trust policy for {role_name}")
                except Exception as e:
                    print(f"  Could not update trust policy: {e}")

            # Attach the inline policy
            print(f"Attaching role policy to {role_name}")
            self.iam_client.put_role_policy(
                PolicyDocument=role_policy_json,
                PolicyName="AgentCorePolicy",
                RoleName=role_name
            )

            print(f"✅ Created role with ARN: {agentcore_iam_role['Role']['Arn']}")
            return agentcore_iam_role

        except ClientError as e:
            print(f"❌ Error creating IAM role: {e}")
            raise

    def get_or_create_gateway(
        self,
        gateway_name: str,
        role_arn: str,
        description: str = "AgentCore Gateway with OAuth"
    ) -> dict:
        """
        Get existing or create new AgentCore Gateway (idempotent)

        Args:
            gateway_name: Name for the gateway
            role_arn: IAM role ARN
            description: Gateway description

        Returns:
            dict: Gateway information (create or get response)
        """
        try:
            # Check if gateway already exists
            print(f"Checking for existing gateway: {gateway_name}")
            list_response = self.gateway_client.list_gateways(maxResults=100)

            for item in list_response.get('items', []):
                if item.get('name') == gateway_name:
                    gateway_id = item['gatewayId']
                    status = item.get('status', 'UNKNOWN')

                    print(f"Found existing gateway: {gateway_id} (status: {status})")

                    if status == 'READY':
                        # Gateway is ready, reuse it
                        print(f"✅ Reusing existing gateway in READY state")
                        gateway_details = self.gateway_client.get_gateway(gatewayIdentifier=gateway_id)
                        return gateway_details

                    elif status == 'CREATING':
                        # Gateway is being created, wait for it
                        print(f"Gateway is being created, waiting for it to become READY...")
                        if self.wait_for_gateway_ready(gateway_id):
                            gateway_details = self.gateway_client.get_gateway(gatewayIdentifier=gateway_id)
                            return gateway_details
                        else:
                            raise Exception(f"Gateway {gateway_id} did not become READY")

                    elif status == 'FAILED':
                        # Gateway failed, delete and recreate
                        print(f"⚠️  Gateway is in FAILED state, will delete and recreate")
                        self.delete_gateway(gateway_id)
                        # Continue to create new gateway below
                        break

                    else:
                        print(f"⚠️  Gateway is in {status} state, will create new one")
                        break

            # Create new gateway
            auth_config = {
                "customJWTAuthorizer": {
                    "allowedClients": [self.client_id],
                    "discoveryUrl": self.discovery_url
                }
            }

            print(f"Creating new gateway: {gateway_name}")
            print(f"  Using Cognito User Pool: {self.user_pool_id}")
            print(f"  Using Client ID: {self.client_id}")
            print(f"  Discovery URL: {self.discovery_url}")

            response = self.gateway_client.create_gateway(
                name=gateway_name,
                roleArn=role_arn,
                protocolType='MCP',
                authorizerType='CUSTOM_JWT',
                authorizerConfiguration=auth_config,
                description=description
            )

            gateway_id = response['gatewayId']
            gateway_url = response['gatewayUrl']

            print(f"\n✅ Gateway creation initiated!")
            print(f"Gateway ID: {gateway_id}")
            print(f"Gateway URL: {gateway_url}")

            return response

        except ClientError as e:
            print(f"❌ Error with gateway: {e}")
            raise

    def delete_gateway(self, gateway_id: str) -> None:
        """
        Delete gateway and all its targets

        Args:
            gateway_id: Gateway ID to delete
        """
        try:
            print(f"Deleting all targets for gateway: {gateway_id}")

            # List and delete all targets
            list_response = self.gateway_client.list_gateway_targets(
                gatewayIdentifier=gateway_id,
                maxResults=100
            )

            for item in list_response.get('items', []):
                target_id = item["targetId"]
                print(f"  Deleting target: {target_id}")
                self.gateway_client.delete_gateway_target(
                    gatewayIdentifier=gateway_id,
                    targetId=target_id
                )
                time.sleep(2)

            # Delete the gateway
            print(f"Deleting gateway: {gateway_id}")
            self.gateway_client.delete_gateway(gatewayIdentifier=gateway_id)
            print(f"✅ Gateway {gateway_id} deleted")

        except ClientError as e:
            print(f"❌ Error deleting gateway: {e}")
            raise

    def wait_for_gateway_ready(self, gateway_id: str, max_wait_seconds: int = 300) -> bool:
        """
        Wait for Gateway to become READY

        Args:
            gateway_id: Gateway ID to check
            max_wait_seconds: Maximum time to wait in seconds (default: 300 = 5 minutes)

        Returns:
            bool: True if gateway is ready, False if timeout

        Raises:
            ClientError: If there's an error checking gateway status
        """
        print(f"Waiting for gateway {gateway_id} to become READY...")

        start_time = time.time()
        check_interval = 10  # Check every 10 seconds

        while (time.time() - start_time) < max_wait_seconds:
            try:
                response = self.gateway_client.get_gateway(gatewayIdentifier=gateway_id)
                status = response.get('status', 'UNKNOWN')

                print(f"  Current status: {status} (elapsed: {int(time.time() - start_time)}s)")

                if status == 'READY':
                    print(f"✅ Gateway is now READY!")
                    return True
                elif status in ['FAILED', 'DELETING', 'DELETED']:
                    print(f"❌ Gateway is in {status} state")
                    return False

                # Still creating, wait and check again
                time.sleep(check_interval)

            except ClientError as e:
                print(f"Error checking gateway status: {e}")
                raise

        print(f"❌ Timeout waiting for gateway to become READY")
        return False

    def get_or_create_lambda_target(
        self,
        gateway_id: str,
        target_name: str,
        lambda_arn: str,
        tools: list
    ) -> dict:
        """
        Get existing or create new Lambda target in gateway (idempotent)

        Args:
            gateway_id: Gateway ID
            target_name: Name for the target
            lambda_arn: Lambda function ARN
            tools: List of tool definitions

        Returns:
            dict: Target information (create or get response)
        """
        try:
            # Check if target already exists
            print(f"\nChecking for existing Lambda target: {target_name}")
            list_response = self.gateway_client.list_gateway_targets(
                gatewayIdentifier=gateway_id,
                maxResults=100
            )

            for item in list_response.get('items', []):
                if item.get('name') == target_name:
                    target_id = item['targetId']
                    print(f"Found existing target: {target_id}")
                    print(f"✅ Reusing existing Lambda target")

                    # Get full target details
                    target_details = self.gateway_client.get_gateway_target(
                        gatewayIdentifier=gateway_id,
                        targetId=target_id
                    )
                    return target_details

            # Create new target
            lambda_target_config = {
                "mcp": {
                    "lambda": {
                        "lambdaArn": lambda_arn,
                        "toolSchema": {
                            "inlinePayload": tools
                        }
                    }
                }
            }

            credential_config = [
                {
                    "credentialProviderType": "GATEWAY_IAM_ROLE"
                }
            ]

            print(f"Creating new Lambda target: {target_name}")
            print(f"  Lambda ARN: {lambda_arn}")
            print(f"  Number of tools: {len(tools)}")

            response = self.gateway_client.create_gateway_target(
                gatewayIdentifier=gateway_id,
                name=target_name,
                description='Lambda Target',
                targetConfiguration=lambda_target_config,
                credentialProviderConfigurations=credential_config
            )

            print(f"✅ Lambda target created successfully!")
            return response

        except ClientError as e:
            print(f"❌ Error with Lambda target: {e}")
            raise

    def setup_complete(self, gateway_name: str) -> dict:
        """
        Complete setup: Lambda function, Gateway, and Target

        Args:
            gateway_name: Name for the gateway

        Returns:
            dict: Complete setup information
        """
        print("=" * 70)
        print("AgentCore Gateway Complete Setup")
        print("=" * 70)

        # 1. Create Lambda IAM Role
        print("\n[Step 1/5] Creating Lambda IAM Role...")
        lambda_role_arn = self.create_lambda_iam_role(LAMBDA_IAM_ROLE_NAME)

        # 2. Create Lambda Function
        print("\n[Step 2/5] Creating Lambda Function...")
        lambda_arn = self.create_lambda_function(LAMBDA_FUNCTION_NAME, lambda_role_arn)

        # 3. Create Gateway IAM Role
        print("\n[Step 3/5] Creating Gateway IAM Role...")
        gateway_role_name = f"agentcore-{gateway_name}-role"
        gateway_role = self.create_gateway_iam_role(gateway_role_name)

        # 4. Get or Create Gateway
        print("\n[Step 4/6] Getting or Creating Gateway...")
        gateway_response = self.get_or_create_gateway(
            gateway_name,
            gateway_role['Role']['Arn']
        )

        gateway_id = gateway_response['gatewayId']
        status = gateway_response.get('status', 'UNKNOWN')

        # 4.5. Wait for Gateway to become READY (if needed)
        if status != 'READY':
            print("\n[Step 5/6] Waiting for Gateway to become READY...")
            if not self.wait_for_gateway_ready(gateway_id):
                raise Exception(f"Gateway {gateway_id} did not become READY in time")
        else:
            print("\n[Step 5/6] Gateway is already READY, skipping wait")

        # 5. Get or Create Lambda Target with tool definitions
        print("\n[Step 6/6] Getting or Creating Lambda Target...")
        tools = [
            {
                "name": "get_current_time_tool",
                "description": "Returns the current time in multiple formats (ISO, Unix timestamp, formatted)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "timezone": {
                            "type": "string",
                            "description": "The timezone for the time (optional, defaults to UTC)"
                        }
                    },
                    "required": []
                }
            }
        ]

        target_name = f"{gateway_name}-lambda-target"
        self.get_or_create_lambda_target(
            gateway_id,
            target_name,
            lambda_arn,
            tools
        )

        # Summary
        gateway_url = gateway_response.get('gatewayUrl') or gateway_response.get('url', 'N/A')

        print("\n" + "=" * 70)
        print("Setup Complete!")
        print("=" * 70)
        print(f"Lambda Function ARN: {lambda_arn}")
        print(f"Gateway ID:          {gateway_id}")
        print(f"Gateway URL:         {gateway_url}")
        print(f"User Pool ID:        {self.user_pool_id}")
        print(f"Client ID:           {self.client_id}")
        print(f"Discovery URL:       {self.discovery_url}")

        print("\n💡 Update your .env file with:")
        print(f"MCP_SERVER_URL={gateway_url}")

        return {
            'lambda_arn': lambda_arn,
            'gateway_id': gateway_id,
            'gateway_url': gateway_url,
            'user_pool_id': self.user_pool_id,
            'client_id': self.client_id,
            'discovery_url': self.discovery_url
        }


def main():
    """Main entry point"""
    try:
        print("🚀 Starting AgentCore Gateway setup...\n")

        creator = GatewayCreator()
        result = creator.setup_complete(GATEWAY_NAME)

        print("\n✅ All setup completed successfully!")
        print("\n📋 Next steps:")
        print("1. Update .env with the MCP_SERVER_URL shown above")
        print("2. Run: uv run python cognito-and-ac-gateway/client.py")
        print("3. Test the gateway by calling get_current_time_tool")

        return result

    except ValueError as e:
        print(f"\n❌ Configuration error: {e}")
        print("\n📝 Please ensure:")
        print("1. You have run setup-cognito.py")
        print("2. COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID are in .env")
        return None
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    main()
