#!/usr/bin/env python3
"""
MCP Client with OAuth Authentication

This client connects to MCP servers using OAuth authentication.
Supports AWS Cognito and generic OAuth 2.0 Authorization Servers.

Required environment variables in .env:
- MCP_SERVER_URL: AgentCore Gateway URL
- MCP_USE_DCR: Whether to use Dynamic Client Registration (true/false, default: false)
- COGNITO_APP_CLIENT_ID: Cognito App Client ID (required when DCR is false)
- COGNITO_APP_CLIENT_SECRET: Cognito App Client Secret (required when DCR is false)
"""

import asyncio
import os
import threading
import time
import webbrowser
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from dotenv import load_dotenv

# Load environment variables from current directory
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(env_path)

print(f"Loading .env from: {os.path.abspath(env_path)}")

class InMemoryTokenStorage(TokenStorage):
    """
    In-memory token storage implementation

    Stores OAuth tokens and client information in memory.
    For production use, persistent storage is recommended.
    """

    def __init__(self):
        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        """Get stored tokens"""
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        """Store tokens"""
        self._tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        """Get stored client information"""
        return self._client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        """Store client information"""
        self._client_info = client_info


class CallbackHandler(BaseHTTPRequestHandler):
    """
    HTTP handler for OAuth callback processing

    Receives redirects from Authorization Server and extracts
    authorization code or error information.
    """

    def __init__(self, request, client_address, server, callback_data):
        """
        Initialize with callback data storage

        Args:
            callback_data: Dictionary to store authentication results
        """
        self.callback_data = callback_data
        super().__init__(request, client_address, server)

    def do_GET(self):
        """Handle GET requests from OAuth redirect"""
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)

        if "code" in query_params:
            # Handle successful authentication
            self.callback_data["authorization_code"] = query_params["code"][0]
            self.callback_data["state"] = query_params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("""
            <html>
            <head>
                <meta charset="utf-8">
            </head>
            <body>
                <h1>Authentication Complete!</h1>
                <p>You can close this window and return to the terminal.</p>
                <script>setTimeout(() => window.close(), 2000);</script>
            </body>
            </html>
            """.encode('utf-8'))
        elif "error" in query_params:
            # Handle authentication error
            self.callback_data["error"] = query_params["error"][0]
            self.send_response(400)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"""
            <html>
            <head>
                <meta charset="utf-8">
            </head>
            <body>
                <h1>Authentication Failed</h1>
                <p>Error: {query_params["error"][0]}</p>
                <p>You can close this window and return to the terminal.</p>
            </body>
            </html>
            """.encode('utf-8')
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default log output"""
        pass


class CallbackServer:
    """
    Simple HTTP server for OAuth callback handling

    Runs in the background to receive redirects from Authorization Server
    and process authentication results.
    """

    def __init__(self, port=3000):
        """
        Initialize callback server

        Args:
            port: Port number to listen on
        """
        self.port = port
        self.server = None
        self.thread = None
        self.callback_data = {"authorization_code": None, "state": None, "error": None}

    def _create_handler_with_data(self):
        """Create handler class with access to callback data"""
        callback_data = self.callback_data

        class DataCallbackHandler(CallbackHandler):
            def __init__(self, request, client_address, server):
                super().__init__(request, client_address, server, callback_data)

        return DataCallbackHandler

    def start(self):
        """Start callback server in background thread"""
        handler_class = self._create_handler_with_data()
        self.server = HTTPServer(("localhost", self.port), handler_class)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"🖥️  Callback server started: http://localhost:{self.port}")

    def stop(self):
        """Stop callback server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=1)

    def wait_for_callback(self, timeout=300):
        """
        Wait for OAuth callback with timeout

        Args:
            timeout: Timeout in seconds

        Returns:
            str: Authorization code

        Raises:
            Exception: On error or timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.callback_data["authorization_code"]:
                return self.callback_data["authorization_code"]
            elif self.callback_data["error"]:
                raise Exception(f"OAuth error: {self.callback_data['error']}")
            time.sleep(0.1)
        raise Exception("OAuth callback wait timed out")

    def get_state(self):
        """Get received state parameter"""
        return self.callback_data["state"]

class SimpleAuthClient:
    """
    Simple MCP client with OAuth authentication

    Supports both DCR (Dynamic Client Registration) and pre-registered clients
    (such as Cognito).
    """

    def __init__(self, server_url: str, use_dcr: bool = True):
        """
        Initialize MCP client

        Args:
            server_url: MCP server URL to connect to
            use_dcr: Whether to use Dynamic Client Registration
        """
        self.server_url = server_url
        self.use_dcr = use_dcr

        # Cognito settings (used when DCR is disabled)
        self.client_id = os.getenv("COGNITO_APP_CLIENT_ID")
        self.client_secret = os.getenv("COGNITO_APP_CLIENT_SECRET")

        # Check environment variables when DCR is disabled
        if not self.use_dcr and not all([self.client_id, self.client_secret]):
            raise ValueError("Cognito environment variables required when DCR is disabled")

    async def connect(self):
        """
        Connect to MCP server

        Executes OAuth authentication flow then starts MCP session.
        """
        print(f"🔗 Attempting to connect to {self.server_url}...")

        try:
            callback_server = CallbackServer(port=3030)
            callback_server.start()

            async def callback_handler() -> tuple[str, str | None]:
                """Wait for OAuth callback and return authorization code and state"""
                print("⏳ Waiting for authentication callback...")
                try:
                    auth_code = callback_server.wait_for_callback(timeout=300)
                    return auth_code, callback_server.get_state()
                finally:
                    callback_server.stop()

            async def _default_redirect_handler(authorization_url: str) -> None:
                """Default redirect handler (open URL in browser)"""
                print(f"Opening browser for authentication: {authorization_url}")
                webbrowser.open(authorization_url)

            # Select authentication method (DCR or pre-registered client)
            if self.use_dcr:
                # Use Dynamic Client Registration
                client_metadata_dict = {
                    "client_name": "Simple Auth Client",
                    "redirect_uris": ["http://localhost:3030/callback"],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "client_secret_post",
                }

                oauth_auth = OAuthClientProvider(
                    server_url=self.server_url,
                    client_metadata=OAuthClientMetadata.model_validate(client_metadata_dict),
                    storage=InMemoryTokenStorage(),
                    redirect_handler=_default_redirect_handler,
                    callback_handler=callback_handler,
                )
            else:
                # Use pre-registered client (Cognito)
                pre_registered_client = OAuthClientInformationFull(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    client_name="MCP Cognito Client",
                    redirect_uris=["http://localhost:3030/callback"],
                    grant_types=["authorization_code", "refresh_token"],
                    response_types=["code"],
                    token_endpoint_auth_method="client_secret_post",
                )

                client_metadata_dict = {
                    "client_name": "MCP Cognito Client",
                    "redirect_uris": ["http://localhost:3030/callback"],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "client_secret_post",
                    "scope": "openid profile email"
                }

                storage = InMemoryTokenStorage()
                await storage.set_client_info(pre_registered_client)

                oauth_auth = OAuthClientProvider(
                    server_url=self.server_url,
                    client_metadata=OAuthClientMetadata.model_validate(client_metadata_dict),
                    storage=storage,
                    redirect_handler=_default_redirect_handler,
                    callback_handler=callback_handler
                )

            # Connect with StreamableHTTP transport
            print("📡 Starting StreamableHTTP transport connection...")
            async with streamablehttp_client(
                url=self.server_url,
                auth=oauth_auth,
                timeout=timedelta(seconds=60),
            ) as (read_stream, write_stream, get_session_id):
                await self._run_session(read_stream, write_stream, get_session_id)

        except Exception as e:
            print(f"❌ Connection failed: {e}")
            import traceback
            traceback.print_exc()

    async def _run_session(self, read_stream, write_stream, get_session_id):
        """
        Run MCP session with specified streams

        Args:
            read_stream: Stream for reading
            write_stream: Stream for writing
            get_session_id: Function to get session ID (optional)
        """
        print("🤝 Initializing MCP session...")
        async with ClientSession(read_stream, write_stream) as session:
            self.session = session
            print("⚡ Starting session initialization...")
            await session.initialize()
            print("✨ Session initialization complete!")

            print(f"\n✅ Connected to MCP server: {self.server_url}")
            if get_session_id:
                session_id = get_session_id()
                if session_id:
                    print(f"Session ID: {session_id}")

            # Start interactive loop
            await self.interactive_loop()

    async def list_tools(self):
        """Get list of available tools from server"""
        if not self.session:
            print("❌ Not connected to server")
            return

        try:
            result = await self.session.list_tools()
            if hasattr(result, "tools") and result.tools:
                print("\n📋 Available tools:")
                for i, tool in enumerate(result.tools, 1):
                    print(f"{i}. {tool.name}")
                    if tool.description:
                        print(f"   Description: {tool.description}")
                    print()
            else:
                print("No tools available")
        except Exception as e:
            print(f"❌ Failed to get tool list: {e}")

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None):
        """
        Call specified tool

        Args:
            tool_name: Name of tool to call
            arguments: Arguments to pass to tool (optional)
        """
        if not self.session:
            print("❌ Not connected to server")
            return

        try:
            result = await self.session.call_tool(tool_name, arguments or {})
            print(f"\n🔧 Tool '{tool_name}' execution result:")
            if hasattr(result, "content"):
                for content in result.content:
                    if content.type == "text":
                        print(content.text)
                    else:
                        print(content)
            else:
                print(result)
        except Exception as e:
            print(f"❌ Failed to call tool '{tool_name}': {e}")

    async def interactive_loop(self):
        """Run interactive command loop"""
        print("\n🎯 Interactive MCP Client")
        print("Commands:")
        print("  list - Display available tools")
        print("  call <tool_name> [args] - Call a tool")
        print("  quit - Exit client")
        print()

        while True:
            try:
                command = input("mcp> ").strip()

                if not command:
                    continue

                if command == "quit":
                    break

                elif command == "list":
                    await self.list_tools()

                elif command.startswith("call "):
                    parts = command.split(maxsplit=2)
                    tool_name = parts[1] if len(parts) > 1 else ""

                    if not tool_name:
                        print("❌ Please specify tool name")
                        continue

                    # Parse arguments (simple JSON format)
                    arguments = {}
                    if len(parts) > 2:
                        import json

                        try:
                            arguments = json.loads(parts[2])
                        except json.JSONDecodeError:
                            print("❌ Invalid argument format (use JSON format)")
                            continue

                    await self.call_tool(tool_name, arguments)

                else:
                    print("❌ Unknown command. Try 'list', 'call <tool_name>', or 'quit'")

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except EOFError:
                break


async def main():
    """
    Main entry point

    Loads settings from environment variables and starts MCP client.
    """
    print("=" * 70)
    print("MCP Client with OAuth Authentication")
    print("=" * 70)

    # Load configuration from environment variables
    server_url = os.getenv("MCP_SERVER_URL")
    use_dcr = os.getenv("MCP_USE_DCR", "false").lower() == "true"
    client_id = os.getenv("COGNITO_APP_CLIENT_ID")
    client_secret = os.getenv("COGNITO_APP_CLIENT_SECRET")

    # Validate configuration
    print("\n[Configuration]")
    if server_url:
        print(f"  Server URL:      {server_url}")
    else:
        # Traditional port-based approach (for backward compatibility)
        server_port = os.getenv("MCP_SERVER_PORT", 8000)
        server_url = f"http://localhost:{server_port}/mcp"
        print(f"  Server URL:      {server_url} (default)")

    print(f"  Transport:       StreamableHTTP")
    print(f"  Using DCR:       {use_dcr}")

    if not use_dcr:
        print(f"  Client ID:       {client_id if client_id else '❌ Not set'}")
        print(f"  Client Secret:   {'✅ Set' if client_secret else '❌ Not set'}")

        # Validate required environment variables when DCR is disabled
        if not client_id or not client_secret:
            print("\n❌ Configuration error:")
            print("  When MCP_USE_DCR=false, the following are required:")
            print("  - COGNITO_APP_CLIENT_ID")
            print("  - COGNITO_APP_CLIENT_SECRET")
            print("\n📝 Please check your .env file")
            return

    print("\n🚀 Starting MCP client connection...")

    try:
        client = SimpleAuthClient(server_url, use_dcr)
        await client.connect()
    except ValueError as e:
        print(f"\n❌ Configuration error: {e}")
        print("\n📝 Please check your .env file contains:")
        print("  - MCP_SERVER_URL=<gateway_url>")
        print("  - MCP_USE_DCR=false")
        print("  - COGNITO_APP_CLIENT_ID=<client_id>")
        print("  - COGNITO_APP_CLIENT_SECRET=<client_secret>")
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        import traceback
        traceback.print_exc()


def cli():
    """CLI entry point for uv script"""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
