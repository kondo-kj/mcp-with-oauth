"""
MCP Resource Server with Token Introspection.

This server validates tokens via Authorization Server introspection and serves MCP resources.
Demonstrates RFC 9728 Protected Resource Metadata for AS/RS separation.

NOTE: this is a simplified example for demonstration purposes.
This is not a production-ready implementation.
"""

import datetime
import logging
import os
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp.server import FastMCP

from token_verifier import IntrospectionTokenVerifier

# Load environment variables from current directory
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(env_path)

print(f"Loading .env from: {os.path.abspath(env_path)}")

logger = logging.getLogger(__name__)


class ResourceServerSettings(BaseSettings):
    """Settings for the MCP Resource Server."""

    model_config = SettingsConfigDict(env_prefix="MCP_RESOURCE_")

    # Server settings
    host: str = "localhost"
    port: int = 8001
    server_url: AnyHttpUrl | None = None
    transport: Literal["sse", "streamable-http"] = "streamable-http"

    # Authorization Server settings
    auth_server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:9000")
    auth_server_introspection_endpoint: str | None = None
    # No user endpoint needed - we get user data from token introspection

    # MCP settings
    mcp_scope: str = "user"

    # RFC 8707 resource validation
    oauth_strict: bool = False

    def model_post_init(self, __context):
        """Post-initialization to set computed fields."""
        # Set server_url if not provided
        if self.server_url is None:
            self.server_url = AnyHttpUrl(f"http://{self.host}:{self.port}/mcp")

        # Set introspection endpoint if not provided
        if self.auth_server_introspection_endpoint is None:
            self.auth_server_introspection_endpoint = f"{self.auth_server_url}/introspect"


def create_resource_server(settings: ResourceServerSettings) -> FastMCP:
    """
    Create MCP Resource Server with token introspection.

    This server:
    1. Provides protected resource metadata (RFC 9728)
    2. Validates tokens via Authorization Server introspection
    3. Serves MCP tools and resources
    """
    # Create token verifier for introspection with RFC 8707 resource validation
    token_verifier = IntrospectionTokenVerifier(
        introspection_endpoint=settings.auth_server_introspection_endpoint,
        server_url=str(settings.server_url),
        validate_resource=settings.oauth_strict,  # Only validate when --oauth-strict is set
    )

    # Create FastMCP server as a Resource Server
    app = FastMCP(
        name="MCP Resource Server",
        instructions="Resource Server that validates tokens via Authorization Server introspection",
        host=settings.host,
        port=settings.port,
        debug=True,
        # Auth configuration for RS mode
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=settings.auth_server_url,
            required_scopes=[settings.mcp_scope],
            resource_server_url=settings.server_url,
        ),
    )

    @app.tool()
    async def get_time() -> dict[str, Any]:
        """
        Get the current server time.

        This tool demonstrates that system information can be protected
        by OAuth authentication. User must be authenticated to access it.
        """

        now = datetime.datetime.now()

        return {
            "current_time": now.isoformat(),
            "timezone": "UTC",  # Simplified for demo
            "timestamp": now.timestamp(),
            "formatted": now.strftime("%Y-%m-%d %H:%M:%S"),
        }

    return app


def main() -> int:
    """
    Run the MCP Resource Server.

    This server:
    - Provides RFC 9728 Protected Resource Metadata
    - Validates tokens via Authorization Server introspection
    - Serves MCP tools requiring authentication

    Must be used with a running Authorization Server.

    Configuration is loaded from environment variables with prefix MCP_RESOURCE_:
    - MCP_RESOURCE_PORT: Server port (default: 8001)
    - MCP_RESOURCE_AUTH_SERVER_URL: Authorization Server URL (default: http://localhost:9000)
    - MCP_RESOURCE_TRANSPORT: Transport protocol (default: streamable-http)
    - MCP_RESOURCE_OAUTH_STRICT: Enable RFC 8707 validation (default: false)
    """
    logging.basicConfig(level=logging.INFO)

    try:
        # Load settings from environment variables
        settings = ResourceServerSettings()

        logger.info("=" * 70)
        logger.info("MCP Resource Server with OAuth Authentication")
        logger.info("=" * 70)
        logger.info(f"\n[Configuration]")
        logger.info(f"  Server URL:         {settings.server_url}")
        logger.info(f"  Transport:          {settings.transport}")
        logger.info(f"  Auth Server:        {settings.auth_server_url}")
        logger.info(f"  OAuth Strict:       {settings.oauth_strict}")
        logger.info(f"  Required Scope:     {settings.mcp_scope}")

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your .env file configuration")
        return 1

    try:
        mcp_server = create_resource_server(settings)

        logger.info(f"\n🚀 Starting MCP Resource Server...")
        logger.info(f"🔑 Using Authorization Server: {settings.auth_server_url}")

        # Run the server - this should block and keep running
        mcp_server.run(transport=settings.transport)
        logger.info("Server stopped")
        return 0
    except Exception:
        logger.exception("Server error")
        return 1


if __name__ == "__main__":
    exit(main())