# DangNam — mạng xã hội có Vệ sĩ AI chống lừa đảo qua tin nhắn

Mạng xã hội demo (Flask + HTML/CSS/JS thuần): bảng tin, bạn bè, Messenger realtime, gọi thoại / video WebRTC.
Điểm nhấn là **Vệ sĩ đọc tin nhắn** gửi đến người dùng bằng **AI 3 · Đọc vị** (mô hình **TF-IDF + Linear SVM** đã train trong
`ai_training/IDF_SVM/`) và áp dụng **luật 3 lần**. Vệ sĩ **chỉ bảo vệ người nhận**; người gửi không biết mình bị gắn cờ
cho tới lần 3.

| Lần | Người nhận thấy | Tệp .apk |
| --- | --- | --- |
| 1 | Cảnh báo + thẻ giải thích, **tin vẫn hiện**, link bị làm mờ | Phải bấm xác nhận mới tải |
| 2 | Cảnh báo + **che tin** (bấm mới xem), copy STK đếm ngược 60 giây, người giám hộ được báo | **Chặn tải** |
| 3 | **Vệ sĩ tự động chặn** người gửi, báo **cả 2 bên** | — |

Bị chặn nhầm (ví dụ con nhắn mẹ xin tiền gấp)? Hai bên **Khiếu nại gỡ chặn**: chụp ảnh trực tiếp + Mật mã gia đình + xác nhận
nhau. Gỡ chặn xong Vệ sĩ **đếm lại từ lần 1** (vòng lặp): nếu lại lừa đảo 3 lần thì chặn lại.

> Hướng phát triển: thay AI 3 hiện tại (chấm từng tin, train trên SMS) bằng mô hình **nhận diện theo kịch bản** (đọc cả cuộc
> trò chuyện). Adapter đã gửi sẵn 20 tin gần nhất cho mô hình (mục 5).

---

## 1. Cài đặt

```powershell
# 1. Bật MySQL / MariaDB (XAMPP). CSDL mặc định: data_scam
# 2. Cài thư viện
pip install -r requirements.txt
copy .env.example .env                     # rồi sửa SECRET_KEY, ADMIN_PASSWORD...

# 3. Tạo / nâng cấp bảng (Alembic)
python -m flask --app app db upgrade

# 4. Tạo dữ liệu demo + 8 kịch bản
python seed.py                 # hoặc: --reset (xóa và tạo lại)   |   --no-scan (không cho Vệ sĩ quét tin cũ)

# 5. Chạy
python app.py                  # http://127.0.0.1:5000
```

Mô hình TF-IDF + SVM tự nạp khi server khởi động (khoảng 1 giây). Trang quản trị `/admin` (mật khẩu `ADMIN_PASSWORD`) có các tab:
Mô hình AI · Truy vết IP · Yêu cầu truy vết · Độ uy tín. Không cần Internet khi chạy. Nếu AI 3 lỗi thì adapter tự chuyển sang
chế độ dự phòng (mock), app không crash.

## 2. Tài khoản demo (mật khẩu chung `demo123`)

Có nút **“Đăng nhập nhanh tài khoản demo”** ở trang đăng nhập và trang `/demo`.

