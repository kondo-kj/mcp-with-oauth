#!/usr/bin/env python3
"""
Add MCP Resource Server to Cognito User Pool

This script adds a local MCP server as a resource server to an existing Cognito User Pool.
Configuration is loaded from the .env file.

Required environment variables in .env:
- COGNITO_USER_POOL_ID: Cognito User Pool ID
- MCP_SERVER_URL: MCP Server URL (used as resource server identifier)
- AWS_DEFAULT_REGION: AWS region (default: us-west-2)

The MCP server URL should match the URL where mcp-server-with-auth.py is running
(typically http://localhost:8001/mcp).
"""

import os
from pathlib import Path
import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Load environment variables from current directory
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(env_path)

print(f"Loading .env from: {os.path.abspath(env_path)}")

# Load configuration from environment variables
REGION = os.getenv('AWS_DEFAULT_REGION', 'us-west-2')
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
MCP_SERVER_URL = os.getenv('MCP_SERVER_URL', 'http://localhost:8001/mcp')
RESOURCE_SERVER_NAME = "MCP Server"


def validate_config():
    """Validate that required environment variables are set"""
    errors = []

    if not USER_POOL_ID:
        errors.append("COGNITO_USER_POOL_ID is not set in .env file")

    if not MCP_SERVER_URL:
        errors.append("MCP_SERVER_URL is not set in .env file")

    if errors:
        print("❌ Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        print("\n📝 Please ensure your .env file contains:")
        print("  - COGNITO_USER_POOL_ID=<user_pool_id>")
        print("  - MCP_SERVER_URL=<mcp_server_url>")
        print("  - AWS_DEFAULT_REGION=<region> (optional, defaults to us-west-2)")
        return False

    return True


def get_or_create_resource_server(cognito, user_pool_id, identifier, name):
    """
    Get existing or create new resource server (idempotent)

    Args:
        cognito: Boto3 Cognito client
        user_pool_id: Cognito User Pool ID
        identifier: Resource server identifier (usually the MCP Server URL)
        name: Resource server name

    Returns:
        dict: Resource server information
    """
    try:
        # Check if resource server already exists
        print(f"Checking for existing resource server: {identifier}")

        try:
            existing = cognito.describe_resource_server(
                UserPoolId=user_pool_id,
                Identifier=identifier
            )

            rs = existing['ResourceServer']
            print("\n✅ Resource server already exists:")
            print(f"  UserPoolId:          {user_pool_id}")
            print(f"  Identifier (issuer): {rs['Identifier']}")
            print(f"  Name:                {rs['Name']}")
            print(f"  Scopes:              {rs.get('Scopes', [])}")
            return rs

        except cognito.exceptions.ResourceNotFoundException:
            # Resource server doesn't exist, create it
            print(f"Resource server not found, creating new one...")

            resp = cognito.create_resource_server(
                UserPoolId=user_pool_id,
                Identifier=identifier,
                Name=name,
                # Scopes are not specified → no custom scopes
            )

            rs = resp["ResourceServer"]
            print("\n✅ Resource server created:")
            print(f"  UserPoolId:          {user_pool_id}")
            print(f"  Identifier (issuer): {rs['Identifier']}")
            print(f"  Name:                {rs['Name']}")
            print(f"  Scopes:              {rs.get('Scopes', [])}")
            return rs

    except ClientError as e:
        print(f"❌ Error with resource server: {e}")
        raise


def main() -> None:
    """Main entry point"""
    print("=" * 70)
    print("Add MCP Resource Server to Cognito User Pool")
    print("=" * 70)

    # Validate configuration
    print("\n[Step 1/2] Validating configuration...")
    if not validate_config():
        return

    print(f"\nConfiguration:")
    print(f"  Region:          {REGION}")
    print(f"  User Pool ID:    {USER_POOL_ID}")
    print(f"  MCP Server URL:  {MCP_SERVER_URL}")

    # Create or get resource server
    print("\n[Step 2/2] Creating or getting resource server...")
    cognito = boto3.client("cognito-idp", region_name=REGION)

    try:
        get_or_create_resource_server(
            cognito,
            USER_POOL_ID,
            MCP_SERVER_URL,
            RESOURCE_SERVER_NAME
        )

        print("\n✅ Operation completed successfully!")
        print("\n📝 Next step:")
        print("  Run the client: uv run python client.py")

    except Exception as e:
        print(f"\n❌ Operation failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
