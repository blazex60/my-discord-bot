"use strict";
/**
 * Discord VC 議事録自動作成ボット
 * discord.js + @discordjs/voice による録音 → Python パイプライン呼び出し
 */

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const {
  Client,
  GatewayIntentBits,
  REST,
  Routes,
  SnowflakeUtil,
} = require("discord.js");
const {
  joinVoiceChannel,
  VoiceConnectionStatus,
  EndBehaviorType,
  entersState,
} = require("@discordjs/voice");
const prism = require("prism-media");
const yaml = require("js-yaml");
require("dotenv").config();

// --- 設定読み込み ---
const config = yaml.load(fs.readFileSync("config.yaml", "utf8"));
const DISCORD_TOKEN = process.env.DISCORD_TOKEN;
if (!DISCORD_TOKEN) {
  throw new Error(
    "DISCORD_TOKEN が設定されていません。.env ファイルに記載するか環境変数を設定してください。"
  );
}

const TMP_DIR = config.storage.tmp_dir;
const OUTPUT_DIR = config.storage.output_dir;
const MAX_RECORDING_HOURS = config.storage.max_recording_hours ?? 3;
fs.mkdirSync(path.join(TMP_DIR, "recordings"), { recursive: true });
fs.mkdirSync(path.join(TMP_DIR, "transcripts"), { recursive: true });
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

// --- Discord クライアント ---
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildVoiceStates,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
});

// --- セッション管理 ---
// guildId (string) → { sessionId, connection, startTime, startSnowflake, textChannelId, perUserBuffers, timeoutHandle }
const sessions = new Map();

// --- スラッシュコマンド定義 ---
const COMMANDS = [
  {
    name: "record_start",
    description: "VC に参加して録音を開始する",
  },
  {
    name: "record_stop",
    description: "録音を停止してバッチ処理（ASR → 議事録生成）を開始する",
  },
  {
    name: "transcribe_only",
    description: "既存の WAV ファイルから ASR・要約のみ再実行する",
  },
];

// ============================================================
// ユーティリティ
// ============================================================

/** PCM バッファを 48kHz / 2ch / 16-bit WAV ファイルとして書き出す */
function writePcmToWav(pcmBuffer, filePath) {
  const numChannels = 2;
  const sampleRate = 48000;
  const bitDepth = 16;
  const byteRate = (sampleRate * numChannels * bitDepth) / 8;
  const blockAlign = (numChannels * bitDepth) / 8;
  const dataSize = pcmBuffer.length;

  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + dataSize, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16); // fmt chunk size
  header.writeUInt16LE(1, 20); // PCM
  header.writeUInt16LE(numChannels, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(byteRate, 28);
  header.writeUInt16LE(blockAlign, 32);
  header.writeUInt16LE(bitDepth, 34);
  header.write("data", 36);
  header.writeUInt32LE(dataSize, 40);

  fs.writeFileSync(filePath, Buffer.concat([header, pcmBuffer]));
}

/** YYYY-MM-DD HH:MM:SS 形式の文字列を返す（UTC） */
function formatTimestamp(date) {
  return date.toISOString().replace("T", " ").slice(0, 19);
}

/** Python スクリプトをサブプロセスで実行し、終了コードを返す */
function runPython(args) {
  return new Promise((resolve, reject) => {
    const proc = spawn("uv", ["run", "python", ...args], { stdio: "inherit" });
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code === 0) resolve();
      else reject(code);
    });
  });
}

/** Discord チャンネルの message ID から Snowflake を生成する（開始時刻直前） */
function timestampToSnowflake(ms) {
  // Discord Snowflake: (ms - DISCORD_EPOCH) << 22
  return SnowflakeUtil.generate({ timestamp: ms - 1 }).toString();
}

// ============================================================
// 録音処理
// ============================================================

