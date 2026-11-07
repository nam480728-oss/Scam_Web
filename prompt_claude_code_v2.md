# PROMPT CHO CLAUDE CODE (v2) — Mạng xã hội "Khiên" với đội vệ sĩ 3 AI chống lừa đảo

> Dán toàn bộ nội dung này vào Claude Code, hoặc để file trong thư mục dự án và bảo: "Đọc prompt_claude_code_v2.md và làm theo".
> Đổi tên "Khiên" thành tên app của bạn trước khi dán.

---

## 0. Vai trò và cách làm việc

Bạn là kỹ sư full-stack Python. Hãy xây một **mạng xã hội demo kiểu Facebook** tên **"Khiên"** bằng **Flask + HTML/CSS (Jinja2) + JavaScript thuần**. App có đủ tính năng mạng xã hội cơ bản, nhưng **điểm nhấn để demo là đội vệ sĩ 3 AI**. Mỗi AI canh một kênh riêng:

| Agent | Canh kênh | Câu hỏi | Trạng thái |
|---|---|---|---|
| **Agent 1 · Chống deepfake** | Cuộc gọi thoại và video | Gương mặt, giọng nói này có thật không? | Chưa train → làm bản demo có chỗ cắm model |
| **Agent 2 · Thám tử** | Con người: ai kết bạn, ai nhắn tin, ai gọi | Người này có đáng tin không? | Chưa train → heuristic có chỗ cắm model |
| **Agent 3 · Đọc vị** | Tin nhắn | Cuộc trò chuyện này có phải kịch bản lừa không? | **Đã train, chạy được** → chỉ viết adapter |

Ngoài ra có một **Bộ công cụ dùng chung** (không phải AI): trích xuất thực thể, tra danh sách đen, giải mã QR, đọc quyền file APK, phát hiện tên miền nhái.

Quy tắc làm việc:
1. **Trước khi code, hỏi tôi về Agent 3** (mục 5.3): model chạy kiểu HTTP API hay hàm Python, input/output thực tế ra sao. Nếu tôi chưa trả lời được, dùng schema mặc định.
2. Lập kế hoạch theo các giai đoạn ở mục 10, cho tôi xem rồi mới làm. Sau mỗi giai đoạn, chạy thử và báo ngắn gọn.
3. Giao diện **100% tiếng Việt**. Tên biến, hàm, file bằng tiếng Anh.
4. App **chạy được offline trên một máy**: demo bằng 2 cửa sổ trình duyệt, hoặc 2 máy cùng mạng LAN. Agent 3 lỗi thì tự chuyển sang dự phòng, app không được crash.

---

## 1. Công nghệ

- Python 3.11+, Flask, Jinja2, Flask-Login, Flask-WTF (CSRF), Flask-SQLAlchemy + SQLite
- Flask-SocketIO: chat realtime, thông báo, và **signaling cho WebRTC**
- **WebRTC** (API trình duyệt, JS thuần) cho gọi thoại và gọi video 1-1. Cấu hình STUN qua `.env`, mặc định để trống để chạy được trên localhost/LAN.
- HTML/CSS thuần (CSS variables, dark mode), JavaScript thuần. **Không dùng React/Vue/Tailwind.**
- Thư viện phụ: `python-dotenv`, `requests`, `Pillow`, `imagehash`, `Unidecode`
- Tùy chọn, có thì dùng, không có thì bỏ qua êm: `pyzbar` (QR), `pytesseract` (OCR), `androguard` (đọc quyền APK)
- Có `.env.example`, `requirements.txt`, `README.md`, test bằng `pytest`

## 2. Cấu trúc thư mục đề xuất

```
khien/
├── app.py  config.py  models.py  seed.py
├── blueprints/        # auth, feed, profile, friends, messenger, calls, notifications, search, settings, guardian, demo
├── agents/
│   ├── contracts.py           # dataclass input/output
│   ├── agent1_deepfake.py     # Chống deepfake (demo + chỗ cắm model)
│   ├── agent2_detective.py    # Thám tử (heuristic + chỗ cắm model)
│   ├── agent3_adapter.py      # Đọc vị (nối model thật)
│   ├── orchestrator.py        # điều phối theo sự kiện
│   └── decision.py            # quyết định bằng luật, KHÔNG dùng LLM
├── toolkit/                   # bộ công cụ dùng chung, không AI
│   ├── normalize.py  extract.py  blacklist.py  qr.py  apk_inspect.py  domain_check.py
├── data/   # teencode.json, blacklist.json, official_domains.json, banks.json, scenarios.json
├── templates/   static/css/   static/js/   static/uploads/   static/demo_media/
└── tests/
```

