# MCP with OAuth Authentication

リモート MCP サーバーに OAuth 認証を実装するためのサンプル実装とデモ環境を提供するリポジトリです。

MCP Specの2025-06-18に準拠しています
https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization

本リポジトリの実装は、以下のリポジトリを大いに参考にしています
https://github.com/modelcontextprotocol/python-sdk/tree/main/examples

## このリポジトリの目的

このリポジトリは、**リモート MCP (Model Context Protocol) サーバーに OAuth認証機能を追加する方法**を学び、実際に体験するためのサンプル実装集です。

すべてのコンポーネントがローカルで実装されたものから、各コンポーネントをマネージドに実装したものまでを見ることによって、理解を深めることを目的としています。

## フォルダ構成

このリポジトリには、現在 3 つの異なる実装パターンが含まれています：

### `cognito-and-ac-gateway/`
**AWS フルマネージド実装**

AWS のマネージドサービスを使用した構成のサンプルです。

**コンポーネント:**
- 認可サーバー: Amazon Cognito
- MCPサーバー: AgentCore Gateway
- クライアント: ローカル(client.py)


### `cognito/`
**Cognito とローカル MCP サーバーのハイブリッド実装**

AWS Cognito を認証基盤として使用し、MCP サーバーはローカルで実行する構成のサンプルです。

**コンポーネント:**
- 認可サーバー: Amazon Cognito
- MCPサーバー: ローカル(mcp-server-with-auth.py)
- クライアント: ローカル(client.py)


### `local/`
**ローカル環境で完結する実装**

すべてのコンポーネントがローカルで動作する、学習と開発に最適なサンプルです。

**コンポーネント:**
- 認可サーバー: ローカル(auth_server.py)
- MCPサーバー: ローカル(mcp-server-with-auth.py)
- クライアント: ローカル(client.py)