/** VC に接続してセッションを開始する */
function startRecording(guildId, sessionId, voiceChannel, textChannelId) {
  const recordingsDir = path.join(TMP_DIR, "recordings");

  const connection = joinVoiceChannel({
    channelId: voiceChannel.id,
    guildId,
    adapterCreator: voiceChannel.guild.voiceAdapterCreator,
    selfDeaf: false,
    selfMute: true,
    selfVideo: false,
  });

  // perUserBuffers: userId → Buffer[]
  const perUserBuffers = new Map();

  const receiver = connection.receiver;

  // VC に参加しているメンバーの録音を開始する
  // 新規参加者は on("speaking") でサブスクライブ
  receiver.speaking.on("start", (userId) => {
    if (perUserBuffers.has(userId)) return; // すでに録音中
    perUserBuffers.set(userId, []);

    const audioStream = receiver.subscribe(userId, {
      end: { behavior: EndBehaviorType.Manual },
    });

    const decoder = new prism.opus.Decoder({
      rate: 48000,
      channels: 2,
      frameSize: 960,
    });

    // エラーハンドリング: 暗号化関連エラーを無視して録音を継続
    audioStream.on("error", (err) => {
      console.warn(`Audio stream error for user ${userId}:`, err.message);
    });

    decoder.on("error", (err) => {
      console.warn(`Decoder error for user ${userId}:`, err.message);
    });

    audioStream.pipe(decoder).on("data", (chunk) => {
      const buf = perUserBuffers.get(userId);
      if (buf) buf.push(chunk);
    });
  });

  const startTime = Date.now();
  const startSnowflake = timestampToSnowflake(startTime);

  sessions.set(guildId, {
    sessionId,
    connection,
    startTime,
    startSnowflake,
    textChannelId,
    perUserBuffers,
    timeoutHandle: null,
  });

  return { connection, startSnowflake };
}

/** 録音を停止し、WAV ファイルを保存する */
async function stopRecording(guildId) {
  const session = sessions.get(guildId);
  if (!session) throw new Error("セッションが存在しません");

  const { sessionId, connection, perUserBuffers, timeoutHandle } = session;

  // タイムアウトキャンセル
  if (timeoutHandle) clearTimeout(timeoutHandle);

  // WAV ファイル書き出し
  const recordingsDir = path.join(TMP_DIR, "recordings");
  const savedFiles = [];

  for (const [userId, chunks] of perUserBuffers.entries()) {
    if (chunks.length === 0) continue;
    const pcm = Buffer.concat(chunks);
    const filePath = path.join(recordingsDir, `${sessionId}_${userId}.wav`);
    writePcmToWav(pcm, filePath);
    savedFiles.push(filePath);
  }

  // VC 切断
  connection.destroy();
  sessions.delete(guildId);

  return savedFiles;
}

/** チャットログを収集して保存する */
async function collectChatLog(channel, startSnowflake, sessionId) {
  const transcriptsDir = path.join(TMP_DIR, "transcripts");
  const lines = [];

  let lastId = startSnowflake;
  while (true) {
    const fetched = await channel.messages.fetch({
      after: lastId,
      limit: 100,
    });
    if (fetched.size === 0) break;

    // Snowflake 昇順にソート
    const sorted = [...fetched.values()].sort((a, b) =>
      a.id < b.id ? -1 : 1
    );
    for (const msg of sorted) {
      if (msg.author.bot) continue;
      if (!msg.content.trim()) continue;
      const ts = formatTimestamp(msg.createdAt);
      lines.push(`[${ts}] ${msg.member?.displayName ?? msg.author.username}: ${msg.content}`);
    }

    lastId = sorted[sorted.length - 1].id;
    if (fetched.size < 100) break;
  }

  if (lines.length === 0) return null;

  const chatPath = path.join(transcriptsDir, `${sessionId}_chat.txt`);
  fs.writeFileSync(chatPath, lines.join("\n"), "utf8");
  return { chatPath, count: lines.length };
}

/** VC チャンネルメンバーのメタデータを保存する（user_id → display_name） */
function saveMetadata(voiceChannel, sessionId) {
  const transcriptsDir = path.join(TMP_DIR, "transcripts");
  const meta = {};
  for (const [userId, member] of voiceChannel.members) {
    if (member.user.bot) continue;
    meta[userId] = member.displayName;
  }
  const metaPath = path.join(transcriptsDir, `${sessionId}_meta.json`);
  fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2), "utf8");
}

// ============================================================
// バッチパイプライン
// ============================================================