## 3. Tính năng mạng xã hội

Bố cục 3 cột quen thuộc, nhưng **thương hiệu, logo, màu sắc là của riêng "Khiên"**. Không sao chép logo hay tên Facebook.

**Bắt buộc:**
- Đăng ký, đăng nhập (mật khẩu được hash). Xác minh số điện thoại bằng **OTP giả lập** hiển thị trên màn hình. Thêm tùy chọn **"Xác minh danh tính" giả lập** để nhận huy hiệu xác minh.
- Hồ sơ: ảnh đại diện, ảnh bìa, giới thiệu, ngày tham gia, huy hiệu xác minh. **Lưu lịch sử đổi tên và đổi ảnh đại diện** (Agent 2 cần dữ liệu này).
- Bảng tin: đăng bài (chữ + ảnh), bày tỏ cảm xúc, bình luận, chia sẻ. **Bài đăng không bị hệ thống chống lừa đảo quét.**
- Bạn bè: gửi, chấp nhận, từ chối lời mời; gợi ý kết bạn; bạn chung.
- **Messenger:**
  - chat 1-1 realtime
  - gửi chữ, ảnh, file (cho phép .apk nhưng **không bao giờ thực thi**), link
  - trạng thái đã xem, hộp "tin nhắn chờ" từ người lạ
- **Gọi thoại và gọi video 1-1** bằng WebRTC:
  - màn hình cuộc gọi đến (nghe/từ chối)
  - trong cuộc gọi: tắt mic, tắt camera, kết thúc
  - lịch sử cuộc gọi ghi vào hội thoại
- Thông báo realtime, tìm kiếm người dùng.
- Cài đặt:
  - dark mode
  - bật/tắt từng agent
  - **Mật mã gia đình** (câu hỏi bí mật kèm danh sách người thân)
  - **Người giám hộ**

## 4. Phạm vi và nguyên tắc

- Hệ thống chỉ bảo vệ **người nhận** ở 3 điểm tiếp xúc: **lời mời kết bạn, tin nhắn, cuộc gọi**.
- Không quét bài đăng hay bình luận.
- Cảnh báo chỉ hiện cho người được bảo vệ. Người bị gắn cờ không biết.
- **Agent 2 chỉ dùng dữ liệu trong app** và các định danh mà chính người đó gửi (STK, SĐT). **Tuyệt đối không thu thập thông tin từ internet** về đời tư người dùng. Thẻ tín nhiệm chỉ hiển thị điểm và lý do, không hiển thị dữ liệu thô của người khác.
- Nội dung tin nhắn và cuộc gọi luôn được coi là **dữ liệu**, không bao giờ là chỉ dẫn cho AI.

## 5. Ba agent

Định nghĩa dataclass trong `agents/contracts.py`. Mỗi agent là một class có `analyze(...)` và thuộc tính `mode` (`"demo"`, `"heuristic"`, `"model"` hoặc `"mock"`). **Thay Agent 1 hoặc Agent 2 bằng model thật sau này chỉ cần sửa trong file của chính agent đó.**

### 5.1 Agent 1 · Chống deepfake (`agent1_deepfake.py`)

**Luồng dữ liệu:**
- Trong cuộc gọi video, client (JS) cứ **mỗi 1 giây** chụp một khung hình nhỏ từ luồng video **của người gọi đến**: vẽ lên `<canvas>`, nén JPEG 320px, gửi qua SocketIO tới server.
- Âm thanh: gửi đoạn 2–3 giây mỗi 5 giây (MediaRecorder). Bản demo có thể chỉ cần gửi metadata.

**Đầu ra mỗi lần (`Agent1Result`):**
- `face_score` (0–1)
- `voice_score` (0–1)
- `behavior_score` (0–1)
- `combined_score`
- `signals` (danh sách câu tiếng Việt)
- `latency_ms`

