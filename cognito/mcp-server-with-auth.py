"""
MCP Resource Server with AWS Cognito Authentication

このサーバーは AWS Cognito で発行された JWT トークンを検証し、MCP リソースを提供します。
RFC 9728 Protected Resource Metadata に準拠した Authorization Server と Resource Server の分離構成を実装しています。
RFC 8707 Resource Indicators にも対応しています。

注意: これはデモンストレーション用の実装です。本番環境での使用には追加のセキュリティ対策が必要です。
"""

import datetime
import os
import logging
from typing import Any, Literal, Optional

import click
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp.server import FastMCP

from cognito_token_verifier import CognitoTokenVerifier
from dotenv import load_dotenv

# 環境変数を .env ファイルから読み込み
load_dotenv()

logger = logging.getLogger(__name__)


class ResourceServerSettings(BaseSettings):
    """
    MCP Resource Server の設定クラス
    
    環境変数から設定を読み込み、サーバーの動作を制御します。
    """

    model_config = SettingsConfigDict(env_prefix="MCP_RESOURCE_")

    # サーバー基本設定
    host: str = "localhost"
    port: int = 8001
    server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8001/mcp")

    # AWS Cognito 設定
    cognito_user_pool_id: str = os.getenv("COGNITO_USER_POOL_ID")
    cognito_region: str = os.getenv("COGNITO_REGION", "us-west-2")
    cognito_app_client_id: str = os.getenv("COGNITO_APP_CLIENT_ID")
    cognito_domain: str = os.getenv("COGNITO_DOMAIN")
    
    # MCP 認証設定
    mcp_scope: str = "openid"  # Cognito で使用するスコープ

    # RFC 8707 リソース検証
    expected_resource: Optional[str] = None  # RFC 8707 Resource Indicator


def create_resource_server(settings: ResourceServerSettings) -> FastMCP:
    """
    Cognito 認証対応の MCP Resource Server を作成
    
    このサーバーは以下の機能を提供します：
    1. RFC 9728 準拠の Protected Resource Metadata
    2. Cognito JWT トークンの検証
    3. RFC 8707 Resource Indicators 対応
    4. 認証が必要な MCP ツールとリソースの提供
    
    Args:
        settings: サーバー設定
        
    Returns:
        FastMCP: 設定済みの MCP サーバーインスタンス
    """
    # Cognito JWT トークン検証器を作成（RFC 8707対応）
    token_verifier = CognitoTokenVerifier(
        user_pool_id=settings.cognito_user_pool_id,
        region=settings.cognito_region,
        app_client_id=settings.cognito_app_client_id,
        expected_resource=settings.expected_resource  # RFC 8707対応
    )
    
    # Cognito Issuer URL を構築
    cognito_issuer_url = f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"

    # FastMCP サーバーを Resource Server として作成
    app = FastMCP(
        name="MCP Server sample",
        instructions="get time",
        host=settings.host,
        port=settings.port,
        debug=True,
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(cognito_issuer_url),
            required_scopes=[settings.mcp_scope],
            resource_server_url=settings.server_url,
        ),
    )

    @app.tool()
    async def get_time() -> dict[str, Any]:
        """
        現在のサーバー時刻を取得
        
        このツールは OAuth 認証によって保護されたシステム情報の例です。
        ユーザーは認証済みである必要があります。
        RFC 8707 Resource Binding が有効な場合、適切なリソース指定が必要です。
        
        Returns:
            dict: 現在時刻の情報（ISO形式、タイムスタンプ、フォーマット済み文字列）
        """
        now = datetime.datetime.now()

        return {
            "current_time": now.isoformat(),
            "timezone": "UTC",
            "timestamp": now.timestamp(),
            "formatted": now.strftime("%Y-%m-%d %H:%M:%S"),
        }

    return app

@click.command()
@click.option("--port", default=8001, help="Port to listen on")
@click.option(
    "--transport",
    default="streamable-http",
    type=click.Choice(["sse", "streamable-http"]),
    help="Transport protocol to use",
)
def main(port: int, transport: Literal["sse", "streamable-http"]) -> int:
    """
    Cognito 認証対応の MCP Resource Server を実行

    このサーバーは Cognito JWT トークンを直接検証します。
    別途 Authorization Server を起動する必要はありません。
    RFC 8707 Resource Indicators にも対応しています。

    Args:
        port: サーバーのリスニングポート
        transport: 使用するトランスポートプロトコル

    Returns:
        int: 終了コード（0: 正常終了, 1: エラー終了）
    """
    logging.basicConfig(level=logging.INFO)

    # 必要な環境変数の確認
    required_env_vars = [
        "COGNITO_USER_POOL_ID",
        "COGNITO_APP_CLIENT_ID", 
        "COGNITO_DOMAIN"
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"必要な環境変数が設定されていません: {missing_vars}")
        return 1

    try:
        # サーバー設定を作成
        host = "localhost"
        server_url = f"http://{host}:{port}/mcp"
        settings = ResourceServerSettings(
            host=host,
            port=port,
            server_url=AnyHttpUrl(server_url),
            expected_resource=server_url,  # RFC 8707対応
        )
    except ValueError as e:
        logger.error(f"設定エラー: {e}")
        return 1

    try:
        mcp_server = create_resource_server(settings)

        logger.info(f"🚀 MCP Resource Server を開始しました: {settings.server_url}")
        logger.info(f"🔑 使用中の Cognito User Pool: {settings.cognito_user_pool_id}")
        
        # RFC 8707設定の表示
        if settings.expected_resource:
            logger.info(f"🎯 RFC 8707 Resource Binding有効: {settings.expected_resource}")
        else:
            logger.info("📝 RFC 8707 Resource Binding無効（expected_resource未設定）")

        mcp_server.run(transport=transport)
        logger.info("サーバーを停止しました")
        return 0
    except Exception:
        logger.exception("サーバーエラーが発生しました")
        return 1


if __name__ == "__main__":
    main()  # type: ignore[call-arg]
