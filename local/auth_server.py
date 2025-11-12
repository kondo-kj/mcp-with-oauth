"""
Authorization Server for MCP Split Demo.

This server handles OAuth flows, client registration, and token issuance.
Can be replaced with enterprise authorization servers like Auth0, Entra ID, etc.

NOTE: this is a simplified example for demonstration purposes.
This is not a production-ready implementation.

"""

import asyncio
import logging
import os
import time

from dotenv import load_dotenv
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from uvicorn import Config, Server

from mcp.server.auth.routes import cors_middleware, create_auth_routes
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions

from simple_auth_provider import SimpleAuthSettings, SimpleOAuthProvider

# Load environment variables from current directory
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(env_path)

print(f"Loading .env from: {os.path.abspath(env_path)}")

logger = logging.getLogger(__name__)


class AuthServerSettings(BaseSettings):
    """Settings for the Authorization Server."""

    model_config = SettingsConfigDict(env_prefix="MCP_AUTH_")

    # Server settings
    host: str = "localhost"
    port: int = 9000
    server_url: AnyHttpUrl | None = None
    auth_callback_path: str | None = None

    def model_post_init(self, __context):
        """Post-initialization to set computed fields."""
        # Set server_url if not provided
        if self.server_url is None:
            self.server_url = AnyHttpUrl(f"http://{self.host}:{self.port}")

        # Set auth_callback_path if not provided
        if self.auth_callback_path is None:
            self.auth_callback_path = f"{self.server_url}/login/callback"


class SimpleAuthProvider(SimpleOAuthProvider):
    """
    Authorization Server provider with simple demo authentication.

    This provider:
    1. Issues MCP tokens after simple credential authentication
    2. Stores token state for introspection by Resource Servers
    """

    def __init__(self, auth_settings: SimpleAuthSettings, auth_callback_path: str, server_url: str):
        super().__init__(auth_settings, auth_callback_path, server_url)


def create_authorization_server(server_settings: AuthServerSettings, auth_settings: SimpleAuthSettings) -> Starlette:
    """Create the Authorization Server application."""
    oauth_provider = SimpleAuthProvider(
        auth_settings, server_settings.auth_callback_path, str(server_settings.server_url)
    )

    mcp_auth_settings = AuthSettings(
        issuer_url=server_settings.server_url,
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=[auth_settings.mcp_scope],
            default_scopes=[auth_settings.mcp_scope],
        ),
        required_scopes=[auth_settings.mcp_scope],
        resource_server_url=None,
    )

    # Create OAuth routes
    routes = create_auth_routes(
        provider=oauth_provider,
        issuer_url=mcp_auth_settings.issuer_url,
        service_documentation_url=mcp_auth_settings.service_documentation_url,
        client_registration_options=mcp_auth_settings.client_registration_options,
        revocation_options=mcp_auth_settings.revocation_options,
    )

    # Add login page route (GET)
    async def login_page_handler(request: Request) -> Response:
        """Show login form."""
        state = request.query_params.get("state")
        if not state:
            raise HTTPException(400, "Missing state parameter")
        return await oauth_provider.get_login_page(state)

    routes.append(Route("/login", endpoint=login_page_handler, methods=["GET"]))

    # Add login callback route (POST)
    async def login_callback_handler(request: Request) -> Response:
        """Handle simple authentication callback."""
        return await oauth_provider.handle_login_callback(request)

    routes.append(Route("/login/callback", endpoint=login_callback_handler, methods=["POST"]))

    # Add token introspection endpoint (RFC 7662) for Resource Servers
    async def introspect_handler(request: Request) -> Response:
        """
        Token introspection endpoint for Resource Servers.

        Resource Servers call this endpoint to validate tokens without
        needing direct access to token storage.
        """
        form = await request.form()
        token = form.get("token")
        if not token or not isinstance(token, str):
            return JSONResponse({"active": False}, status_code=400)

        # Look up token in provider
        access_token = await oauth_provider.load_access_token(token)
        if not access_token:
            return JSONResponse({"active": False})

        return JSONResponse(
            {
                "active": True,
                "client_id": access_token.client_id,
                "scope": " ".join(access_token.scopes),
                "exp": access_token.expires_at,
                "iat": int(time.time()),
                "token_type": "Bearer",
                "aud": access_token.resource,  # RFC 8707 audience claim
            }
        )

    routes.append(
        Route(
            "/introspect",
            endpoint=cors_middleware(introspect_handler, ["POST", "OPTIONS"]),
            methods=["POST", "OPTIONS"],
        )
    )

    return Starlette(routes=routes)


async def run_server(server_settings: AuthServerSettings, auth_settings: SimpleAuthSettings):
    """Run the Authorization Server."""
    auth_server = create_authorization_server(server_settings, auth_settings)

    config = Config(
        auth_server,
        host=server_settings.host,
        port=server_settings.port,
        log_level="info",
    )
    server = Server(config)

    logger.info(f"🚀 MCP Authorization Server running on {server_settings.server_url}")

    await server.serve()


def main() -> int:
    """
    Run the MCP Authorization Server.

    This server handles OAuth flows and can be used by multiple Resource Servers.

    Uses simple hardcoded credentials for demo purposes.

    Configuration is loaded from environment variables with prefix MCP_AUTH_:
    - MCP_AUTH_PORT: Server port (default: 9000)
    """
    logging.basicConfig(level=logging.INFO)

    try:
        # Load simple auth settings
        auth_settings = SimpleAuthSettings()

        # Load server settings from environment variables
        server_settings = AuthServerSettings()

        logger.info("=" * 70)
        logger.info("MCP Authorization Server")
        logger.info("=" * 70)
        logger.info(f"\n[Configuration]")
        logger.info(f"  Server URL:         {server_settings.server_url}")
        logger.info(f"  Callback Path:      {server_settings.auth_callback_path}")
        logger.info(f"  Demo User:          {auth_settings.demo_username}")

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your .env file configuration")
        return 1

    asyncio.run(run_server(server_settings, auth_settings))
    return 0


if __name__ == "__main__":
    exit(main())