**Ba nhóm tín hiệu:**
1. **Hình ảnh** (`face_score`): chỗ cắm model phát hiện ghép mặt. Hàm `_predict_face(frame) -> float`.
2. **Giọng nói** (`voice_score`): chỗ cắm model chống giả giọng. Hàm `_predict_voice(audio) -> float`.
3. **Hành vi cuộc gọi** (`behavior_score`), tính thật bằng luật:
   - cuộc gọi từ người lạ hoặc tài khoản có điểm tín nhiệm thấp
   - độ phân giải video thấp kéo dài
   - camera bật rồi tắt liên tục
   - **né hoặc không vượt qua thử thách**

**Chế độ demo** (vì chưa có model), `AGENT1_MODE=demo`:
- Ở trang `/demo`, người đóng vai kẻ gian chọn **"Camera giả"**. Trình duyệt phát file video có sẵn trong `static/demo_media/` qua `video.captureStream()` để làm nguồn camera, và gửi cờ `demo_source="deepfake_sample"` lên server.
- Khi có cờ đó, `face_score` tăng dần từ khoảng 0.3 lên 0.9 trong 10–15 giây, có dao động ngẫu nhiên nhẹ để trông tự nhiên.
- Camera thật thì điểm thấp, dao động quanh 0.05–0.25.
- **Ghi rõ trong README:** đây là mô phỏng để trình diễn luồng xử lý, chưa phải model thật.
- Để sẵn 1–2 file video mẫu. Nếu không có, sinh một video hoạt hình đơn giản bằng Pillow hoặc OpenCV.

**Thang phản ứng** (ngưỡng trong `config.py`, có tính đến điểm tín nhiệm từ Agent 2):
- `combined_score ≥ 0.5`: hiện **cảnh báo nhỏ** ở góc màn hình cuộc gọi.
- `combined_score ≥ 0.7`: hiện **thử thách thời gian thực** cho người nhận đọc yêu cầu, ví dụ:
  - "Hãy nhờ người gọi quay mặt sang trái"
  - "Hãy nhờ người gọi đưa tay qua mặt"
  - "Hãy nhờ người gọi đọc câu: [câu ngẫu nhiên]"

  Người nhận bấm "Người gọi làm được" hoặc "Không làm được / hình vỡ". Kết quả này cập nhật `behavior_score`.
- **Tự động ngắt cuộc gọi** khi `combined_score ≥ 0.9` **và** (người gọi là người lạ hoặc clone, **hoặc** điểm tín nhiệm dưới 40, **hoặc** thất bại thử thách). Sau khi ngắt:
  - hiện màn hình giải thích
  - hiện nút **"Gọi lại tài khoản thật của [tên]"** nếu Agent 2 tìm ra tài khoản gốc
  - hiện nút "Báo cáo"
- **Không bao giờ tự ngắt chỉ dựa vào điểm hình ảnh.** Đây là cách tránh ngắt nhầm cuộc gọi thật khi mạng yếu hoặc trời tối.

Kết thúc cuộc gọi, Agent 1 ghi `CallVerdict` (điểm cao nhất, có deepfake không, có bị ngắt không). Kết quả này được gửi cho Agent 3 và Agent 2 (mục 6).

### 5.2 Agent 2 · Thám tử (`agent2_detective.py`)

**Được gọi khi:**
- có lời mời kết bạn
- có tin nhắn đầu tiên từ người lạ
- có cuộc gọi đến
- mở khung chat với một người

Kết quả được cache 10 phút.

**Đầu ra (`TrustCard`):**
- `trust_score` (0–100)
- `level` (`tin_cay` / `chu_y` / `rui_ro_cao`)
- `reasons` (câu tiếng Việt)
- `clone_of` (null hoặc `{user_id, name, similarity}`)
- `features` (dict)
- `latency_ms`

**Đặc trưng, chỉ lấy từ DB của app:**
- tuổi tài khoản
- đã xác minh số điện thoại hoặc danh tính chưa
- số lần đổi tên và đổi ảnh đại diện trong 30 ngày
- số lời mời kết bạn gửi trong 24h, tỷ lệ được chấp nhận
- số người lạ đã nhắn trong 24h, tỷ lệ được trả lời
- số tin gần giống nhau gửi cho nhiều người lạ (rải tin hàng loạt; so sánh bằng SimHash hoặc `difflib` trên văn bản đã chuẩn hóa)
- số lần bị chặn hoặc báo cáo
- số bạn chung với người được bảo vệ, đã từng trò chuyện chưa
- STK và SĐT người này từng gửi có nằm trong danh sách đen không (gọi `toolkit.blacklist`)
- các cờ deepfake từ những cuộc gọi trước