| Tài khoản | Tên hiển thị | Vai trò |
| --- | --- | --- |
| `balan` | Trần Thị Lan (62 tuổi) | Nạn nhân KB 1, 3, 8 · có Mật mã gia đình, người giám hộ là Thu Hà |
| `thuha` | Nguyễn Thu Hà | Con gái **thật** của Bà Lan |
| `nguyenthuha.2025` | Nguyễn Thu Hà | **Kẻ gian** giả làm Thu Hà (tài khoản mới, cùng tên + ảnh) |
| `ongminh` / `canbo.congan` | Lê Văn Minh / Cán bộ Công an Quận | KB 2: giả công an + APK |
| `evn.cskh` | EVN CSKH | KB 3: giả điện lực + link nhái |
| `tuyendung.online` | Tuyển Dụng Online 24h | KB 4: việc nhẹ lương cao, rải tin cho 20 người |
| `anhtuan` / `huong.dautu` | Phạm Anh Tuấn / Hương Đầu Tư | KB 5: đầu tư tiền ảo “nuôi” 10 ngày |
| `chilinh` / `shipper.ghn` | Đỗ Chi Linh / Shipper Giao Hàng Nhanh | KB 6: giả shipper đòi phí ship |
| `minhanh`, `hoanglong`, `shop.mebong` | Minh Anh, Hoàng Long, Shop Mẹ Bống | KB 7: chứng minh không báo nhầm |
| `minhkhoa`, `thanhtruc`, … | 22 người dùng bình thường | Bạn bè, bài đăng, hội thoại thường ngày |

Mọi STK / SĐT / tên miền trong dữ liệu demo đều **giả**. Kịch bản nằm trong `data/scenarios.json` (sửa tự do).

## 3. Trình diễn

- **`/demo`**: chọn kịch bản rồi bấm **▶ Phát kịch bản**. Máy chủ tự gửi tin nhắn, các bước cách nhau 2–3 giây. Màn hình chia
  3 cột: **kẻ gian | nạn nhân | dây chuyền Vệ sĩ** (Tiền xử lý → AI 3 → Luật 3 lần sáng lần lượt). Công tắc bật/tắt AI 3 của nạn
  nhân để so sánh trước và sau. Nút **↺ Làm mới** dựng lại dữ liệu của kịch bản (gỡ chặn, xóa khiếu nại).
- **`/guardian`**: dòng thời gian realtime (tin nhắn, Hỏi Vệ sĩ, khiếu nại). Mỗi tin có 3 cột Tiền xử lý | AI 3 | Quyết định,
  kèm thời gian xử lý (ms) và chế độ. Thống kê: số tin đã đọc, tin bị gắn cờ, số lần tự chặn, khiếu nại, nhãn từ người dùng.

### 8 kịch bản (chỉ tin nhắn)

| # | Kịch bản | Điều xảy ra |
| --- | --- | --- |
| 1 | Giả con gái xin tiền | Tài khoản mới tên “Nguyễn Thu Hà” (vào hộp Tin nhắn chờ) xin 15 triệu, dặn đừng nói với bố → lần 1 + gợi ý hỏi Mật mã gia đình |
| 2 | Giả công an + `XacMinhCongDan.apk` | Dọa rửa tiền → gửi APK; tin APK là lần 2 → che tin + chặn tải |
| 3 | Giả điện lực + `evn-thanhtoan.xyz` | Dọa cắt điện trong 2h → bị gắn cờ, link bị làm mờ; tin thứ 2 bị che |
| 4 | Việc nhẹ lương cao, rải hàng loạt | Gỡ chữ chèn “v.i.ệ.c n.h.ẹ” trước khi AI 3 đọc; 20 người nhận, mỗi người lần 1; 1 người báo cáo → lưu nhãn train |
| 5 | Đầu tư tiền ảo kéo dài 10 ngày | AI 3 theo dõi pha qua ngữ cảnh: Tiếp cận → Tạo lòng tin → Yêu cầu tiền |
| 6 | Giả shipper đòi phí ship | Đòi chuyển khoản phí ship vào STK lạ → lần 1, nút copy STK có nhắc |
| 7 | Chứng minh không báo nhầm | “ck t 200k tiền trà sữa”, shop quen gửi STK, link YouTube → **tất cả mức 0** |
| 8 | Chặn sau 3 lần + khiếu nại | `thuha` (con thật) nhắn mẹ 3 tin xin tiền gấp → lần 1, lần 2 che tin, lần 3 **tự chặn**, báo 2 bên |

