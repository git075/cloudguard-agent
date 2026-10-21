"""
GitHub App Authentication Service for CloudGuard FinOps.
Generates RS256 JWT app tokens and short-lived Installation Access Tokens for fine-grained multi-tenant GitHub integration.
"""
import os
import time
import logging
from typing import Dict, Any, Optional

import jwt
import requests

logger = logging.getLogger("cloudguard.github_app")


class GitHubAppAuth:
    """
    Handles GitHub App RS256 JWT generation and installation token exchange.
    Replaces static Personal Access Tokens (PAT) with secure, short-lived (1-hour) installation tokens.
    """

    def __init__(
        self,
        app_id: Optional[str] = None,
        private_key_pem: Optional[str] = None,
        use_mock: bool = True,
    ):
        self.app_id = app_id or os.getenv("GITHUB_APP_ID")
        self.private_key_pem = private_key_pem or os.getenv("GITHUB_APP_PRIVATE_KEY")
        self.use_mock = use_mock

    def generate_app_jwt(self) -> str:
        """
        Generates a 10-minute JSON Web Token (JWT) signed with the GitHub App's RSA Private Key (RS256).
        Used to authenticate as the GitHub App itself to request installation access tokens.
        """
        if self.use_mock or not self.app_id or not self.private_key_pem:
            logger.info("GitHubAppAuth: Operating in MOCK mode (App JWT).")
            return "mock-github-app-jwt-token"

        now = int(time.time())
        payload = {
            "iat": now - 60,       # Issued 60s in past to account for clock skew
            "exp": now + (10 * 60), # Valid for 10 minutes (GitHub max limit)
            "iss": self.app_id,     # GitHub App ID
        }

        # Sign JWT using RS256 RSA private key
        encoded_jwt = jwt.encode(payload, self.private_key_pem, algorithm="RS256")
        return encoded_jwt

    def get_installation_access_token(self, installation_id: str) -> Dict[str, Any]:
        """
        Exchanges the GitHub App JWT for a short-lived (1-hour) Installation Access Token
        scoped to a specific customer's GitHub organization installation.
        """
        if self.use_mock or not self.app_id or not self.private_key_pem:
            logger.info("GitHubAppAuth: Returning MOCK installation token for ID '%s'.", installation_id)
            return {
                "token": f"ghs_mock_installation_token_{installation_id}",
                "expires_at": "2026-10-07T12:00:00Z",
                "permissions": {"pull_requests": "write", "contents": "write"},
            }

        app_jwt = self.generate_app_jwt()
        url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        response = requests.post(url, headers=headers, timeout=10)
        if response.status_code != 201:
            logger.error("Failed to fetch installation token: %s", response.text)
            raise ValueError(f"GitHub App token exchange failed with status {response.status_code}: {response.text}")

        data = response.json()
        logger.info("Successfully minted GitHub App installation token for installation '%s'.", installation_id)
        return data

    def get_pygithub_client(self, installation_id: str) -> Any:
        """
        Returns a PyGithub client instance authenticated with a fresh installation access token.
        """
        token_data = self.get_installation_access_token(installation_id)
        token = token_data["token"]

        if self.use_mock or token.startswith("ghs_mock_"):
            return None

        from github import Github
        return Github(token)