**Phát hiện clone:** so người này với **bạn bè của người được bảo vệ**. Tiêu chí:
- tên gần giống (bỏ dấu rồi dùng `difflib`)
- ảnh đại diện giống (`imagehash`)
- tài khoản mới hơn tài khoản gốc và không phải chính người đó

**Tính điểm:** bắt đầu từ 70, cộng hoặc trừ theo trọng số. Mỗi yếu tố được cộng hoặc trừ sinh ra một câu trong `reasons`.
- Ví dụ trừ điểm: "Tài khoản tạo 2 ngày trước", "Ảnh đại diện trùng với Nguyễn Thu Hà trong danh sách bạn của bạn".
- Ví dụ cộng điểm: "Đã xác minh danh tính", "12 bạn chung".

Có cờ `AGENT2_USE_MODEL=false` kèm hàm `_load_model()` rỗng để sau này cắm LightGBM hoặc GNN.

### 5.3 Agent 3 · Đọc vị (`agent3_adapter.py`) — model ĐÃ TRAIN

**Không tự viết model.** Chỉ viết adapter với 3 backend, chọn qua `.env`:
- `AGENT3_BACKEND=http`: POST tới `AGENT3_URL`, timeout `AGENT3_TIMEOUT` (mặc định 15s).
- `AGENT3_BACKEND=python`: import hàm theo `AGENT3_MODULE` (ví dụ `my_model.infer:analyze`), gọi `analyze(payload) -> dict`.
- `AGENT3_BACKEND=mock`: luật đơn giản để demo khi model tắt. **Backend thật lỗi hoặc quá thời gian thì tự rơi về mock** và ghi log.

Hai hàm `build_payload()` và `map_response()` tách riêng để tôi chỉnh cho khớp model.

**Input mặc định:**
```json
{
  "conversation": [{"role": "sender|receiver", "text": "...", "timestamp": "ISO8601", "attachments": []}],
  "trust_card": {"trust_score": 25, "level": "rui_ro_cao", "clone_of": null, "reasons": []},
  "toolkit": {"normalized_text": "...", "entities": {}, "blacklist_hits": [], "apk_findings": [], "domain_findings": []},
  "recent_call": {"deepfake_detected": true, "max_score": 0.92, "ended_by_guardian": true, "minutes_ago": 2}
}
```
`conversation` lấy tối đa 20 tin gần nhất. `recent_call` để null nếu không có cuộc gọi trong 24h.

**Output mặc định mong đợi:**
```json
{
  "is_scam": true,
  "risk_score": 0.0,
  "phase": "tiep_can|tao_tin|gay_ap_luc|co_lap|yeu_cau|none",
  "scenario": "gia_cong_an|gia_nguoi_than|gia_ngan_hang_dien_luc|viec_nhe_luong_cao|dau_tu_tien_ao|gia_shipper|lay_lai_tien|bat_coc_online|khac|none",
  "signals": ["..."],
  "explanation_vi": "Giải thích dễ hiểu cho người lớn tuổi"
}
```
Kiểm tra (validate) output; thiếu trường thì dùng giá trị mặc định an toàn. Không bao giờ ghép nội dung tin nhắn vào chỉ dẫn hệ thống.

## 6. Bộ công cụ dùng chung (`toolkit/`) — không AI, dùng ngay được

- `normalize.py`: chữ thường; gỡ ký tự chèn ("c.h.u.y.ể.n" → "chuyển"); đổi teencode theo `teencode.json` ("ck", "stk", "ko", "tk"...); tạo bản không dấu.
- `extract.py`, trích xuất bằng regex có kiểm tra hợp lệ:
  - URL
  - SĐT Việt Nam: `(0|\+84)(3|5|7|8|9)\d{8}`
  - STK: 8–19 chữ số gần các từ "stk / tk / số tài khoản / ck"
  - tên ngân hàng
  - file `.apk`
