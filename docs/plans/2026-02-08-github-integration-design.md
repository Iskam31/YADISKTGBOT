# GitHub Integration Module Design

## Overview
Add GitHub integration to the Telegram bot: connect via PAT, manage repositories, create/list/close issues, view PRs.

## Architecture
- Module: `modules/github/` following existing Yandex module pattern
- Auth: Personal Access Token (user creates on github.com, sends to bot)
- Notifications: MVP - no auto-notifications, only on-demand via commands
- UI: Button in main menu + inline submenus + slash commands as shortcuts

## Models
- GitHubToken: user_id (PK), encrypted_token, github_username, created_at, is_valid
- GitHubRepo: id (PK), user_id (FK, indexed), owner, name, is_default, added_at
  - Unique constraint on (user_id, owner, name)

## Service (GitHubAPI)
- REST client via aiohttp, base URL https://api.github.com
- Methods: check_token, list_repos, get_repo, list_issues, create_issue, close_issue, get_issue, list_pulls, get_pull
- Auth: Bearer token header, 15s timeout

## FSM States
- GitHubSetup: waiting_for_token
- GitHubIssue: waiting_for_title, waiting_for_body
- GitHubRepoAdd: waiting_for_repo

## Commands
- /github - submenu
- /gh_token - token setup
- /repo add/list/set - repository management
- /issue, /issues, /issue_close - issue management
- /prs, /pr - PR viewing

## UI
- GitHub button added to main ReplyKeyboard (6 buttons, 3x2 grid)
- Inline submenus for navigation within GitHub features
- Pagination for issues/PRs lists

## Testing
- All testing via Docker containers (docker-compose up -d --build)
