# AgentCore Gateway with Cognito OAuth

AWS Bedrock AgentCore Gateway と Amazon Cognito を使った OAuth 認証付き MCP サーバーのサンプル実装です。

## 📁 ファイル構成

- **`create_gateway.py`** - Lambda 関数と AgentCore Gateway を作成するメインスクリプト
- **`add_resource_server.py`** - Gateway を Cognito のリソースサーバーとして登録（必須）
- **`client.py`** - Gateway に接続する MCP クライアント（OAuth 認証付き）

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
cp .env.example .env

# .env を編集（必要に応じて AWS リージョンなどを変更）
```

### 3. Cognito のセットアップ

Cognito User Pool、アプリクライアント、テストユーザーを作成します。

**⚠️ 注意:** `setup_cognito.py` 内のユーザーID とパスワードを適宜変更してください。

```bash
# Cognito リソースを作成
cd cognito-and-ac-gateway
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
- `COGNITO_APP_CLIENT_ID`
- `COGNITO_APP_CLIENT_SECRET`

### 4. Gateway の作成

```bash
# Lambda 関数と Gateway を作成（冪等性あり）
uv run python create_gateway.py
```

このスクリプトは以下を実行します：
1. Lambda 用 IAM ロールの作成
2. Lambda 関数の作成（現在時刻を返す `get_current_time_tool`）
3. Gateway 用 IAM ロールの作成
4. AgentCore Gateway の作成（OAuth 認証設定含む）
5. Lambda を Gateway のターゲットとして登録

**出力された `MCP_SERVER_URL` を `.env` に追加してください。**

### 5. リソースサーバーの追加

Gateway URL を Cognito User Pool のリソースサーバーとして登録します。

```bash
# リソースサーバーを追加（冪等性あり）
uv run python add_resource_server.py
```

このステップにより、Cognito が Gateway URL を認可対象のリソースとして認識できるようになります。

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
mcp> list                                    # 利用可能なツール一覧
mcp> call sample-agentcore-gateway-lambda-target___get_current_time_tool  # 現在時刻を取得
mcp> quit                                    # 終了
```

## 📝 各スクリプトの詳細

### create_gateway.py

AgentCore Gateway の完全なセットアップを行います。

**主な機能：**
- 冪等性: 何度実行しても安全
- Lambda 関数と Gateway が既に存在する場合は再利用
- Gateway のステータスを監視（READY になるまで待機）

**作成されるリソース：**
- Lambda 関数: `agentcore-gateway-lambda`
- Gateway: `sample-agentcore-gateway`
- IAM ロール: Lambda 用と Gateway 用

### client.py

MCP クライアントとして Gateway に接続します。

**認証フロー：**
1. ローカルで OAuth コールバックサーバーを起動（ポート 3030）
2. ブラウザで Cognito 認証ページを開く
3. 認証後、Authorization Code を受け取る
4. トークンを取得して Gateway に接続

**対応する認証方式：**
- DCR (Dynamic Client Registration)
- 事前登録クライアント（Cognito アプリクライアント）

### add_resource_server.py

Cognito User Pool に AgentCore Gateway をリソースサーバーとして追加します（**必須ステップ**）。

**用途：**
- Gateway URL を Cognito のリソースサーバーとして登録
- Cognito が Gateway を認可対象のリソースとして認識できるようにする
- カスタムスコープの定義（オプション）

**実行タイミング：**
- Gateway 作成後、クライアント接続前に実行

**実行：**
```bash
uv run python cognito-and-ac-gateway/add_resource_server.py
```
