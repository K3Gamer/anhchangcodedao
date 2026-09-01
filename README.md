# 🤖 Codi

Discord Bot quản trị & hỗ trợ cộng đồng lập trình **"Code vì Đam Mê"**, viết bằng **Python 3.13+** và **discord.py 2.x**.

## ✨ Tính năng nổi bật

| Nhóm | Chi tiết |
| --- | --- |
| 🛡️ **AutoMod** | Anti Spam, Anti Mention, Anti Link, Anti Invite, Anti Scam, Anti Emoji, Anti Caps, Anti Bad Words, Anti Flood, Auto Slowmode — bật/tắt & whitelist từng tính năng |
| 🚨 **AntiNuke** | Giám sát Audit Log, chặn Mass Ban/Kick, xóa kênh/role/emoji/sticker/webhook, tạo kênh/role hàng loạt — tự xử lý (ban/kick/gỡ quyền) |
| 📜 **Logging** | Join/Leave, xóa/sửa tin nhắn, voice, role, nickname, ban/unban, timeout, channel, emoji, sticker... |
| 👮 **Moderation** | clear, lock/unlock, slowmode, kick, ban/unban, timeout, move/moveall, rename, role, announce |
| ⚠️ **Warn** | warn / unwarn / warnings kèm lưu JSON file |
| 📊 **Leveling** | Tự động cộng XP khi nhắn tin, thẻ `/rank` ảnh, bảng xếp hạng `/leaderboard` hình ảnh gradient hiện đại |
| 🎫 **Ticket Góp ý** | Persistent buttons, transcript HTML, tự động đóng & gửi transcript |
| ℹ️ **Info** | serverinfo, userinfo, botinfo, membercount, roleinfo, channelinfo, emojiinfo, avatar, banner, uptime |
| 🎨 **Tiện ích** | poll, embed, remind, help tương tác (Select Menu) |
| ⚙️ **Cấu hình** | prefix, mod log channel, logging channel, settings |

Toàn bộ **Buttons / Views / Modals / Select Menus** đều là **Persistent** — hoạt động tốt kể cả khi bot restart.

## 🚀 Cài đặt & chạy

### 1. Yêu cầu

- Python **3.13+** (khuyến nghị) hoặc 3.10+
- Không cần MongoDB — dữ liệu lưu dạng **JSON file** trong thư mục `data/`

### 2. Cài thư viện

```bash
cd Codi
pip install -r requirements.txt
```

### 3. Cấu hình

```bash
copy .env.example .env
```

Sửa file `.env`:

```env
DISCORD_TOKEN=token_cua_bot
```

> ⚠️ Nhớ bật **MESSAGE CONTENT INTENT** trong Discord Developer Portal → Bot → Privileged Gateway Intents
> (và bật `SERVER MEMBERS INTENT` để đếm thành viên & log join/leave chính xác).

### 4. Chạy bot

```bash
python bot.py
```

### Hoạt động trên GitHub Actions

> ⚠️ **Lưu ý quan trọng:** GitHub Actions **không phải** giải pháp host 24/7 hoàn hảo:
> - Free runner bị **giới hạn tối đa ~6h/job** — bot sẽ tự khởi động lại mỗi 6h qua cron.
> - Runner bị **hủy sau mỗi job** — mọi file tạm đều mất.
> - Gói free của repo **private** chỉ có giới hạn phút chạy/tháng; chạy 24/7 sẽ tiêu tốn rất nhiều phút.

Workflow `.github/workflows/bot.yml` tự động:
1. Checkout code, cài dependencies.
2. **Pull dữ liệu** từ nhánh `data` trên GitHub (nơi lưu XP/config/warn/ticket).
3. Chạy bot, đồng thời **đẩy dữ liệu lên nhánh `data` mỗi 5 phút** để không mất XP.

**Cách bật:**
1. Vào repo → **Settings → Secrets and variables → Actions** → thêm secret `DISCORD_TOKEN` = token bot.
2. Vào tab **Actions** → chọn workflow **Host Bot** → **Run workflow** để chạy lần đầu.
3. Sau đó bot tự chạy lại mỗi 6h nhờ cron.

Nhánh `data` được tạo/tự động đẩy bởi các script trong `.github/scripts/`:
- `pull_data.sh` — kéo dữ liệu hiện có về `./data/` lúc khởi động.
- `push_data.sh` — đẩy `./data/` lên nhánh `data` (force-push snapshot, giữ nhánh gọn nhẹ).

### 5. Khởi tạo hệ thống trên server

- `/gopyticketsetup` — tạo panel Ticket Góp ý
- `/setmodlog #kênh` — kênh log quản trị
- `/setlogging #kênh` — kênh log sự kiện
- `/settings` — xem cấu hình server

## 📂 Cấu trúc dự án

```
Codi/
├── bot.py                 # Điểm khởi động
├── requirements.txt
├── .env.example
├── core/                  # Lõi bot: cấu hình, DB, logging, lỗi, quyền
├── database/              # Lớp lưu trữ JSON + cache (Guild Config, Warn, Ticket)
├── utils/                 # Tiện ích: embed, hằng số, thời gian, cache
├── views/                 # Persistent Views (Confirm, Ticket, Help)
├── services/              # Nghiệp vụ: Ticket, Transcript
├── cogs/                  # Nhóm lệnh & sự kiện
├── data/                  # Dữ liệu bot (guild_configs.json, warns.json, tickets.json, transcripts/)
└── logs/                  # File log bot
```

## 🛠 Bảo trì

- Thêm lệnh: tạo method mới trong cog tương ứng (hoặc cog mới rồi khai báo trong `core/bot.py`).
- Mọi Embed được tạo qua `bot.embeds` (đồng nhất Blurple + Thumbnail + Footer + Timestamp).
- Lỗi không mong muốn được log ra console, file `logs/bot.log` và gửi vào kênh log (nếu đã cấu hình).

## 📝 Ghi chú

- AntiNuke không bao giờ xử lý **chủ server** và **bản thân bot**; nhớ thêm role Staff/Admin vào whitelist nếu cần.
- Lời nhắc `/remind` không tồn tại qua lần restart bot (đây là đặc thù của tính năng nhắc hẹn).
