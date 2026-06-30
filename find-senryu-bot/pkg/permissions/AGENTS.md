<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# pkg/permissions

## Purpose
Bot管理者権限（`admin.owner_ids`）の確認ロジックを提供するパッケージです。コマンドハンドラがユーザーのBot管理者権限を検証する際に使用します。

## Key Files

| File | Description |
|------|-------------|
| `permissions.go` | `IsOwner()` / `CheckOwnerPermission()` / `GetAdminGuildID()` |

## For AI Agents

### Working In This Directory
- `IsOwner(userID)` は `config.Admin.OwnerIDs` リストと照合する
- `CheckOwnerPermission()` はIsOwnerの結果をロギング付きで返す便利ラッパー
- ギルドレベルの管理ロール確認は `service.GetGuildAdminRole()` を使用（このパッケージではなく `service/` が担当）

### Common Patterns
- 権限不足の場合は `logger.Warn("Unauthorized admin action attempt")` でログを残す

## Dependencies

### Internal
- `config/` — `admin.owner_ids` / `admin.guild_id` 取得
- `pkg/logger/` — ロギング

<!-- MANUAL: -->
