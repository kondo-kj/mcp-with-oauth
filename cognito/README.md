# MCP Server with Cognito OAuth

AWS Cognito を使った OAuth 認証付き MCP サーバーのサンプル実装です。

## 📁 ファイル構成

- **`mcp-server-with-auth.py`** - MCP サーバー（ローカルで実行）
- **`setup_cognito.py`**, **`add_resource_server.py`** - Cognitoのセットアップスクリプト
- **`client.py`** - MCP サーバーに接続する MCP クライアント（ローカルで実行）

## 🚀 実行手順

### 1. 環境のセットアップ

```bash
# プロジェクトルートで依存関係をインストール
uv sync
```

### 2. 環境変数の設定

親ディレクトリの `.env.example` を参考に `.env` ファイルを作成：

```bash
# .env.example をコピー
cd cognito
cp .env.example .env

# .env を編集（必要に応じて AWS リージョンなどを変更）
```

### 3. Cognito のセットアップ

Cognito User Pool、アプリクライアント、テストユーザーを作成します。

**⚠️ 注意:** `setup_cognito.py` 内のユーザーID とパスワードを適宜変更してください。

```bash
# Cognito リソースを作成
uv run python setup_cognito.py
```

**このスクリプトで作成されるもの:**
1. **Cognito User Pool** - ユーザー認証基盤
   - Email による認証を有効化
   - パスワードポリシーの設定
2. **App Client** - OAuth 2.0 クライアント
   - Authorization Code フロー対応
   - Refresh Token サポート
   - Client Secret 付き
3. **Hosted UI Domain** - Cognito のログインページ用ドメイン
   - `{random-prefix}.auth.{region}.amazoncognito.com` の形式
4. **テストユーザー** - 動作確認用
   - Email とパスワードで即座にログイン可能な状態で作成

**出力された値を `.env` に追加:**
- `COGNITO_USER_POOL_ID`
- `COGNITO_REGION`
- `COGNITO_APP_CLIENT_ID`
- `COGNITO_APP_CLIENT_SECRET`
- `COGNITO_DOMAIN`

### 4. MCP サーバーの起動

```bash
# MCP サーバーを起動
uv run python mcp-server-with-auth.py
```

サーバーはデフォルトで `http://localhost:8001/mcp` で起動します。

**出力された `MCP_SERVER_URL` を `.env` に追加してください。**
デフォルトのポートで起動している場合、なにもしなくても大丈夫です。

### 5. リソースサーバーの追加

MCP サーバー URL を Cognito User Pool のリソースサーバーとして登録します。

```bash
# リソースサーバーを追加
# 別のターミナルで実行
uv run python add_resource_server.py
```

このステップにより、Cognito が MCP サーバー URL を認可対象のリソースとして認識できるようになります。

### 6. クライアントでの接続

```bash
# MCP クライアントを起動
uv run python client.py
```

ブラウザが開き、Cognito のログイン画面が表示されます。

**ログイン情報:**
- **ユーザーID（Email）**: `setup_cognito.py` で設定したテストユーザーの Email
- **パスワード**: `setup_cognito.py` で設定したテストユーザーのパスワード

認証後、以下のコマンドが使用可能：

```
mcp> list                    # 利用可能なツール一覧
mcp> call get_time           # 現在時刻を取得
mcp> quit                    # 終了
```

## 📝 各スクリプトの詳細

### setup_cognito.py

Cognito の完全なセットアップを行います。

**主な機能：**
- 冪等性: 何度実行しても安全
- User Pool と App Client の作成
- Managed Login (v2) の有効化
- テストユーザーの作成

**設定のカスタマイズ:**
スクリプト内の以下の変数を編集できます：
- `POOL_NAME` - User Pool 名
- `CLIENT_NAME` - App Client 名
- `COGNITO_DOMAIN_PREFIX` - ドメインプレフィックス（グローバルに一意である必要あり）
- `TEST_USER_NAME` - テストユーザーのユーザー名
- `TEST_USER_EMAIL` - テストユーザーの Email
- `TEST_USER_PERM_PASSWORD` - テストユーザーのパスワード

### add_resource_server.py

Cognito User Pool に MCP サーバーをリソースサーバーとして追加します（**必須ステップ**）。

**用途：**
- MCP サーバー URL を Cognito のリソースサーバーとして登録
- Cognito が MCP サーバーを認可対象のリソースとして認識できるようにする
- カスタムスコープの定義（オプション）

**実行タイミング：**
- MCP サーバー起動後、クライアント接続前に実行

**実行：**
```bash
uv run python add_resource_server.py
```

### mcp-server-with-auth.py

Cognito 認証対応のメイン MCP サーバーです。

**主な機能：**
- Cognito JWT トークンの直接検証（別途 Authorization Server 不要）
- RFC 9728 Protected Resource Metadata 対応
- RFC 8707 Resource Indicators 対応
- 認証が必要なツールの提供

**コマンドラインオプション：**
```bash
uv run python mcp-server-with-auth.py --port 8001 --transport streamable-http
```

オプション：
- `--port` - サーバーポート（デフォルト: 8001）
- `--transport` - トランスポートプロトコル: `sse` または `streamable-http`（デフォルト: streamable-http）

### client.py

MCP サーバーに接続する OAuth 認証対応のクライアントです。

**認証フロー：**
1. ローカルで OAuth コールバックサーバーを起動（ポート 3030）
2. ブラウザで Cognito 認証ページを開く
3. 認証後、Authorization Code を受け取る
4. トークンを取得して MCP サーバーに接続

**対応する認証方式：**
- DCR (Dynamic Client Registration) - Cognito では非対応
- 事前登録クライアント（Cognito アプリクライアント）- **この方式を使用**
