package commands

import (
	"strings"

	"github.com/bwmarrin/discordgo"
	"github.com/u16-io/FindSenryu4Discord/config"
	"github.com/u16-io/FindSenryu4Discord/pkg/metrics"
)

// helpDocsURL points to the web page with detailed usage instructions.
const helpDocsURL = "https://senryu-bot.u16.io/help" // TODO: 実URLに差し替え

// HandleHelpCommand handles the /help slash command.
// Shows an ephemeral list of available commands with a link to the detailed web docs.
func HandleHelpCommand(s *discordgo.Session, i *discordgo.InteractionCreate) {
	metrics.RecordCommandExecuted("help")

	lines := []string{
		"`/mute` — このチャンネルでの川柳検出をミュートします",
		"`/unmute` — このチャンネルでの川柳検出のミュートを解除します",
		"`/rank` — ギルド内で詠んだ回数が多い人のランキングを表示します",
		"`/delete [user]` — 自分の川柳を削除します（管理者は他ユーザーも指定可）",
		"`/channel` — チャンネルタイプ別の川柳検出設定を変更します（管理者専用）",
		"`/doctor` — このチャンネルでBotが正常に動作するか診断します",
		"`/detect on | off | status` — 自分の川柳検出のオン/オフを切り替えます",
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
			Components: []discordgo.MessageComponent{
				discordgo.ActionsRow{
					Components: []discordgo.MessageComponent{
						discordgo.Button{
							Label: "詳しい使い方",
							Style: discordgo.LinkButton,
							URL:   helpDocsURL,
						},
					},
				},
			},
			Flags: discordgo.MessageFlagsEphemeral,
		},
	})
}
