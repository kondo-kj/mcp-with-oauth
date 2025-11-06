import boto3
import urllib.parse

# ===== 設定ここから（必要に応じて書き換え）=====

REGION = "us-west-2"

# ユーザープール・クライアントの名前
POOL_NAME = "mcp-with-oauth-userpool"
CLIENT_NAME = "agentcore-client"

# Cognito ドメインのプレフィックス（グローバルに一意である必要あり）
COGNITO_DOMAIN_PREFIX = "agentcore-demo-1234"

# クライアントのコールバックURL（client.py の仕様に合わせる）
CALLBACK_URL = "http://localhost:3030/callback"
LOGOUT_URL = "http://localhost:3030/logout"

# テストユーザー
TEST_USER_NAME = "testuser"
TEST_USER_EMAIL = "testuser@example.com"
TEST_USER_TEMP_PASSWORD = "Testuser1!"
TEST_USER_PERM_PASSWORD = "Testuser1!"

# ===== 設定ここまで =====

def main() -> None:
    cognito = boto3.client("cognito-idp", region_name=REGION)

    # 1. ユーザープール作成（ユーザー名ログイン）
    print("== Create User Pool ==")
    pool = cognito.create_user_pool(
        PoolName=POOL_NAME,
        AutoVerifiedAttributes=["email"],  # メールは検証対象にするだけ
        # UsernameAttributes は指定しない → "username" ログイン
    )
    user_pool_id = pool["UserPool"]["Id"]
    print("UserPoolId:", user_pool_id)

    # 2. アプリクライアント作成
    #    Authorization Code Flow（Managed Login / Hosted UI どちらでも使える）
    print("== Create User Pool Client ==")
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
        ],  # カスタムスコープなし
        SupportedIdentityProviders=["COGNITO"],
        CallbackURLs=[CALLBACK_URL],
        LogoutURLs=[LOGOUT_URL],
        PreventUserExistenceErrors="ENABLED",
    )
    client_id = client["UserPoolClient"]["ClientId"]
    client_secret = client["UserPoolClient"]["ClientSecret"]
    print("ClientId:", client_id)
    print("ClientSecret:", client_secret)

    # 3. ユーザープールドメイン作成 + Managed Login 有効化
    print("== Create User Pool Domain (Managed Login) ==")
    domain_resp = cognito.create_user_pool_domain(
        Domain=COGNITO_DOMAIN_PREFIX,
        UserPoolId=user_pool_id,
        ManagedLoginVersion=2,  # 2 = Managed Login
    )
    print("ManagedLoginVersion:", domain_resp.get("ManagedLoginVersion"))

    # 4. Managed Login のスタイルをデフォルトで作成
    print("== Create Managed Login Branding (use default style) ==")
    branding_resp = cognito.create_managed_login_branding(
        UserPoolId=user_pool_id,
        ClientId=client_id,
        UseCognitoProvidedValues=True,  # デフォルトスタイル
    )
    print(
        "ManagedLoginBrandingId:",
        branding_resp["ManagedLoginBranding"]["ManagedLoginBrandingId"],
    )

    # 5. テストユーザー作成（ユーザー名でログインさせる）
    print("== Create Test User ==")
    cognito.admin_create_user(
        UserPoolId=user_pool_id,
        Username=TEST_USER_NAME,  # ← ログインに使うID
        TemporaryPassword=TEST_USER_TEMP_PASSWORD,
        UserAttributes=[
            {"Name": "email", "Value": TEST_USER_EMAIL},
            {"Name": "email_verified", "Value": "true"},
        ],
        MessageAction="SUPPRESS",  # 招待メールなどは送らない
    )

    # 最初から永続パスワードにしてしまう
    cognito.admin_set_user_password(
        UserPoolId=user_pool_id,
        Username=TEST_USER_NAME,
        Password=TEST_USER_PERM_PASSWORD,
        Permanent=True,
    )
    print("Test user created:", TEST_USER_NAME)

    # 6. ログイン URL（Managed Login）
    print("== Build Login URL ==")
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

    print("======================================")
    print("UserPoolId:", user_pool_id)
    print("ClientId:", client_id)
    print("ClientSecret:", client_secret)
    print("TestUser (username):", TEST_USER_NAME)
    print("TestUser email:", TEST_USER_EMAIL)
    print("Login URL (Managed Login):")
    print(login_url)
    print("======================================")


if __name__ == "__main__":
    main()