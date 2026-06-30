<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# pkg/crypto

## Purpose
川柳データ（上の句・中の句・下の句）のAES-256-GCM暗号化・復号を提供するパッケージです。暗号化が無効な場合は入力をそのまま返すため、呼び出し側は暗号化の有無を意識せずに使用できます。

## Key Files

| File | Description |
|------|-------------|
| `crypto.go` | `Init()` / `Encrypt()` / `Decrypt()` / `IsEnabled()` / `IsEncrypted()` |
| `crypto_test.go` | 暗号化・復号・エラーケースのテスト |

## For AI Agents

### Working In This Directory
- `Init(hexKey)` は起動時に一度だけ呼び出す（`main.go` と `cmd/migrate/main.go` で実施）
- キーはhexエンコードされた32バイト（64文字）のAES-256キー
- `Encrypt()` は nonce をciphertextの先頭に付加してからbase64エンコードする
- `IsEncrypted(s)` はbase64デコード → AES-GCM復号を試みて判定する（完全な確認ではなくヒューリスティック）
- 暗号化無効時は `Encrypt()` / `Decrypt()` が入力をそのまま返す（透過的）
- キー変更後の既存データ再暗号化は現状未サポート

### Testing Requirements
- `go test ./pkg/crypto/...`

### Common Patterns
- `mu sync.Mutex` で `Init()` の並行呼び出しから `gcm` を保護
- 呼び出し後に `conf.Encryption.Key = ""` でメモリからキーを削除する（`main.go` 参照）

## Dependencies

### External
- 標準ライブラリのみ: `crypto/aes`, `crypto/cipher`, `crypto/rand`, `encoding/base64`, `encoding/hex`
- `github.com/cockroachdb/errors` — エラーラッピング

<!-- MANUAL: -->
