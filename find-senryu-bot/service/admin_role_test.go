package service

import (
	"testing"

	"github.com/jinzhu/gorm"
	_ "github.com/mattn/go-sqlite3"
	"github.com/u16-io/FindSenryu4Discord/db"
	"github.com/u16-io/FindSenryu4Discord/model"
)

func setupAdminRoleTestDB(t *testing.T) {
	t.Helper()
	var err error
	db.DB, err = gorm.Open("sqlite3", ":memory:")
	if err != nil {
		t.Fatalf("failed to open test database: %v", err)
	}
	db.DB.AutoMigrate(&model.Metadata{})
	t.Cleanup(func() {
		db.DB.Close()
	})
}

func TestGetGuildAdminRole_NotConfigured(t *testing.T) {
	setupAdminRoleTestDB(t)

	roleID, err := GetGuildAdminRole("guild1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if roleID != "" {
		t.Errorf("expected empty string, got %q", roleID)
	}
}

func TestSetAndGetGuildAdminRole(t *testing.T) {
	setupAdminRoleTestDB(t)

	want := "role123456789"
	if err := SetGuildAdminRole("guild1", want); err != nil {
		t.Fatalf("failed to set role: %v", err)
	}

	got, err := GetGuildAdminRole("guild1")
	if err != nil {
		t.Fatalf("failed to get role: %v", err)
	}
	if got != want {
		t.Errorf("expected %q, got %q", want, got)
	}
}

func TestSetGuildAdminRole_Overwrite(t *testing.T) {
	setupAdminRoleTestDB(t)

	if err := SetGuildAdminRole("guild1", "role_old"); err != nil {
		t.Fatalf("failed to set initial role: %v", err)
	}
	if err := SetGuildAdminRole("guild1", "role_new"); err != nil {
		t.Fatalf("failed to overwrite role: %v", err)
	}

	got, err := GetGuildAdminRole("guild1")
	if err != nil {
		t.Fatalf("failed to get role: %v", err)
	}
	if got != "role_new" {
		t.Errorf("expected %q, got %q", "role_new", got)
	}
}

func TestClearGuildAdminRole(t *testing.T) {
	setupAdminRoleTestDB(t)

	if err := SetGuildAdminRole("guild1", "role123"); err != nil {
		t.Fatalf("failed to set role: %v", err)
	}

	count, err := ClearGuildAdminRole("guild1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if count != 1 {
		t.Errorf("expected 1 row deleted, got %d", count)
	}

	roleID, err := GetGuildAdminRole("guild1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if roleID != "" {
		t.Errorf("expected empty string after clear, got %q", roleID)
	}
}

func TestClearGuildAdminRole_NotConfigured(t *testing.T) {
	setupAdminRoleTestDB(t)

	count, err := ClearGuildAdminRole("guild_none")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if count != 0 {
		t.Errorf("expected 0 rows deleted, got %d", count)
	}
}

func TestGetGuildAdminRole_IsolatedPerGuild(t *testing.T) {
	setupAdminRoleTestDB(t)

	if err := SetGuildAdminRole("guild1", "role_a"); err != nil {
		t.Fatalf("failed to set role for guild1: %v", err)
	}

	roleID, err := GetGuildAdminRole("guild2")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if roleID != "" {
		t.Errorf("guild2 should have no role, got %q", roleID)
	}
}
