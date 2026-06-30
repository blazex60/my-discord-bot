package service

import (
	"fmt"

	"github.com/cockroachdb/errors"
	"github.com/jinzhu/gorm"
	"github.com/u16-io/FindSenryu4Discord/db"
	"github.com/u16-io/FindSenryu4Discord/model"
	"github.com/u16-io/FindSenryu4Discord/pkg/logger"
	"github.com/u16-io/FindSenryu4Discord/pkg/metrics"
)

const metadataKeyAdminRolePrefix = "admin_role:"

func adminRoleKey(guildID string) string {
	return fmt.Sprintf("%s%s", metadataKeyAdminRolePrefix, guildID)
}

// GetGuildAdminRole returns the configured admin role ID for a guild.
// Returns empty string if not configured.
func GetGuildAdminRole(guildID string) (string, error) {
	metrics.RecordDatabaseOperation("get_guild_admin_role")
	var meta model.Metadata
	err := db.DB.Where("key = ?", adminRoleKey(guildID)).First(&meta).Error
	if err != nil {
		if gorm.IsRecordNotFoundError(err) {
			return "", nil
		}
		metrics.RecordError("database")
		logger.Error("Failed to get guild admin role", "error", err, "guild_id", guildID)
		return "", errors.Wrap(err, "failed to get guild admin role")
	}
	return meta.Value, nil
}

// SetGuildAdminRole sets the admin role ID for a guild.
func SetGuildAdminRole(guildID, roleID string) error {
	metrics.RecordDatabaseOperation("set_guild_admin_role")
	key := adminRoleKey(guildID)
	meta := model.Metadata{Key: key, Value: roleID}
	if err := db.DB.Where("key = ?", key).Assign(model.Metadata{Value: roleID}).FirstOrCreate(&meta).Error; err != nil {
		metrics.RecordError("database")
		logger.Error("Failed to set guild admin role", "error", err, "guild_id", guildID)
		return errors.Wrap(err, "failed to set guild admin role")
	}
	return nil
}

// ClearGuildAdminRole removes the admin role configuration for a guild.
// Returns the number of rows deleted.
func ClearGuildAdminRole(guildID string) (int64, error) {
	metrics.RecordDatabaseOperation("clear_guild_admin_role")
	result := db.DB.Where("key = ?", adminRoleKey(guildID)).Delete(&model.Metadata{})
	if result.Error != nil {
		metrics.RecordError("database")
		logger.Error("Failed to clear guild admin role", "error", result.Error, "guild_id", guildID)
		return 0, errors.Wrap(result.Error, "failed to clear guild admin role")
	}
	return result.RowsAffected, nil
}