- `blacklist.py`: tra `blacklist.json` (STK, SĐT, domain, sha256 của APK). Có hàm `add()` để thêm mục mới khi người dùng báo cáo.
- `qr.py`: giải mã QR bằng `pyzbar` nếu có. Không có thì đọc trường `demo_qr_payload` của ảnh seed.
- `apk_inspect.py`: tính sha256; đọc quyền bằng `androguard` nếu có, không thì đọc `demo_apk_meta`. Các quyền nguy hiểm cần gắn cờ:
  - Trợ năng (`BIND_ACCESSIBILITY_SERVICE`)
  - đọc SMS (`READ_SMS`)
  - hiển thị đè lên app khác (`SYSTEM_ALERT_WINDOW`)
- `domain_check.py`: so tên miền với `official_domains.json` (vietcombank.com.vn, evn.com.vn, dichvucong.gov.vn...) bằng khoảng cách Levenshtein để phát hiện tên nhái, cộng với tra danh sách đen.

**Luồng tin nhắn:** mỗi tin đi qua toolkit trước. Tin **không có thực thể nào, không có từ khóa tiền bạc hoặc khẩn cấp, và người gửi có điểm tín nhiệm ≥ 70** thì không cần gọi Agent 3, đỡ tốn tài nguyên. Các tin còn lại gọi Agent 3.

## 7. Orchestrator và bộ quyết định

`orchestrator.py` xử lý theo **sự kiện**. Mọi phân tích chạy **nền** (background task của SocketIO), không làm chậm chat hay cuộc gọi.

| Sự kiện | Agent chạy | Hiển thị |
|---|---|---|
| Lời mời kết bạn | Agent 2 | Thẻ tín nhiệm trên lời mời |
| Mở chat / tin đầu từ người lạ | Agent 2 | Banner đầu khung chat |
| Tin nhắn mới | Toolkit → (nếu cần) Agent 3, có kèm Thẻ tín nhiệm và cờ cuộc gọi gần nhất | Huy hiệu và thẻ giải thích trên tin |
| Cuộc gọi đến | Agent 2 trước, rồi Agent 1 suốt cuộc gọi | Thẻ tín nhiệm trên màn hình gọi đến, đồng hồ đo deepfake trong cuộc gọi |
| Kết thúc cuộc gọi | Lưu `CallVerdict` | Thông báo kết quả |

**Mức cảnh báo cho tin nhắn** (`decision.py`, ngưỡng trong `config.py`):
- **Mức 3 · Chặn:** có bất kỳ điều kiện nào sau:
  - trúng danh sách đen
  - APK có quyền nguy hiểm
  - tên miền nhái
  - `risk_score ≥ 0.85`
  - (`recent_call.deepfake_detected` **và** tin có yêu cầu tiền)
- **Mức 2 · Cảnh báo + hãm:** `risk_score ≥ 0.6`, **hoặc** (`clone_of` khác null **và** có yêu cầu tiền).
- **Mức 1 · Nhắc nhẹ:** `risk_score ≥ 0.35`, **hoặc** `trust_score < 40`.
- **Mức 0 · An toàn:** còn lại.

**Lưu vết:** bảng `GuardianEvent` lưu loại sự kiện, kết quả JSON của từng agent và toolkit, mức cuối, thời gian từng bước, chế độ từng agent.

**Phối hợp giữa các agent và miễn dịch bầy đàn:**
- Agent 1 phát hiện deepfake → giảm điểm tín nhiệm người gọi (Agent 2), và gắn `recent_call` cho Agent 3.
- Agent 3 kết luận lừa đảo (mức 3) hoặc người dùng bấm "Báo cáo lừa đảo":
  - thêm STK, SĐT, domain, hash APK vào danh sách đen
  - giảm điểm tín nhiệm người gửi
  - **cảnh báo mọi người khác mà người này đã nhắn tin, gọi hoặc kết bạn trong 7 ngày**
- Người dùng bấm "Không phải lừa đảo" hoặc "Đây là người quen": lưu bảng `Feedback`, sau này dùng làm nhãn train.

## 8. Giao diện bảo vệ (phần phải đẹp nhất)

- **Thẻ tín nhiệm:**
  - Hiện ở lời mời kết bạn, hồ sơ (chỉ người xem thấy), đầu khung chat và màn hình cuộc gọi đến.
  - Gồm vòng điểm có màu (xanh / vàng / đỏ), 2–3 lý do chính và nút "Xem thêm".
  - Nếu là clone: hiện lớn **"Có thể là tài khoản giả mạo [tên]"** kèm nút mở tài khoản thật.