async function runBatchPipeline(interaction, sessionId, startTime) {
  const recordingsDir = path.join(TMP_DIR, "recordings");
  const wavFiles = fs
    .readdirSync(recordingsDir)
    .filter((f) => f.startsWith(sessionId) && f.endsWith(".wav"));
  const totalWavs = Math.max(wavFiles.length, 1);

  // インタラクショントークンは15分で有効期限切れになるため、
  // 期限切れの場合はチャンネルに直接メッセージを送信する
  let tokenExpired = false;
  const edit = async (content) => {
    if (tokenExpired) {
      // トークンが既に期限切れの場合はチャンネルに直接送信
      return;
    }
    try {
      await interaction.editReply({ content });
    } catch (err) {
      if (err.code === 50027 || err.code === 10015) {
        // 50027: Invalid Webhook Token, 10015: Unknown Webhook
        console.warn("⚠️ インタラクショントークンが期限切れです。チャンネルに直接送信します。");
        tokenExpired = true;
      } else {
        throw err;
      }
    }
  };

  // フェーズ2: ASR
  await edit(`🎤 音声認識処理中 (Whisper)... 0/${totalWavs} ファイル`);
  try {
    await runPython(["pipeline/transcriber.py", sessionId]);
  } catch (code) {
    const errorMsg = `❌ エラーが発生しました: ASR 処理失敗 (終了コード: ${code})`;
    if (tokenExpired) {
      await interaction.channel.send({ content: errorMsg });
    } else {
      await edit(errorMsg);
    }
    return;
  }
  await edit(`🎤 音声認識処理中 (Whisper)... ${totalWavs}/${totalWavs} ファイル`);

  // フェーズ3: LLM 要約
  await edit("🧠 議事録生成中 (LLM)... チャンク 0/? を処理中");
  let llmExitCode = 0;
  try {
    await runPython(["pipeline/summarizer.py", sessionId]);
  } catch (code) {
    llmExitCode = code;
  }

  if (llmExitCode !== 0) {
    const partialPath = path.join(TMP_DIR, `partial_${sessionId}.txt`);
    if (llmExitCode === 2 && fs.existsSync(partialPath)) {
      const errorMsg = "❌ エラーが発生しました: VRAM 不足により LLM 処理を中断しました。生成済みのチャンク要約を送信します。";
      if (tokenExpired) {
        await interaction.channel.send({
          content: errorMsg,
          files: [{ attachment: partialPath, name: `partial_${sessionId}.txt` }],
        });
      } else {
        await edit(errorMsg);
        await interaction.channel.send({
          files: [{ attachment: partialPath, name: `partial_${sessionId}.txt` }],
        });
      }
    } else {
      const errorMsg = `❌ エラーが発生しました: LLM 処理失敗 (終了コード: ${llmExitCode})`;
      if (tokenExpired) {
        await interaction.channel.send({ content: errorMsg });
      } else {
        await edit(errorMsg);
      }
    }
    return;
  }

  // フェーズ4: 結果送信
  const elapsed = ((Date.now() - startTime) / 60000).toFixed(1);
  const outputPath = path.join(OUTPUT_DIR, `minutes_${sessionId}.md`);

  if (fs.existsSync(outputPath)) {
    const successMsg = `✅ 議事録を生成しました（所要時間: ${elapsed} 分）`;
    
    if (tokenExpired) {
      // トークンが期限切れの場合はチャンネルに直接送信
      await interaction.channel.send({
        content: successMsg,
        files: [{ attachment: outputPath, name: `minutes_${sessionId}.md` }],
      });
    } else {
      // トークンが有効な場合は通常通りeditReplyを使用
      await edit(successMsg);
      await interaction.channel.send({
        files: [{ attachment: outputPath, name: `minutes_${sessionId}.md` }],
      });
    }
  } else {
    const errorMsg = "❌ エラーが発生しました: 出力ファイルが見つかりません";
    if (tokenExpired) {
      await interaction.channel.send({ content: errorMsg });
    } else {
      await edit(errorMsg);
    }
    return;
  }

  // 一時ファイル削除
  for (const f of fs.readdirSync(recordingsDir)) {
    if (f.startsWith(sessionId)) fs.unlinkSync(path.join(recordingsDir, f));
  }
  const transcriptsDir = path.join(TMP_DIR, "transcripts");
  for (const f of fs.readdirSync(transcriptsDir)) {
    if (f.startsWith(sessionId)) fs.unlinkSync(path.join(transcriptsDir, f));
  }
}

// ============================================================
// イベントハンドラ
// ============================================================

client.once("clientReady", async () => {
  console.log(`Bot 起動完了: ${client.user.tag}`);

  // スラッシュコマンドをグローバル登録
  const rest = new REST().setToken(DISCORD_TOKEN);
  await rest.put(Routes.applicationCommands(client.user.id), {
    body: COMMANDS,
  });
  console.log("スラッシュコマンド登録完了");
});

