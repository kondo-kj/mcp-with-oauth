# MCP with OAuth 2.0 Authentication

リモート MCP サーバーに OAuth 2.0 認証を実装するためのサンプル実装とデモ環境を提供するリポジトリです。

MCP Specの2025-06-18に準拠しています
https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization

本リポジトリの実装は、以下のリポジトリを大いに参考にしています
https://github.com/modelcontextprotocol/python-sdk/tree/main/examples

## このリポジトリの目的

このリポジトリは、**リモート MCP (Model Context Protocol) サーバーに OAuth 2.0 認証機能を追加する方法**を学び、実際に体験するためのサンプル実装集です。

すべてのコンポーネントがローカルで実装されたものから、各コンポーネントをマネージドに実装したものまでを見ることによって、理解を深めることを目的としています。

## フォルダ構成

このリポジトリには、現在 2 つの異なる実装パターンが含まれています：

### `cognito-and-ac-gateway/`
**AWS を使用した実装**

AWS のマネージドサービスを使用した構成のサンプルです。

**使用する AWS サービス:**
- **Amazon Cognito** - OAuth 2.0 認可サーバー（ユーザー認証基盤）
- **AWS Bedrock AgentCore Gateway** - OAuth 認証機能付き MCP サーバー
- **AWS Lambda** - MCP ツールの実装（バックエンド）


### `local/`
**ローカル環境で完結する実装**

すべてのコンポーネントがローカルで動作する、学習と開発に最適なサンプルです。

**含まれるコンポーネント:**
- **ローカル認証サーバー** - Python/Starlette で実装された OAuth 2.0 認可サーバー
- **ローカル MCP サーバー** - FastMCP で実装された Resource Server
- **MCP クライアント** - OAuth 2.0 対応クライアント実装


## クイックスタート

### ローカル環境で試す（推奨）

最も簡単に始められる方法です：

```bash
# 依存関係のインストール
uv sync

# local フォルダに移動
cd local

# 詳細は local/README.md を参照
```

3 つのターミナルで以下を順番に起動：
1. `uv run python auth_server.py --port=9000`
2. `uv run python mcp-server-with-auth.py --port=8001 --auth-server=http://localhost:9000`
3. `MCP_USE_DCR=false uv run python client.py`

### AWS 環境で試す

本番環境に近い構成を体験できます：

```bash
# 依存関係のインストール
uv sync

# cognito-and-ac-gateway フォルダに移動
cd cognito-and-ac-gateway

# 詳細は cognito-and-ac-gateway/README.md を参照
```

AWS アカウントと適切な権限が必要です。

