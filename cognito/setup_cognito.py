#!/usr/bin/env python3
"""
Setup AWS Cognito User Pool for MCP Server with Auth

This script creates:
1. Cognito User Pool with Managed Login
2. App Client for OAuth 2.0 authorization code flow
3. Cognito Domain for Hosted UI
4. Test user with preset password

Required AWS permissions:
- cognito-idp:CreateUserPool
- cognito-idp:CreateUserPoolClient
- cognito-idp:CreateUserPoolDomain
- cognito-idp:CreateManagedLoginBranding
- cognito-idp:AdminCreateUser
- cognito-idp:AdminSetUserPassword
"""

import boto3
import urllib.parse

# ===== Configuration (customize as needed) =====

REGION = "us-west-2"

# User Pool and Client names
POOL_NAME = "mcp-with-oauth-userpool"
CLIENT_NAME = "mcp-client"

# Cognito domain prefix (must be globally unique)
COGNITO_DOMAIN_PREFIX = "mcp-oauth-demo-1234"

# Client callback URLs (matches client.py configuration)
CALLBACK_URL = "http://localhost:3030/callback"
LOGOUT_URL = "http://localhost:3030/logout"

# Test user credentials
TEST_USER_NAME = "testuser"
TEST_USER_EMAIL = "testuser@example.com"
TEST_USER_TEMP_PASSWORD = "Testuser1!"
TEST_USER_PERM_PASSWORD = "Testuser1!"

# ===== End Configuration =====

def main() -> None:
    cognito = boto3.client("cognito-idp", region_name=REGION)

    # 1. Create User Pool (username-based login)
    print("=" * 70)
    print("Step 1: Creating User Pool")
    print("=" * 70)
    pool = cognito.create_user_pool(
        PoolName=POOL_NAME,
        AutoVerifiedAttributes=["email"],  # Email verification enabled
        # UsernameAttributes not specified → username login
    )
    user_pool_id = pool["UserPool"]["Id"]
    print(f"✅ User Pool created: {user_pool_id}")

    # 2. Create App Client
    #    Authorization Code Flow (for Managed Login / Hosted UI)
    print("\n" + "=" * 70)
    print("Step 2: Creating App Client")
    print("=" * 70)
    client = cognito.create_user_pool_client(
        UserPoolId=user_pool_id,
        ClientName=CLIENT_NAME,
        GenerateSecret=True,
        AllowedOAuthFlows=["code"],
        AllowedOAuthFlowsUserPoolClient=True,
        AllowedOAuthScopes=[
            "openid",
            "email",
            "profile",
        ],  # No custom scopes
        SupportedIdentityProviders=["COGNITO"],
        CallbackURLs=[CALLBACK_URL],
        LogoutURLs=[LOGOUT_URL],
        PreventUserExistenceErrors="ENABLED",
    )
    client_id = client["UserPoolClient"]["ClientId"]
    client_secret = client["UserPoolClient"]["ClientSecret"]
    print(f"✅ App Client created")
    print(f"   Client ID: {client_id}")
    print(f"   Client Secret: {client_secret}")

    # 3. Create User Pool Domain + Enable Managed Login
    print("\n" + "=" * 70)
    print("Step 3: Creating Cognito Domain (Managed Login)")
    print("=" * 70)
    domain_resp = cognito.create_user_pool_domain(
        Domain=COGNITO_DOMAIN_PREFIX,
        UserPoolId=user_pool_id,
        ManagedLoginVersion=2,  # 2 = Managed Login
    )
    print(f"✅ Cognito Domain created: {COGNITO_DOMAIN_PREFIX}")
    print(f"   Managed Login Version: {domain_resp.get('ManagedLoginVersion')}")

    # 4. Create Managed Login Branding (default style)
    print("\n" + "=" * 70)
    print("Step 4: Creating Managed Login Branding")
    print("=" * 70)
    branding_resp = cognito.create_managed_login_branding(
        UserPoolId=user_pool_id,
        ClientId=client_id,
        UseCognitoProvidedValues=True,  # Use default style
    )
    print(
        f"✅ Managed Login Branding created: {branding_resp['ManagedLoginBranding']['ManagedLoginBrandingId']}"
    )

    # 5. Create Test User (username-based login)
    print("\n" + "=" * 70)
    print("Step 5: Creating Test User")
    print("=" * 70)
    cognito.admin_create_user(
        UserPoolId=user_pool_id,
        Username=TEST_USER_NAME,  # Login ID
        TemporaryPassword=TEST_USER_TEMP_PASSWORD,
        UserAttributes=[
            {"Name": "email", "Value": TEST_USER_EMAIL},
            {"Name": "email_verified", "Value": "true"},
        ],
        MessageAction="SUPPRESS",  # Don't send invitation email
    )

    # Set permanent password
    cognito.admin_set_user_password(
        UserPoolId=user_pool_id,
        Username=TEST_USER_NAME,
        Password=TEST_USER_PERM_PASSWORD,
        Permanent=True,
    )
    print(f"✅ Test user created: {TEST_USER_NAME}")
    print(f"   Email: {TEST_USER_EMAIL}")
    print(f"   Password: {TEST_USER_PERM_PASSWORD}")

    # 6. Build Login URL (Managed Login)
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    domain_url = f"https://{COGNITO_DOMAIN_PREFIX}.auth.{REGION}.amazoncognito.com"

    scope = " ".join(
        [
            "openid",
            "email",
            "profile",
        ]
    )

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": CALLBACK_URL,
        "scope": scope,
    }

    login_url = domain_url + "/login?" + urllib.parse.urlencode(
        params, quote_via=urllib.parse.quote
    )

    print("\n✅ Cognito setup completed successfully!")
    print("\n" + "=" * 70)
    print("Configuration Values (add these to your .env file)")
    print("=" * 70)
    print(f"COGNITO_USER_POOL_ID={user_pool_id}")
    print(f"COGNITO_APP_CLIENT_ID={client_id}")
    print(f"COGNITO_APP_CLIENT_SECRET={client_secret}")
    print(f"COGNITO_DOMAIN={COGNITO_DOMAIN_PREFIX}.auth.{REGION}.amazoncognito.com")
    print("\nNote: Region is automatically extracted from User Pool ID")
    print("\n" + "=" * 70)
    print("Test User Credentials")
    print("=" * 70)
    print(f"Username: {TEST_USER_NAME}")
    print(f"Password: {TEST_USER_PERM_PASSWORD}")
    print("\n" + "=" * 70)
    print("Login URL (Managed Login)")
    print("=" * 70)
    print(login_url)
    print("=" * 70)


if __name__ == "__main__":
    main()
