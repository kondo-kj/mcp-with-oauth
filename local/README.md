# Local OAuth 2.0 Authentication

ローカル環境で完結する OAuth 2.0 認証付き MCP サーバーのサンプル実装です。

この実装は以下のリポジトリの実装に微修正を加えたものになっています。
- https://github.com/modelcontextprotocol/python-sdk/tree/main/examples/clients/simple-auth-client
- https://github.com/modelcontextprotocol/python-sdk/tree/main/examples/servers/simple-auth

⚠️ **重要**: このプロジェクトはデモンストレーション目的で作成されており、本番環境での使用は推奨されません。

## 🌟 このサンプルについて

このサンプルでは、**すべてのコンポーネントがローカルで動作**します：
- **Authorization Server**: ローカル認証サーバー（Python/Starlette）
- **Resource Server**: MCP Server（FastMCP）
- **Client**: MCP クライアント


## 📁 ファイル構成

- **`auth_server.py`** - ローカル OAuth 2.0 認証サーバー
- **`simple_auth_provider.py`** - シンプル認証プロバイダー実装
- **`mcp-server-with-auth.py`** - OAuth 2.0 認証機能付き MCP サーバー（Resource Server）
- **`client.py`** - OAuth 2.0 対応 MCP クライアント
- **`token_verifier.py`** - トークン検証ライブラリ（Token Introspection 対応）



**認証フロー:**
1. Client が Authorization Server にリダイレクト
2. ユーザーがログイン（デモ認証情報）
3. Authorization Code を取得
4. Access Token に交換
5. Resource Server が Token Introspection で検証
6. MCP API にアクセス

## 🚀 実行手順

### 1. 環境のセットアップ

```bash
# プロジェクトルートで依存関係をインストール
uv sync
```

### 2. 環境変数の設定

```bash
cd local
cp .env.example .env
```

`.env`ファイルを編集して、必要に応じて設定を変更してください：

```bash
# MCP Client Configuration
MCP_SERVER_PORT=8001          # クライアントが接続するサーバーのポート
MCP_USE_DCR=false            # Dynamic Client Registration の使用

# MCP Authorization Server Configuration
MCP_AUTH_PORT=9000           # 認証サーバーのポート

# MCP Resource Server Configuration
MCP_RESOURCE_PORT=8001                           # サーバーが起動するポート
MCP_RESOURCE_AUTH_SERVER_URL=http://localhost:9000  # 認証サーバーURL
MCP_RESOURCE_TRANSPORT=streamable-http           # トランスポートプロトコル
MCP_RESOURCE_OAUTH_STRICT=false                  # RFC 8707 検証の有効化
```

### 3. デフォルト認証情報

このサンプルでは、以下のデフォルト認証情報が事前設定されています：

**デモユーザー:**
- Username: `demo_user`
- Password: `demo_password`

**事前登録クライアント:**
- Client ID: `simple-mcp-client`
- Client Secret: `simple-mcp-secret-123`

### 4. Authorization Server の起動

```bash
cd local
uv run python auth_server.py
```

サーバーは`.env`ファイルの設定を読み込んで起動します。

**起動すると以下のエンドポイントが利用可能になります:**
- `/oauth2/authorize` - 認証エンドポイント
- `/oauth2/token` - トークンエンドポイント
- `/login` - ログインページ
- `/introspect` - トークン検証エンドポイント（Resource Server 用）

**設定可能な環境変数（`.env`ファイルで設定）:**
- `MCP_AUTH_PORT` - ポート番号（デフォルト: 9000）

### 5. Resource Server (MCP Server) の起動

新しいターミナルを開いて：

```bash
cd local
uv run python mcp-server-with-auth.py
```

サーバーは`.env`ファイルの設定を読み込んで起動します。

**起動すると以下のエンドポイントが利用可能になります:**
- `/mcp` - MCP API
- `/.well-known/oauth-protected-resource` - リソースメタデータ（RFC 9728）

**設定可能な環境変数（`.env`ファイルで設定）:**
- `MCP_RESOURCE_PORT` - ポート番号（デフォルト: 8001）
- `MCP_RESOURCE_AUTH_SERVER_URL` - 認証サーバー URL（デフォルト: http://localhost:9000）
- `MCP_RESOURCE_TRANSPORT` - トランスポートプロトコル（デフォルト: streamable-http）
- `MCP_RESOURCE_OAUTH_STRICT` - RFC 8707 リソース検証を有効化（デフォルト: false）

### 6. Client での接続

新しいターミナルを開いて：

```bash
cd local
uv run python client.py
```

クライアントは`.env`ファイルの設定を読み込んで起動します。ブラウザが開き、ローカル認証サーバーのログイン画面が表示されます。

**ログイン情報:**
- **Username**: `demo_user`
- **Password**: `demo_password`

認証後、以下のコマンドが使用可能：

```
mcp> list             # 利用可能なツール一覧
mcp> call get_time    # 現在時刻を取得
mcp> quit             # 終了
```

## 📝 クライアント認証モード（DCR フラグ）

クライアントは 2 つの認証モードをサポートしています。`.env` ファイルの `MCP_USE_DCR` で切り替えることができます。

### DCR 無効モード（`MCP_USE_DCR=false`）【推奨】

事前に認証サーバーに登録されたクライアント情報を使用します。

**特徴:**
- クライアント ID/シークレットが事前に決まっている
- Dynamic Client Registration (DCR) のエンドポイントを使用しない
- シンプルで確実な動作
- このデモでは、認証サーバー起動時に自動的にクライアント情報が登録されます

**使用するクライアント情報:**
- Client ID: `simple-mcp-client`
- Client Secret: `simple-mcp-secret-123`

**設定方法:**
`.env` ファイルを編集：
```bash
MCP_USE_DCR=false
```

### DCR 有効モード（`MCP_USE_DCR=true`）

クライアント起動時に動的にクライアント情報を登録します（RFC 7591: OAuth 2.0 Dynamic Client Registration Protocol）。

**特徴:**
- クライアント起動時に認証サーバーの `/register` エンドポイントを呼び出し
- 動的に Client ID と Client Secret が発行される
- 毎回異なるクライアント情報が生成される
- 本番環境でのクライアント管理に適している
- このデモ環境では DCR 機能が有効になっており、両方のモードが動作します

**設定方法:**
`.env` ファイルを編集：
```bash
MCP_USE_DCR=true
```

**💡 使い分け:**
- **DCR 無効（false）**: デモやテストで固定のクライアント情報を使いたい場合に推奨
- **DCR 有効（true）**: 本番環境に近い動的なクライアント登録を試したい場合