Kết quả cụ thể phụ thuộc mô hình AI 3 đang chọn (trong test dùng AI giả lập: KB 7 luôn mức 0, KB 8 luôn 1 → 2 → 3).

### Demo Khiếu nại gỡ chặn (2 cửa sổ)

1. Phát KB 8 ở `/demo` (hoặc tự nhắn 3 tin lừa đảo) → Bà Lan đã chặn `thuha`.
2. Cửa sổ thường đăng nhập `balan`, cửa sổ ẩn danh đăng nhập `thuha`. Bên nào cũng thấy thanh “⛔ Vệ sĩ đã tự động chặn” và
   nút **Khiếu nại gỡ chặn** (cả trong menu đầu chat và tab Đã chặn). Một bên mở, bên kia nhận thông báo, dùng chung 1 khiếu nại.
3. Mỗi bên bấm **Chụp**: hệ thống ra 1 thao tác ngẫu nhiên (quay trái, há miệng…), đếm 3-2-1 rồi chụp 3 khung cách nhau
   1 giây. Kiểm tra: thấy khuôn mặt trong ≥ 2 khung (OpenCV) · có cử động giữa các khung (chống ảnh tĩnh).
4. Nếu Bà Lan đã đặt **Mật mã gia đình** (Cài đặt), bên bị chặn phải trả lời đúng (tối đa 3 lần).
5. Khi cả 2 đã chụp đạt, mỗi bên xem ảnh của bên kia và bấm “Đúng là người thân của tôi” / “Không phải”.
6. Cả 2 xác nhận → gỡ chặn, bộ đếm về 0. Một bên từ chối / sai mật mã 3 lần / chụp hỏng 3 lần → thất bại, vẫn chặn.
7. **Vòng lặp:** gỡ chặn xong Vệ sĩ theo dõi lại **từ đầu**: lại lừa đảo thì lần 1 → lần 2 → lần 3 **chặn lại**
   (“lần chặn thứ N”), và lại có 3 lượt khiếu nại mới.

Giới hạn: khiếu nại hết hạn sau **24 giờ**, tối đa **3 lần cho mỗi lần bị chặn**, mỗi người chụp tối đa 3 lần. **Ảnh bị xóa khi
khiếu nại kết thúc**. Chặn do Vệ sĩ không gỡ được bằng nút “Bỏ chặn”, chỉ qua khiếu nại.

**Demo qua 2 máy cùng mạng LAN:** trình duyệt chỉ cho dùng camera / micro trên `localhost` hoặc HTTPS. Đặt `HOST=0.0.0.0` và
`SSL_ADHOC=true` trong `.env` (chứng chỉ tự ký), mở `https://<IP-máy-chủ>:5000` rồi chấp nhận cảnh báo chứng chỉ.

## 4. Tính năng chat

| Tính năng | Cách dùng | Ghi chú với Vệ sĩ |
| --- | --- | --- |
| Tin chữ / ảnh / tệp / emoji | Ô soạn tin, 📎, 😊, kéo thả, dán ảnh | AI 3 đọc chữ (cả chú thích ảnh) |
| **Tin nhắn thoại** | 🎤 → nói → ➤ Gửi (tối đa 2 phút) | Vệ sĩ **không** đọc được tin thoại: không tính lần. Người gửi đã bị cảnh báo từ lần 2 thì tin thoại bị che (bấm “Vẫn nghe”); tin thoại từ người lạ có dòng nhắc cẩn thận giọng giả |
| **Trả lời trích dẫn** | Rê chuột vào tin → ↩️ | Trích dẫn tin bị che thì cũng hiện “đã bị che” |
| **Thu hồi** | ⋯ → Thu hồi với mọi người (trong 24 giờ) | Ẩn với cả 2 bên. Tin lừa đảo bị thu hồi **vẫn tính lần**, người nhận vẫn thấy “đã bị Vệ sĩ cảnh báo” |
| **Thả cảm xúc** | 😊 → ❤️ 😂 😮 😢 😡 👍 (bấm lại để gỡ) | Bị chặn thì không thả được |
| **Ghim tin** | ⋯ → Ghim (tối đa 3 tin / cuộc chat) | Thanh ghim đầu khung chat, bấm để nhảy tới tin |
| **Tìm trong hội thoại** | 🔍 ở đầu khung chat | Bấm kết quả để nhảy tới tin (tự tải tin cũ) |
| **Kho ảnh / tệp / link** | 🗂️ ở đầu khung chat | Ảnh bị che hiện “🛡️ Ảnh bị che”, link trong tin bị cảnh báo có dấu ⚠️ |
| Đã nhận / đã xem, đang nhập, Tin nhắn chờ (người lạ), chặn, gọi thoại / video | Như cũ | Cuộc gọi không bị quét |