client.on("interactionCreate", async (interaction) => {
  if (!interaction.isChatInputCommand()) return;

  const { commandName, guild, member } = interaction;
  const guildId = guild.id;

  // ============================================================
  if (commandName === "record_start") {
    if (sessions.has(guildId)) {
      await interaction.reply(
        "すでに録音セッションが進行中です。`/record_stop` で停止してください。"
      );
      return;
    }

    // コマンド実行者の VC チャンネルを取得
    const voiceChannel = member.voice?.channel;
    if (!voiceChannel) {
      await interaction.reply("VC チャンネルに参加してから実行してください。");
      return;
    }

    await interaction.deferReply();

    const _now = new Date();
    const _pad = (n) => String(n).padStart(2, "0");
    const sessionId = `${_now.getFullYear()}${_pad(_now.getMonth() + 1)}${_pad(_now.getDate())}_${_pad(_now.getHours())}${_pad(_now.getMinutes())}${_pad(_now.getSeconds())}`;

    saveMetadata(voiceChannel, sessionId);

    const { connection, startSnowflake } = startRecording(
      guildId,
      sessionId,
      voiceChannel,
      interaction.channelId
    );

    // 接続確立を待つ
    try {
      await entersState(connection, VoiceConnectionStatus.Ready, 30_000);
    } catch {
      connection.destroy();
      sessions.delete(guildId);
      await interaction.editReply(
        "❌ VC 接続に失敗しました。30 秒以内に接続が確立できませんでした。"
      );
      return;
    }

    // 最大録音時間タイムアウト
    const session = sessions.get(guildId);
    session.timeoutHandle = setTimeout(async () => {
      if (!sessions.has(guildId)) return;
      await interaction.editReply(
        `⚠️ 最大録音時間 (${MAX_RECORDING_HOURS} 時間) に達したため自動停止しました。バッチ処理を開始します...`
      );
      const savedFiles = await stopRecording(guildId);
      const chatResult = await collectChatLog(
        interaction.channel,
        startSnowflake,
        sessionId
      );
      await interaction.editReply(
        `⏳ バッチ処理を開始しました...（チャットログ: ${chatResult?.count ?? 0} 件）`
      );
      await runBatchPipeline(interaction, sessionId, session.startTime);
    }, MAX_RECORDING_HOURS * 3600 * 1000);

    await interaction.editReply(
      `🔴 録音中... (セッション: \`${sessionId}\`)\nこのチャンネルのチャットも議事録に反映します。`
    );
  }

  // ============================================================
  if (commandName === "record_stop") {
    const session = sessions.get(guildId);
    if (!session) {
      await interaction.reply("録音中のセッションがありません。");
      return;
    }

    await interaction.deferReply();

    const { sessionId, startTime, startSnowflake, textChannelId } = session;

    // チャットログ収集
    await interaction.editReply("⏳ チャットログを収集しています...");
    const textChannel = guild.channels.cache.get(textChannelId);
    let chatCount = 0;
    try {
      const chatResult = await collectChatLog(
        textChannel,
        startSnowflake,
        sessionId
      );
      chatCount = chatResult?.count ?? 0;
    } catch (e) {
      console.error("チャットログ収集エラー:", e);
    }

    // 録音停止・WAV 保存
    let savedFiles = [];
    try {
      savedFiles = await stopRecording(guildId);
    } catch (e) {
      await interaction.editReply(
        `❌ エラーが発生しました: 録音停止失敗 (${e})\nWAV ファイルは保持されています。\`/transcribe_only\` で再開できます。`
      );
      return;
    }

    if (savedFiles.length === 0) {
      await interaction.editReply(
        "⚠️ WAV ファイルが空です（誰も発言しませんでした）。処理をスキップします。"
      );
      return;
    }

    await interaction.editReply(
      `⏳ バッチ処理を開始しました...（WAV: ${savedFiles.length} ファイル、チャットログ: ${chatCount} 件）`
    );
    await runBatchPipeline(interaction, sessionId, startTime);
  }

  // ============================================================
  if (commandName === "transcribe_only") {
    const recordingsDir = path.join(TMP_DIR, "recordings");
    const wavFiles = fs
      .readdirSync(recordingsDir)
      .filter((f) => f.endsWith(".wav"))
      .sort();

    if (wavFiles.length === 0) {
      await interaction.reply("再処理する WAV ファイルが見つかりません。");
      return;
    }

    // 最新ファイルのステムからセッション ID を推定
    const stem = path.basename(wavFiles[wavFiles.length - 1], ".wav");
    const parts = stem.split("_");
    const sessionId =
      parts.length >= 2 ? `${parts[0]}_${parts[1]}` : stem;

    await interaction.deferReply();
    await interaction.editReply("⏳ バッチ処理を開始しました...");
    await runBatchPipeline(interaction, sessionId, Date.now());
  }
});

client.login(DISCORD_TOKEN);
