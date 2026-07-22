package commands

import (
	"strings"

	"github.com/bwmarrin/discordgo"
	"github.com/u16-io/FindSenryu4Discord/config"
	"github.com/u16-io/FindSenryu4Discord/pkg/metrics"
)

// HandleHelpCommand handles the /help slash command.
// Shows an ephemeral list of available commands.
func HandleHelpCommand(s *discordgo.Session, i *discordgo.InteractionCreate) {
	metrics.RecordCommandExecuted("help")

	lines := []string{
		"`/mute` — このチャンネルでの川柳検出をミュートします",
		"`/unmute` — このチャンネルでの川柳検出のミュートを解除します",
		"`/rank` — ギルド内で詠んだ回数が多い人のランキングを表示します",
		"`/delete <user>` — 指定ユーザーの川柳を削除します（自分の川柳を削除する場合も自分を指定）",
		"`/channel` — チャンネルタイプ別の川柳検出設定を変更します（管理者専用）",
		"`/doctor` — このチャンネルでBotが正常に動作するか診断します",
		"`/detect on | off | status` — 自分の川柳検出のオン/オフを切り替えます",
		"`/detect ban <user> | unban <user> | list` — 川柳検出の無効化を管理します（管理者専用）",
		"`/admin stats | backup | contact-message | role-set | role-unset | role-show` — Bot管理者向けの管理操作（管理用ギルドかつBot管理者のみ）",
	}

	conf := config.GetConf()
	if conf.Admin.ContactChannelID != "" {
		lines = append(lines, "`/contact` — Bot管理者にお問い合わせを送信します")
	}

	description := strings.Join(lines, "\n") +
		"\n\nメッセージで `詠め` と送ると新しい川柳を生成、`詠むな` と送ると最後に詠んだ人を晒します。"

	embed := &discordgo.MessageEmbed{
		Title:       "コマンド一覧",
		Description: description,
		Color:       0x5865F2,
	}

	s.InteractionRespond(i.Interaction, &discordgo.InteractionResponse{
		Type: discordgo.InteractionResponseChannelMessageWithSource,
		Data: &discordgo.InteractionResponseData{
			Embeds: []*discordgo.MessageEmbed{embed},
			Flags:  discordgo.MessageFlagsEphemeral,
		},
	})
}