Ảnh / tệp không kèm chữ cũng giống tin thoại: không tính lần, nhưng bị che (và chặn tải .apk) nếu người gửi đã bị cảnh báo từ lần 2.

## 5. AI 3 · Đọc vị và bộ quyết định

`agents/orchestrator.py` xử lý **mỗi tin nhắn mới** ở chế độ **nền** (background task của Socket.IO): tin tới người nhận ngay,
cảnh báo đến sau vài mili-giây qua sự kiện `guardian:message`.

```
Tin nhắn → Tiền xử lý (agents/agent3_text.py) → AI 3 (agents/agent3_adapter.py) → Luật 3 lần (agents/decision.py)
            chuẩn hóa teencode / chữ chèn,      mô hình + hiệu chỉnh ngữ cảnh,      gắn cờ = AI 3 kết luận lừa đảo
            tìm từ khóa, STK, link, số tiền     kịch bản + pha + giải thích           hoặc rủi ro ≥ 0.6
```

**Một tin bị gắn cờ CHỈ dựa vào AI 3** (`is_scam` hoặc `risk_score ≥ LEVEL2_RISK` = 0.6 trong `config.py`). Mỗi tin gắn cờ tăng
bộ đếm của người gửi trong cuộc chat đó; mức của tin = số lần (tối đa 3). Không còn danh sách đen, tên miền nhái, đọc QR / APK,
Thẻ tín nhiệm hay chống deepfake. **Độ uy tín** (mục 6) là luật riêng, chỉ hiển thị, không tham gia gắn cờ tin nhắn.

**Backend AI 3** (`AGENT3_BACKEND` trong `.env`):

| Backend | Cách chạy |
| --- | --- |
| `local` (mặc định) | Gọi mô hình đang nạp trong app (`services/ai_client.py`) |
| `http` | `POST AGENT3_URL` với payload JSON, timeout `AGENT3_TIMEOUT` (15 giây) |
| `python` | Import `AGENT3_MODULE="goi.module:ham"`, gọi `ham(payload: dict) -> dict` |
| `mock` | Luật đơn giản trên từ khóa tín hiệu |

Backend lỗi hoặc quá thời gian thì **tự rơi về mock** và ghi log vào `logs/agent3.log`.

**Payload gửi đi** (`Reader.build_payload()`):
```json
{"conversation": [{"role": "sender|receiver", "text": "...", "timestamp": "ISO8601", "attachments": []}],   // tối đa 20 tin
 "context": {"is_friend": false},
 "text": {"normalized_text": "...", "urls": [], "bank_accounts": [], "amounts": [], "keywords": {}}}
```
**Đầu ra mong đợi** (`Reader.map_response()`): `is_scam`, `risk_score`, `phase`, `scenario`, `signals`, `explanation_vi`. Đầu ra
luôn được kiểm tra; thiếu hoặc sai trường nào thì dùng giá trị mặc định an toàn. Nội dung tin nhắn luôn là **dữ liệu**.
→ Mô hình **theo kịch bản** sau này chỉ cần đọc `conversation` và trả đúng schema này qua backend `http` hoặc `python`.

