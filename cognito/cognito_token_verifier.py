"""
AWS Cognito JWT トークン検証モジュール

このモジュールは AWS Cognito User Pool から発行された JWT トークンを検証します。
RFC 7519 (JWT) および AWS Cognito の仕様に準拠した実装です。
"""

import jwt
import requests
import logging
from jwt.algorithms import RSAAlgorithm
from typing import Optional, Dict, Any
from dataclasses import dataclass
from mcp.server.auth.provider import TokenVerifier, AccessToken

logger = logging.getLogger(__name__)


class CognitoTokenVerifier(TokenVerifier):
    """
    AWS Cognito JWT トークン検証クラス
    
    Cognito User Pool から発行された Access Token および ID Token を検証します。
    JWKS (JSON Web Key Set) を使用してトークンの署名を検証し、
    クレームの妥当性をチェックします。
    """
    
    def __init__(self, user_pool_id: str, app_client_id: str, expected_resource: Optional[str] = None):
        """
        CognitoTokenVerifier を初期化

        Args:
            user_pool_id: Cognito User Pool ID (例: us-west-2_XXXXXXXXX)
            app_client_id: Cognito App Client ID
            expected_resource: RFC 8707で期待されるリソースURI（設定時は強制的にRFC 8707検証を実行）
        """
        self.user_pool_id = user_pool_id
        # User Pool ID から region を自動抽出 (例: "us-west-2_XXXXXXXXX" → "us-west-2")
        self.region = user_pool_id.split('_')[0]
        self.app_client_id = app_client_id
        self.expected_resource = expected_resource
        self.jwks_url = f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
        self.issuer = f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool_id}"
        self._jwks_cache = None
    
    def _verify_resource_binding(self, payload: Dict[str, Any]) -> bool:
        """
        RFC 8707 Resource Indicator検証
        
        Args:
            payload: JWT payload
            
        Returns:
            bool: 検証結果
        """
        if not self.expected_resource:
            # expected_resource が未設定の場合は RFC 8707 検証をスキップ
            logger.info("RFC 8707 Resource binding検証をスキップ（expected_resource未設定）")
            return True
        
        aud = payload.get('aud')
        if not aud:
            logger.error("RFC 8707: 'aud'クレームが見つかりません")
            return False
        
        # audクレームが期待されるリソースと一致するかチェック
        if aud == self.expected_resource:
            logger.info(f"✅ RFC 8707 Resource Binding検証成功: {aud}")
            return True
        else:
            logger.error(f"❌ RFC 8707 Resource Binding検証失敗. 期待値: {self.expected_resource}, 実際値: {aud}")
            return False

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        """
        Cognito JWT トークンを検証
        
        Args:
            token: 検証対象の JWT トークン
            
        Returns:
            AuthInfo: 検証成功時の認証情報、失敗時は None
        """
        try:
            # JWKS の取得（初回のみ、以降はキャッシュを使用）
            if not self._jwks_cache:
                response = requests.get(self.jwks_url)
                response.raise_for_status()
                self._jwks_cache = response.json()

            # JWT ヘッダーから Key ID を取得
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get('kid')

            # 対応する公開鍵を JWKS から検索
            key = None
            for jwk in self._jwks_cache['keys']:
                if jwk['kid'] == kid:
                    key = RSAAlgorithm.from_jwk(jwk)
                    break

            if not key:
                logger.error(f"公開鍵が見つかりません: kid={kid}")
                return None

            # トークンタイプを事前確認
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            token_use = unverified_payload.get('token_use')
            
            # トークンタイプに応じた検証
            if token_use == 'access':
                # Access Token の検証（audience クレームなし）

                # RFC 8707対応: audクレームがある場合は検証する
                has_aud = 'aud' in unverified_payload
                
                if has_aud:
                    # RFC 8707 Resource Binding対応のAccess Token
                    payload = jwt.decode(
                        token,
                        key,
                        algorithms=['RS256'],
                        issuer=self.issuer,
                        leeway=300,  # ±5分の時刻誤差を許容
                        options={"verify_aud": False}  # audクレームを検証
                    )
                    
                    # RFC 8707 Resource Indicator検証
                    if not self._verify_resource_binding(payload):
                        return None
                        
                else:
                    # 従来のAccess Token（audクレームなし）
                    payload = jwt.decode(
                        token,
                        key,
                        algorithms=['RS256'],
                        issuer=self.issuer,
                        leeway=300,
                        options={"verify_aud": False}
                    )
                
                
                # Client ID の検証
                token_client_id = payload.get('client_id')
                if token_client_id != self.app_client_id:
                    logger.error(f"Client ID が一致しません: 期待値={self.app_client_id}, 実際値={token_client_id}")
                    return None
                    
            elif token_use == 'id':
                # ID Token の検証（audience クレームあり）
                payload = jwt.decode(
                    token,
                    key,
                    algorithms=['RS256'],
                    audience=self.app_client_id,
                    issuer=self.issuer,
                    leeway=300
                )
            else:
                logger.error(f"不明なトークンタイプ: {token_use}")
                return None

            # 必要なスコープの確認
            token_scopes = payload.get('scope', '').split()
            if 'openid' not in token_scopes:
                logger.error(f"必要なスコープ 'profile' が見つかりません: {token_scopes}")
                return None
            
            # RFC 8707 Resource Indicator をAccessTokenに含める
            resource_indicator = payload.get('aud') if token_use == 'access' else None

            # 正式なAccessTokenオブジェクトを返す
            return AccessToken(
                token=token,  # 元のJWTトークン
                client_id=payload.get('client_id', self.app_client_id),
                scopes=token_scopes,
                expires_at=payload.get('exp'),
                resource=resource_indicator  # RFC 8707 resource indicator
            )

        except jwt.ExpiredSignatureError:
            logger.error("トークンの有効期限が切れています")
            return None
        except jwt.InvalidTokenError as e:
            logger.error(f"無効なトークンです: {e}")
            return None
        except Exception as e:
            logger.error(f"トークン検証中にエラーが発生しました: {e}")
            return None