- **Trong cuộc gọi video:**
  - Đồng hồ đo "Độ thật" ở góc màn hình. Ở chế độ demo luôn hiện, ở chế độ thường chỉ hiện khi có nghi ngờ.
  - Cảnh báo theo bậc và hộp thử thách.
  - Màn hình "Vệ sĩ đã ngắt cuộc gọi" kèm giải thích và nút "Gọi lại tài khoản thật".
- **Trong chat:**
  - Huy hiệu theo mức: vàng / cam / đỏ (mức 3 thì che nội dung).
  - Thẻ giải thích dùng `explanation_vi` của Agent 3, có các nút: "Vì sao?" (mở chi tiết các agent), "Báo cáo lừa đảo", "Không phải lừa đảo", "Chặn".
- **Hãm thao tác:**
  - Link nghi vấn bị làm mờ, phải bấm "Tôi hiểu rủi ro, vẫn mở".
  - Từ mức 2, copy STK phải qua **đếm ngược 60 giây**.
  - Ở mức 3, file APK bị chặn tải xuống.
- **Mật mã gia đình:** khi có cờ clone, deepfake hoặc scenario `gia_nguoi_than`, gợi ý người dùng hỏi câu bí mật.
- **Nút "Hỏi Vệ sĩ":** dán một đoạn văn bản hoặc chọn một cuộc hội thoại để kiểm tra. Hệ thống chạy toolkit, Agent 2 và Agent 3, rồi trả lời bằng tiếng Việt.
- **Người giám hộ:** nhận thông báo khi người được giám hộ gặp cảnh báo mức 2 hoặc 3, hoặc bị ngắt cuộc gọi deepfake. **Không** được xem nội dung tin nhắn.

## 9. Chế độ demo (điểm nhấn khi trình bày)

### 9.1 `/guardian` — Bảng điều khiển Vệ sĩ
- **Dòng thời gian realtime** các sự kiện (kết bạn, tin nhắn, cuộc gọi). Mỗi sự kiện hiển thị kết quả của từng agent và toolkit, mức cuối, thời gian xử lý (ms) và chế độ (demo / heuristic / model / mock).
- **Thống kê:**
  - số sự kiện theo loại
  - % tin nhắn không cần gọi Agent 3
  - số cuộc gọi deepfake bị ngắt
  - số clone phát hiện được
  - danh sách đen tăng thêm hôm nay
- Biểu đồ đơn giản bằng `<canvas>` hoặc CSS.

### 9.2 `/demo` — Màn hình trình diễn
- Ba cột: **kẻ gian** | **nạn nhân** | **dây chuyền 3 agent**. Các agent sáng lần lượt khi xử lý.
- Thanh chọn kịch bản và nút **"Phát kịch bản"**: tự gửi lời mời, tin nhắn, cuộc gọi theo kịch bản, cách nhau 2–3 giây.
- Công tắc **bật/tắt từng agent** để so sánh trước và sau.
- Nút **đăng nhập nhanh** vào tài khoản demo.
- Cuộc gọi demo dùng **"Camera giả"** (mục 5.1). Gợi ý chạy hai cửa sổ trình duyệt.

### 9.3 `seed.py` và `data/scenarios.json`
Tạo khoảng 30 người dùng bình thường (ảnh đại diện sinh bằng Pillow), bạn bè, bài đăng và hội thoại thường ngày. Sau đó tạo các kịch bản:

1. **Kịch bản chủ lực, cả đội cùng ra tay — Clone "Nguyễn Thu Hà":**
   - Bà Lan (62 tuổi) có con gái thật là Thu Hà (bạn từ lâu, đã xác minh). Tài khoản clone tạo 1 ngày, cùng ảnh đại diện.
   - Clone gửi lời mời kết bạn → **Agent 2** hiện "Có thể là tài khoản giả mạo Nguyễn Thu Hà".
   - Clone gọi video bằng camera giả → **Agent 1** đưa thử thách, rồi tự ngắt cuộc gọi, kèm nút "Gọi lại Thu Hà thật".
   - 2 phút sau, clone nhắn "mạng yếu quá, mẹ chuyển con 15 triệu vào stk này nhé, đừng nói với bố" → **Agent 3** nhận cờ deepfake, xếp mức 3, gợi ý Mật mã gia đình.