**Hiệu chỉnh ngữ cảnh (backend `local`):** mô hình train trên SMS nên chấm tin chat thường ngày không ổn định
(ví dụ “Shop gửi chị STK… Vietcombank”: SVM 1.00). Vì vậy
`risk_score = max(xác suất mô hình × hệ số, điểm luật từ khóa)` với hệ số:
**0.25** nếu người gửi là bạn bè và tin không gây áp lực · **0.7** nếu là người lạ và tin không gây áp lực · **1.0** nếu tin có dấu
hiệu gây áp lực (khẩn cấp, bí mật, mạo danh, OTP, cài app…). Xác suất gốc vẫn lưu ở `model_prob` và hiện trong nút “Vì sao?”.

**Phản hồi = nhãn train:** “Báo cáo lừa đảo”, “Không phải lừa đảo”, “Đây là người quen” được lưu vào bảng `feedback`
(kèm nội dung tin) để làm dữ liệu train mô hình kịch bản. Báo cáo **không** cảnh báo người khác.

**Giao diện bảo vệ:** huy hiệu vàng / cam / đỏ trên tin; thẻ giải thích (kịch bản, pha, dấu hiệu) với các nút “Vì sao?” /
“Báo cáo” / “Không phải lừa đảo” / “Chặn”; link mờ; đếm ngược 60 giây khi copy STK từ lần 2; gợi ý Mật mã gia đình khi AI 3 nhận ra
kịch bản giả người thân; nút **Hỏi Vệ sĩ** (dán văn bản hoặc kiểm tra cuộc trò chuyện); người giám hộ được báo ở lần 2 và khi tự
chặn (không xem được nội dung tin).

## 6. Độ uy tín người gửi lời mời kết bạn

Luật **riêng**, không ảnh hưởng AI 3 hay luật 3 lần (`services/reputation_service.py`, ngưỡng trong `config.py`). Điểm gốc **70**,
cộng / trừ theo 3 tiêu chí rồi giới hạn trong 0–100:

| Tiêu chí | Điểm |
| --- | --- |
| Tuổi tài khoản | < 1 ngày −25 · 1–7 ngày −15 · 7–30 ngày −5 · 30–180 ngày +5 · 180 ngày–1 năm +10 · > 1 năm +20 |
| Bạn chung với người xem | 0 −10 · 1–2 0 · 3–5 +10 · 6–10 +15 · > 10 +20 |
| Số lần đổi tên | 0 +5 · 1 0 · 2 −5 · 3–4 −15 · ≥ 5 −25 |

🟢 **Đáng tin** ≥ 80 · 🟡 **Cân nhắc** 50–79 · 🔴 **Cảnh giác** < 50. Điểm tính theo cặp (vì bạn chung khác nhau với mỗi người xem).

- **Người dùng chỉ thấy huy hiệu màu** ở: thẻ lời mời kết bạn (`/friends`), trang hồ sơ người khác, đầu khung chat với người lạ /
  Tin nhắn chờ. Không thấy điểm số.
- **Quản trị viên** (tab Độ uy tín) thấy điểm và bảng cộng / trừ của từng lời mời kết bạn.

Dữ liệu demo: các tài khoản lừa đảo có lịch sử đổi tên (`old_names` trong `data/scenarios.json`), ví dụ `nguyenthuha.2025`
(1 ngày, 0 bạn chung với Bà Lan, đổi tên 2 lần) → 40 điểm, 🔴.

## 7. Truy vết IP kẻ lừa đảo

1. Mỗi tin nhắn lưu **IP + trình duyệt** của người gửi lúc gửi; mỗi lần đăng nhập ghi `login_logs`. Hai loại này **tự xóa sau
   `IP_RETENTION_DAYS` ngày** (mặc định 30).
