package commands

import (
	"testing"

	"github.com/bwmarrin/discordgo"
	"github.com/jinzhu/gorm"
	_ "github.com/mattn/go-sqlite3"
	"github.com/u16-io/FindSenryu4Discord/db"
	"github.com/u16-io/FindSenryu4Discord/model"
	"github.com/u16-io/FindSenryu4Discord/service"
)

func setupAdminCommandTestDB(t *testing.T) {
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

func TestCanManageChannel(t *testing.T) {
	tests := []struct {
		name        string
		interaction *discordgo.InteractionCreate
		want        bool
	}{
		{
			name: "Administratorのみ",
			interaction: &discordgo.InteractionCreate{
				Interaction: &discordgo.Interaction{
					Member: &discordgo.Member{
						Permissions: discordgo.PermissionAdministrator,
					},
				},
			},
			want: true,
		},
		{
			name: "ManageChannelsのみ",
			interaction: &discordgo.InteractionCreate{
				Interaction: &discordgo.Interaction{
					Member: &discordgo.Member{
						Permissions: discordgo.PermissionManageChannels,
					},
				},
			},
			want: true,
		},
		{
			name: "両方の権限あり",
			interaction: &discordgo.InteractionCreate{
				Interaction: &discordgo.Interaction{
					Member: &discordgo.Member{
						Permissions: discordgo.PermissionAdministrator | discordgo.PermissionManageChannels,
					},
				},
			},
			want: true,
		},
		{
			name: "どちらの権限もなし",
			interaction: &discordgo.InteractionCreate{
				Interaction: &discordgo.Interaction{
					Member: &discordgo.Member{
						Permissions: discordgo.PermissionSendMessages,
					},
				},
			},
			want: false,
		},
		{
			name: "権限ゼロ",
			interaction: &discordgo.InteractionCreate{
				Interaction: &discordgo.Interaction{
					Member: &discordgo.Member{
						Permissions: 0,
					},
				},
			},
			want: false,
		},
		{
			name: "MemberがnilのDM",
			interaction: &discordgo.InteractionCreate{
				Interaction: &discordgo.Interaction{
					Member: nil,
				},
			},
			want: false,
		},
		{
			name: "ManageChannels含む複数権限",
			interaction: &discordgo.InteractionCreate{
				Interaction: &discordgo.Interaction{
					Member: &discordgo.Member{
						Permissions: discordgo.PermissionManageChannels | discordgo.PermissionSendMessages | discordgo.PermissionViewChannel,
					},
				},
			},
			want: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := canManageChannel(tt.interaction)
			if got != tt.want {
				t.Errorf("canManageChannel() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestIsServerAdmin(t *testing.T) {
	tests := []struct {
		name        string
		interaction *discordgo.InteractionCreate
		want        bool
	}{
		{
			name: "Administratorあり",
			interaction: &discordgo.InteractionCreate{
				Interaction: &discordgo.Interaction{
					Member: &discordgo.Member{
						Permissions: discordgo.PermissionAdministrator,
					},
				},
			},
			want: true,
		},
		{
			name: "ManageChannelsのみはfalse",
			interaction: &discordgo.InteractionCreate{
				Interaction: &discordgo.Interaction{
					Member: &discordgo.Member{
						Permissions: discordgo.PermissionManageChannels,
					},
				},
			},
			want: false,
		},
		{
			name: "MemberがnilのDM",
			interaction: &discordgo.InteractionCreate{
				Interaction: &discordgo.Interaction{
					Member: nil,
				},
			},
			want: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := isServerAdmin(tt.interaction)
			if got != tt.want {
				t.Errorf("isServerAdmin() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestIsServerAdminOrRole_AdminPermission(t *testing.T) {
	i := &discordgo.InteractionCreate{
		Interaction: &discordgo.Interaction{
			Member: &discordgo.Member{
				Permissions: discordgo.PermissionAdministrator,
			},
		},
	}
	if !isServerAdminOrRole(i) {
		t.Error("expected true for PermissionAdministrator, got false")
	}
}

func TestIsServerAdminOrRole_NoMember(t *testing.T) {
	i := &discordgo.InteractionCreate{
		Interaction: &discordgo.Interaction{Member: nil},
	}
	if isServerAdminOrRole(i) {
		t.Error("expected false for nil Member, got true")
	}
}

func TestIsServerAdminOrRole_DMInteraction(t *testing.T) {
	i := &discordgo.InteractionCreate{
		Interaction: &discordgo.Interaction{
			Member: &discordgo.Member{
				Permissions: 0,
				Roles:       []string{"role123"},
			},
		},
	}
	// GuildID is empty string (DM) — should return false before any DB call
	if isServerAdminOrRole(i) {
		t.Error("expected false for DM interaction (empty GuildID), got true")
	}
}

func TestIsServerAdminOrRole_NoRoleConfigured(t *testing.T) {
	setupAdminCommandTestDB(t)

	i := &discordgo.InteractionCreate{
		Interaction: &discordgo.Interaction{
			GuildID: "guild1",
			Member: &discordgo.Member{
				Permissions: 0,
				Roles:       []string{"role123"},
			},
		},
	}
	// No role configured in DB → falls back to PermissionAdministrator only → false
	if isServerAdminOrRole(i) {
		t.Error("expected false when no role configured and no admin permission, got true")
	}
}

func TestIsServerAdminOrRole_MatchingRole(t *testing.T) {
	setupAdminCommandTestDB(t)

	if err := service.SetGuildAdminRole("guild1", "admin_role_id"); err != nil {
		t.Fatalf("failed to set guild admin role: %v", err)
	}

	i := &discordgo.InteractionCreate{
		Interaction: &discordgo.Interaction{
			GuildID: "guild1",
			Member: &discordgo.Member{
				Permissions: 0,
				Roles:       []string{"admin_role_id"},
			},
		},
	}
	if !isServerAdminOrRole(i) {
		t.Error("expected true for matching guild admin role, got false")
	}
}

func TestIsServerAdminOrRole_MatchingRoleInSlice(t *testing.T) {
	setupAdminCommandTestDB(t)

	if err := service.SetGuildAdminRole("guild2", "target_role"); err != nil {
		t.Fatalf("failed to set guild admin role: %v", err)
	}

	i := &discordgo.InteractionCreate{
		Interaction: &discordgo.Interaction{
			GuildID: "guild2",
			Member: &discordgo.Member{
				Permissions: 0,
				Roles:       []string{"role_a", "role_b", "target_role", "role_c"},
			},
		},
	}
	if !isServerAdminOrRole(i) {
		t.Error("expected true when matching role is in middle of slice, got false")
	}
}

func TestIsServerAdminOrRole_WrongRole(t *testing.T) {
	setupAdminCommandTestDB(t)

	if err := service.SetGuildAdminRole("guild3", "admin_role_id"); err != nil {
		t.Fatalf("failed to set guild admin role: %v", err)
	}

	i := &discordgo.InteractionCreate{
		Interaction: &discordgo.Interaction{
			GuildID: "guild3",
			Member: &discordgo.Member{
				Permissions: 0,
				Roles:       []string{"other_role", "another_role"},
			},
		},
	}
	if isServerAdminOrRole(i) {
		t.Error("expected false when member does not have the configured admin role, got true")
	}
}