2. **Giả công an + APK:** người lạ xưng "cán bộ công an quận", nói "anh liên quan đường dây rửa tiền", gửi `XacMinhCongDan.apk` (`demo_apk_meta` có quyền Trợ năng và đọc SMS) → toolkit và Agent 3 → mức 3, chặn file.
3. **Giả điện lực + link nhái:** "EVN CSKH" báo "nợ cước, cắt điện trong 2h", gửi link `evn-thanhtoan.xyz` → domain_check phát hiện tên nhái.
4. **Việc nhẹ lương cao, rải hàng loạt:**
   - Một tài khoản nhắn tin gần giống nhau cho 20 người lạ, chữ lách luật kiểu "v.i.ệ.c n.h.ẹ", "ib zalo", "hoa hồng 30%".
   - Agent 2 tụt điểm vì hành vi rải tin.
   - Một người báo cáo → 19 người còn lại nhận cảnh báo.
5. **Đầu tư tiền ảo kéo dài 10 ngày** (timestamp giả lùi ngày): làm quen → khoe lãi → gửi link sàn → giục nạp tiền. Thể hiện Agent 3 theo dõi pha.
6. **Giả shipper + QR:** ảnh QR thanh toán phí ship, `demo_qr_payload` chứa STK có trong danh sách đen.
7. **Chứng minh không báo nhầm:**
   - "ck t 200k tiền trà sữa nhé"
   - shop quen gửi STK
   - bạn gửi link YouTube
   - **một cuộc gọi video thật giữa hai người bạn bằng camera thật**

   → tất cả phải ra **mức 0** và **không bị ngắt cuộc gọi**.

**Mọi STK, SĐT, tên miền trong dữ liệu demo đều là giả**, không trùng người hoặc tổ chức thật. Riêng `official_domains.json` dùng tên miền chính thức thật để so tên nhái.

## 10. Yêu cầu phi chức năng và thứ tự làm

**Bảo mật:**
- CSRF trên mọi form
- escape nội dung người dùng
- giới hạn kích thước và loại file upload
- lưu file với tên ngẫu nhiên
- APK chỉ lưu và phân tích tĩnh, **không bao giờ mở hay thực thi**

**Quyền riêng tư:**
- Khung hình cuộc gọi chỉ xử lý trong bộ nhớ, **không lưu lại**. Chỉ lưu điểm số.
- Agent 2 không ra internet.

**Responsive:** dùng tốt trên điện thoại, Messenger và màn hình cuộc gọi có bố cục mobile riêng.

**Test (`pytest`):**
- toolkit: chuẩn hóa, trích xuất, domain nhái, APK nguy hiểm
- Agent 2: phát hiện clone, tính điểm
- Agent 1 ở chế độ demo: camera thật không bao giờ bị ngắt
- bộ quyết định với Agent 3 ở chế độ mock
- kịch bản 7 ra mức 0

**README:**
- cài đặt
- `python seed.py` rồi `python app.py`
- danh sách tài khoản demo
- cách demo cuộc gọi bằng 2 cửa sổ
- cấu hình Agent 3
- cách cắm model thật vào Agent 1 (`_predict_face`, `_predict_voice`) và Agent 2 (`_load_model`)

**Thứ tự giai đoạn:**
1. Khung dự án, cấu hình, models, đăng nhập/đăng ký, OTP giả lập
2. Hồ sơ, bạn bè, bảng tin, thông báo, tìm kiếm
3. Messenger realtime
4. Gọi thoại và video WebRTC (signaling qua SocketIO)
5. Toolkit + Agent 2 + adapter Agent 3 (kèm mock) + orchestrator + decision, kèm test
6. Agent 1 chế độ demo, camera giả, thử thách, tự ngắt cuộc gọi
7. Giao diện bảo vệ: Thẻ tín nhiệm, cảnh báo chat, hãm thao tác, Mật mã gia đình, người giám hộ, Hỏi Vệ sĩ
8. `/guardian` và `/demo`
9. `seed.py` với 7 kịch bản
10. Hoàn thiện giao diện, dark mode, mobile, README

Bắt đầu bằng việc hỏi tôi về Agent 3, sau đó trình bày kế hoạch.