2. Khi Vệ sĩ **tự động chặn (lần 3)** → tạo hồ sơ `scam_traces` (giữ lâu dài): IP các tin bị gắn cờ, IP đăng nhập gần nhất,
   **vị trí gần đúng** (quốc gia / tỉnh-thành / nhà mạng, không bao giờ tới địa chỉ cụ thể).
3. Định vị (`services/ip_geo.py`), theo thứ tự: IP demo (`demo_ip_geo` trong `scenarios.json`) → IP nội bộ (“Mạng nội bộ /
   localhost”) → file `.mmdb` offline (`GEOIP_DB_PATH`, ví dụ DB-IP Lite City hoặc MaxMind GeoLite2-City) → ip-api.com
   (chỉ khi `GEOIP_ONLINE=true`, mặc định **tắt**) → “Không xác định”. Lỗi định vị không bao giờ làm hỏng luồng chat.
4. **Chỉ quản trị viên** xem IP (tab Truy vết IP, lọc theo tài khoản / IP, **xuất CSV** để nộp cơ quan chức năng).
5. **Nạn nhân** (người được Vệ sĩ chặn kẻ gian giúp) bấm **🔎 Yêu cầu thông tin truy vết** ở thanh “⛔ Vệ sĩ đã tự động chặn” hoặc
   tab Đã chặn, ghi lý do → quản trị viên **Duyệt / Từ chối** (tab Yêu cầu truy vết) → nạn nhân nhận thông báo, xem IP + vị trí
   gần đúng của **vụ liên quan tới mình** ở `/trace-requests`. Bị từ chối thì gửi lại được.

Chạy sau proxy (nginx / ngrok): đặt `TRUST_PROXY=true` để lấy IP thật từ `X-Forwarded-For`; chạy trực tiếp thì để `false`
(chống giả mạo IP). Demo trên localhost / LAN: IP là `127.0.0.1` / `192.168.x.x` nên chỉ hiện “Mạng nội bộ”; tài khoản lừa đảo
trong dữ liệu demo dùng **IP demo** thuộc dải dành cho tài liệu (`192.0.2.x`, `198.51.100.x`, `203.0.113.x` — RFC 5737, không phải
IP thật của ai) để trang truy vết có vị trí hiển thị.

## 8. Cấu trúc

```
app.py  config.py  seed.py  .env.example  requirements.txt
agents/      contracts.py  agent3_text.py (tiền xử lý)  agent3_adapter.py (AI 3)  decision.py (luật 3 lần)  orchestrator.py
data/        teencode.json  keywords.json  scenarios.json
db/          database.py  models.py                     migrations/  (Alembic)
routes/      auth (OTP giả lập)  feed  social  friends  chat  call  settings  guardian (+ /demo)  appeal  admin  trace
services/    chat_service  call_service  appeal_service  face_check  social_service  profile_service  notify  guard_view
             demo_service  alert_manager  ai_client (nạp TF-IDF + SVM)  realtime (Socket.IO)
             reputation_service (độ uy tín)  trace_service + ip_geo (truy vết IP)
templates/   static/css (style, app, guard, dashboard, admin)  static/js (main, social, chat, call, call_ring, guard_ui, pipeline,
             guardian, demo, appeal, settings, profile)
ai_training/ dữ liệu (data/) + code train AI 3 (IDF_SVM/)   tests/  (pytest)
```

Bảng chính: `users`, `friend_requests`, `blocks` (`source = user | guardian`), `conversations`, `messages` (+ `reply_to_id`,
`recalled_at`, `pinned_at`), `message_reactions`, `scam_counters`, `guardian_events`, `feedback`, `reports`, `appeals`,
`appeal_captures`, `calls`, `notifications`, `posts`, `login_logs`, `scam_traces`, `trace_requests`…

## 9. Kiểm thử

```powershell
python -m pytest tests -q        # tạo CSDL tạm data_scam_test (chạy migration thật), AI 3 giả lập, xong tự xóa
```

