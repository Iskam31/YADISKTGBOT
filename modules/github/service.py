"""GitHub API client.

Handles all interactions with GitHub REST API.
Documentation: https://docs.github.com/en/rest
"""

import aiohttp
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class GitHubAPI:
    """Async client for GitHub REST API."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._timeout = aiohttp.ClientTimeout(total=15)

    async def check_token(self) -> Optional[dict]:
        """Validate token and get user info.

        Returns:
            Dict with 'login', 'name', 'avatar_url' if valid, None otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/user",
                    headers=self.headers,
                    timeout=self._timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"GitHub token valid for user: {data.get('login')}")
                        return {
                            "login": data.get("login"),
                            "name": data.get("name"),
                            "avatar_url": data.get("avatar_url"),
                        }
                    else:
                        logger.warning(f"GitHub token validation failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"GitHub token validation error: {e}")
            return None

    async def get_repo(self, owner: str, name: str) -> Optional[dict]:
        """Get repository info.

        Returns:
            Dict with repo info or None if not found/no access
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/repos/{owner}/{name}",
                    headers=self.headers,
                    timeout=self._timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "full_name": data.get("full_name"),
                            "description": data.get("description"),
                            "private": data.get("private"),
                            "open_issues_count": data.get("open_issues_count"),
                            "language": data.get("language"),
                            "default_branch": data.get("default_branch"),
                            "html_url": data.get("html_url"),
                        }
                    elif response.status == 404:
                        logger.warning(f"Repo not found: {owner}/{name}")
                        return None
                    else:
                        logger.error(f"Get repo failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Get repo error: {e}")
            return None

    async def list_repos(
        self, per_page: int = 30, page: int = 1, affiliation: str = "owner,collaborator"
    ) -> Optional[list]:
        """List authenticated user's repositories.

        Args:
            per_page: Results per page
            page: Page number
            affiliation: Comma-separated: owner, collaborator, organization_member

        Returns:
            List of repo dicts or None on error
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/user/repos",
                    headers=self.headers,
                    params={
                        "per_page": per_page,
                        "page": page,
                        "sort": "updated",
                        "direction": "desc",
                        "affiliation": affiliation,
                    },
                    timeout=self._timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return [
                            {
                                "full_name": r.get("full_name"),
                                "description": r.get("description"),
                                "private": r.get("private"),
                                "language": r.get("language"),
                                "open_issues_count": r.get("open_issues_count"),
                                "owner": r.get("owner", {}).get("login"),
                            }
                            for r in data
                        ]
                    else:
                        logger.error(f"List repos failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"List repos error: {e}")
            return None

    async def list_issues(
        self, owner: str, name: str, state: str = "open", per_page: int = 10, page: int = 1
    ) -> Optional[list]:
        """List issues for a repository (excludes pull requests).

        GitHub's /issues endpoint returns both issues and PRs mixed together.
        We fetch extra items and filter out PRs to guarantee enough real issues.

        Returns:
            List of issue dicts or None on error
        """
        try:
            issues = []
            api_page = page
            # Fetch up to 3 API pages to collect enough real issues
            for _ in range(3):
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self.BASE_URL}/repos/{owner}/{name}/issues",
                        headers=self.headers,
                        params={
                            "state": state,
                            "per_page": 100,
                            "page": api_page,
                            "sort": "created",
                            "direction": "desc",
                        },
                        timeout=self._timeout
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                        elif response.status == 404:
                            return None
                        else:
                            logger.error(f"List issues failed: {response.status}")
                            return None

                # Filter out pull requests
                for i in data:
                    if "pull_request" not in i:
                        issues.append({
                            "number": i.get("number"),
                            "title": i.get("title"),
                            "state": i.get("state"),
                            "user": i.get("user", {}).get("login"),
                            "created_at": i.get("created_at"),
                            "labels": [l.get("name") for l in i.get("labels", [])],
                            "comments": i.get("comments"),
                            "html_url": i.get("html_url"),
                        })

                # Got enough or no more data
                if len(issues) >= per_page or len(data) < 100:
                    break
                api_page += 1

            # Paginate the collected issues
            start = (page - 1) * per_page
            return issues[start:start + per_page]

        except Exception as e:
            logger.error(f"List issues error: {e}")
            return None

    async def create_issue(
        self, owner: str, name: str, title: str, body: Optional[str] = None
    ) -> Optional[dict]:
        """Create a new issue.

        Returns:
            Dict with issue info or None on error
        """
        try:
            payload = {"title": title}
            if body:
                payload["body"] = body

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/repos/{owner}/{name}/issues",
                    headers=self.headers,
                    json=payload,
                    timeout=self._timeout
                ) as response:
                    if response.status == 201:
                        data = await response.json()
                        return {
                            "number": data.get("number"),
                            "title": data.get("title"),
                            "html_url": data.get("html_url"),
                        }
                    elif response.status == 404:
                        logger.warning(f"Repo not found: {owner}/{name}")
                        return None
                    elif response.status == 403:
                        logger.warning(f"No permission to create issue in {owner}/{name}")
                        return None
                    else:
                        text = await response.text()
                        logger.error(f"Create issue failed: {response.status} - {text}")
                        return None
        except Exception as e:
            logger.error(f"Create issue error: {e}")
            return None

    async def close_issue(self, owner: str, name: str, number: int) -> Optional[dict]:
        """Close an issue.

        Returns:
            Dict with issue info or None on error
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(
                    f"{self.BASE_URL}/repos/{owner}/{name}/issues/{number}",
                    headers=self.headers,
                    json={"state": "closed"},
                    timeout=self._timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "number": data.get("number"),
                            "title": data.get("title"),
                            "state": data.get("state"),
                            "html_url": data.get("html_url"),
                        }
                    elif response.status == 404:
                        return None
                    else:
                        logger.error(f"Close issue failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Close issue error: {e}")
            return None

    async def get_issue(self, owner: str, name: str, number: int) -> Optional[dict]:
        """Get detailed issue information.

        Returns:
            Dict with issue details or None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/repos/{owner}/{name}/issues/{number}",
                    headers=self.headers,
                    timeout=self._timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "number": data.get("number"),
                            "title": data.get("title"),
                            "body": data.get("body"),
                            "state": data.get("state"),
                            "user": data.get("user", {}).get("login"),
                            "created_at": data.get("created_at"),
                            "closed_at": data.get("closed_at"),
                            "labels": [l.get("name") for l in data.get("labels", [])],
                            "comments": data.get("comments"),
                            "html_url": data.get("html_url"),
                        }
                    elif response.status == 404:
                        return None
                    else:
                        logger.error(f"Get issue failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Get issue error: {e}")
            return None

    async def list_pulls(
        self, owner: str, name: str, state: str = "open", per_page: int = 10, page: int = 1
    ) -> Optional[list]:
        """List pull requests for a repository.

        Returns:
            List of PR dicts or None on error
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/repos/{owner}/{name}/pulls",
                    headers=self.headers,
                    params={
                        "state": state,
                        "per_page": per_page,
                        "page": page,
                        "sort": "created",
                        "direction": "desc",
                    },
                    timeout=self._timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return [
                            {
                                "number": pr.get("number"),
                                "title": pr.get("title"),
                                "state": pr.get("state"),
                                "user": pr.get("user", {}).get("login"),
                                "created_at": pr.get("created_at"),
                                "draft": pr.get("draft", False),
                                "head_branch": pr.get("head", {}).get("ref"),
                                "base_branch": pr.get("base", {}).get("ref"),
                                "html_url": pr.get("html_url"),
                            }
                            for pr in data
                        ]
                    elif response.status == 404:
                        return None
                    else:
                        logger.error(f"List pulls failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"List pulls error: {e}")
            return None

    async def get_pull(self, owner: str, name: str, number: int) -> Optional[dict]:
        """Get detailed PR information including merge status.

        Returns:
            Dict with PR details or None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/repos/{owner}/{name}/pulls/{number}",
                    headers=self.headers,
                    timeout=self._timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "number": data.get("number"),
                            "title": data.get("title"),
                            "body": data.get("body"),
                            "state": data.get("state"),
                            "user": data.get("user", {}).get("login"),
                            "created_at": data.get("created_at"),
                            "merged_at": data.get("merged_at"),
                            "closed_at": data.get("closed_at"),
                            "draft": data.get("draft", False),
                            "mergeable": data.get("mergeable"),
                            "mergeable_state": data.get("mergeable_state"),
                            "head_branch": data.get("head", {}).get("ref"),
                            "base_branch": data.get("base", {}).get("ref"),
                            "additions": data.get("additions"),
                            "deletions": data.get("deletions"),
                            "changed_files": data.get("changed_files"),
                            "comments": data.get("comments"),
                            "review_comments": data.get("review_comments"),
                            "html_url": data.get("html_url"),
                        }
                    elif response.status == 404:
                        return None
                    else:
                        logger.error(f"Get pull failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Get pull error: {e}")
            return None
