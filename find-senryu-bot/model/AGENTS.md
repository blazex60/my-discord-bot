<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# model

## Purpose
GORMで使用するデータベースモデル（構造体）を定義するパッケージです。ビジネスロジックは含まず、純粋なデータ構造の定義のみを行います。

## Key Files

| File | Description |
|------|-------------|
| `senryu.go` | 全モデル定義: `Senryu`, `MutedChannel`, `GuildChannelTypeSetting`, `DetectionOptOut`, `Metadata` |

## For AI Agents

### Working In This Directory
- モデル変更時は必ず `db/migrations/` にSQLマイグレーションファイルを追加する
- `Senryu.Kamigo/Nakasichi/Simogo` は暗号化が有効な場合、base64エンコードされた暗号文が格納される
- `DetectionOptOut.SetBy` は `'self'`（ユーザー自身）または `'admin'`（管理者によるban）を区別する
- `Metadata` はKey-Valueストアとして暗号化フラグやギルド管理ロールIDなど汎用的な設定保存に使用される

### Common Patterns
- GORMタグで主キー・インデックス・カラム名を明示指定
- `Spoiler *bool`（ポインタ）は `not null` 制約を保ちつつゼロ値を区別するため

## Dependencies

### External
- `github.com/jinzhu/gorm` — ORM（タグ定義のみ、クエリは `db/` と `service/` で実施）

<!-- MANUAL: -->