- `test_app.py`: tài khoản, bạn bè, chat, luật 3 lần (che tin, tự chặn), chặn tay, đính kèm, realtime.
- `test_chat_features.py`: trả lời trích dẫn, thu hồi (vẫn tính lần), thả cảm xúc, ghim (tối đa 3, nhảy tới tin), tìm kiếm,
  kho ảnh / tệp / link, tin nhắn thoại + che tin thoại / ảnh khi người gửi đã bị cảnh báo lần 2.
- `test_appeal.py`: khiếu nại (mở từ 2 phía, chụp đạt / không cử động / thiếu mặt, Mật mã gia đình, 2 bên xác nhận, gỡ chặn
  + reset bộ đếm + xóa ảnh, hết hạn, tối đa 3 lần, vòng lặp chặn lại lần 2, lần 3).
- `test_guardian.py`: tiền xử lý, adapter AI 3 (schema, rơi về mock, hiệu chỉnh ngữ cảnh), luật 3 lần chỉ dựa vào AI 3,
  luồng tin nhắn qua API, báo cáo = nhãn train, Hỏi Vệ sĩ, bảng điều khiển.
- `test_scenarios.py`: seed + 8 kịch bản. `test_social.py`, `test_calls.py`: mạng xã hội, gọi điện.
- `test_reputation.py`: các mốc điểm, xếp màu, người dùng chỉ thấy màu, quản trị viên thấy điểm, không ảnh hưởng AI 3.
- `test_ip_trace.py`: lưu IP khi gửi tin / đăng nhập (ẩn với người dùng), hồ sơ truy vết chỉ tạo ở lần 3, định vị (demo / nội bộ /
  online giả lập), yêu cầu truy vết (chỉ nạn nhân, duyệt / từ chối), CSV, tự xóa IP cũ.

## 10. Bảo mật và quyền riêng tư

- CSRF trên mọi form / API ghi; Jinja tự escape; JS chỉ dựng DOM bằng `textContent`.
- File upload: giới hạn kích thước và loại, lưu với tên ngẫu nhiên. Tệp **APK được lưu với đuôi `.bin`, không bao giờ mở hay
  thực thi**, luôn tải về dạng `application/octet-stream`.
- Cuộc gọi: âm thanh / hình ảnh đi thẳng giữa 2 trình duyệt (WebRTC), máy chủ không nhận và không lưu.
- Tin thu hồi: ẩn với cả 2 bên, nội dung vẫn giữ trong nhật ký Vệ sĩ ở máy chủ (để bằng chứng lừa đảo không bị xóa).
- Ảnh khiếu nại lưu tạm ở `uploads/appeals/<id>/`, chỉ 2 người trong khiếu nại xem được (sau khi cả 2 đã chụp đạt) và bị
  xóa khi khiếu nại kết thúc.
- Mật mã gia đình được lưu dưới dạng hash. Số CCCD khi xác minh danh tính giả lập không được lưu.
- Trang `/guardian` và `/demo` cho mọi người đã đăng nhập xem (theo yêu cầu); các trang này hiện nội dung tin nhắn.
- **IP / vị trí** chỉ hiện ở `/admin`; người dùng không bao giờ thấy IP (kể cả của chính mình), trừ nạn nhân được duyệt yêu cầu
  truy vết (chỉ thấy vụ của mình, không thấy trình duyệt). IP tin nhắn và nhật ký đăng nhập tự xóa sau `IP_RETENTION_DAYS` ngày.
  Định vị online (ip-api.com) mặc định tắt vì gửi IP ra dịch vụ bên ngoài.
- **Điểm uy tín** chỉ quản trị viên thấy; người dùng chỉ thấy màu.
- Chạy bằng server phát triển (Werkzeug + Socket.IO chế độ threading), đủ cho demo; triển khai thật cần WSGI server riêng.
