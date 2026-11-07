# PROMPT CHO CLAUDE CODE — Mạng xã hội "Khiên" tích hợp đội vệ sĩ AI chống lừa đảo


---

## 0. Vai trò và cách làm việc

Bạn là kỹ sư full-stack Python. Hãy xây một **mạng xã hội demo kiểu Facebook** tên **"Khiên"** bằng **Flask + HTML/CSS (Jinja2) + JavaScript thuần**. App có nhiều tính năng mạng xã hội, nhưng **điểm nhấn để demo là hệ thống 3 agent AI chống lừa đảo qua tin nhắn**.

Quy tắc làm việc:
1. **Trước khi code, hãy hỏi tôi về Agent 3** (mục 5.3): model chạy kiểu gì (HTTP API hay hàm Python), input/output thực tế ra sao. Nếu tôi chưa có câu trả lời, dùng schema mặc định ở mục 5.3.
2. Lập kế hoạch theo các giai đoạn ở mục 9, cho tôi xem rồi mới làm. Sau mỗi giai đoạn, chạy thử, báo ngắn gọn đã xong gì.
3. Toàn bộ giao diện bằng **tiếng Việt**. Tên biến, hàm, file bằng tiếng Anh.
4. App phải **chạy được offline**, không phụ thuộc dịch vụ bên ngoài. Agent 3 không kết nối được thì tự chuyển sang chế độ dự phòng, app không được crash.

---

## 1. Công nghệ

- Python 3.11+, Flask, Jinja2, Flask-Login, Flask-WTF (CSRF), Flask-SQLAlchemy + SQLite
- Flask-SocketIO cho chat realtime và đẩy cảnh báo realtime
- HTML/CSS thuần (CSS variables, có dark mode), JavaScript thuần. **Không dùng React/Vue/Tailwind.**
- Thư viện phụ: `python-dotenv`, `requests`, `Pillow`, `imagehash` (so ảnh đại diện), `Unidecode`. `pytesseract` là tùy chọn: nếu máy không có thì bỏ qua OCR, không báo lỗi.
- Cấu hình qua file `.env` (có `.env.example`).
- Có `requirements.txt`, `README.md` hướng dẫn chạy, và test bằng `pytest`.

## 2. Cấu trúc thư mục đề xuất

```
khien/
├── app.py                  # khởi tạo Flask, SocketIO, đăng ký blueprint
├── config.py
├── models.py               # SQLAlchemy models
├── seed.py                 # tạo dữ liệu + kịch bản demo
├── blueprints/             # auth, feed, profile, friends, messenger, notifications, search, settings, guardian, demo
├── agents/
│   ├── contracts.py        # dataclass input/output của 3 agent
│   ├── agent1_sentinel.py  # Lính gác (luật, chờ thay bằng model)
│   ├── agent2_detective.py # Thám tử (heuristic, chờ thay bằng model)
│   ├── agent3_adapter.py   # Đọc vị (kết nối model thật đã train)
│   ├── orchestrator.py     # điều phối dây chuyền
│   └── decision.py         # bộ quyết định bằng luật, KHÔNG dùng LLM
├── data/
│   ├── teencode.json
│   ├── blacklist.json      # STK, SĐT, domain, hash APK mẫu cho demo
│   ├── keywords.json       # từ khóa tín hiệu có trọng số
│   └── banks.json
├── templates/
├── static/css/  static/js/  static/uploads/
└── tests/
```

## 3. Tính năng mạng xã hội

Làm theo thứ tự ưu tiên. Bố cục 3 cột như mạng xã hội quen thuộc, nhưng **thương hiệu, logo và màu sắc là của riêng "Khiên"**. Không sao chép logo hay tên của Facebook.

**Bắt buộc:**
- Đăng ký, đăng nhập, đăng xuất. Mật khẩu được hash.
- Hồ sơ cá nhân: ảnh đại diện, ảnh bìa, giới thiệu, ngày tham gia. **Lưu lịch sử đổi tên và đổi ảnh đại diện**, vì Agent 2 cần dữ liệu này.
- Bảng tin: đăng bài (chữ + ảnh), bày tỏ cảm xúc (thích/yêu/haha/buồn/phẫn nộ), bình luận, chia sẻ. **Bài đăng không bị quét bởi hệ thống chống lừa đảo.**
- Bạn bè: gửi, chấp nhận, từ chối lời mời; gợi ý kết bạn; danh sách bạn bè; xem bạn chung.
- **Messenger** (trọng tâm):
  - chat 1-1 realtime
  - gửi chữ, ảnh, file đính kèm (cho phép cả .apk nhưng **không bao giờ thực thi**), link
  - trạng thái đã xem, danh sách hội thoại, tin nhắn chờ từ người lạ
- Thông báo realtime: lời mời kết bạn, bình luận, cảm xúc, **cảnh báo lừa đảo**.
- Tìm kiếm người dùng.
- Cài đặt: dark mode, bật/tắt Vệ sĩ, thiết lập **"Mật mã gia đình"** (câu hỏi bí mật kèm danh sách người thân), chỉ định **người giám hộ**.

**Nếu còn thời gian:** story 24h, nhóm, trang cá nhân hiển thị ảnh.

## 4. Phạm vi chống lừa đảo

- **Chỉ phân tích những gì gửi đến người dùng qua Messenger:** tin nhắn, ảnh, file, link, QR, và thông tin người gửi.
- **Không quét bài đăng hay bình luận.**
- Cảnh báo chỉ hiện cho **người nhận**. Người gửi không biết mình bị gắn cờ.

## 5. Ba agent và hợp đồng dữ liệu

Định nghĩa trong `agents/contracts.py` bằng dataclass. Mỗi agent là một class có phương thức `analyze(...)` và thuộc tính `mode` (`"rules"`, `"heuristic"`, `"model"` hoặc `"mock"`). Mục tiêu: **sau này thay Agent 1 và Agent 2 bằng model đã train mà không phải sửa code ở chỗ khác.**

### 5.1 Agent 1 · Lính gác (`agent1_sentinel.py`) — chưa train, làm bằng luật

Trả về `Agent1Result`:
`normalized_text`, `entities` (urls, phones, bank_accounts, banks, apk_files, qr_payloads), `blacklist_hits`, `signals` (danh sách nhãn), `score` (0–1), `passed` (bool), `latency_ms`.

Cách làm:
1. **Chuẩn hóa:**
   - chữ thường
   - gỡ ký tự chèn giữa chữ ("c.h.u.y.ể.n" → "chuyển")
   - đổi teencode theo `teencode.json` ("ck", "stk", "k", "ko", "tk", "đt"...)
   - tạo thêm bản không dấu bằng Unidecode để so từ khóa
2. **Trích xuất bằng regex có kiểm tra hợp lệ:**
   - URL
   - SĐT Việt Nam: `(0|\+84)(3|5|7|8|9)\d{8}`
   - STK: dãy 8–19 số đứng gần các từ "stk / tk / số tài khoản / ck"
   - tên ngân hàng theo `banks.json`
   - file hoặc link `.apk`
3. **QR:** nếu ảnh chứa QR thì giải mã (dùng `pyzbar` nếu cài được, không thì bỏ qua). Ở chế độ demo, ảnh seed có thể kèm trường `demo_ocr_text` hoặc `demo_qr_payload`.
4. **OCR:** dùng `pytesseract` với tiếng Việt nếu có, không thì dùng `demo_ocr_text`.
5. **Đối chiếu `blacklist.json`.**
6. **Tính điểm** theo trọng số từ khóa trong `keywords.json`. Các nhóm từ khóa:
   - yêu cầu tiền
   - OTP
   - CCCD
   - mạo danh cơ quan
   - khẩn cấp
   - giữ bí mật
   - chuyển kênh sang Telegram/Zalo
   - cài app
   - lợi nhuận cao
7. **Quyết định:** `passed = True` nếu điểm dưới `AGENT1_THRESHOLD`, không trúng danh sách đen và không có APK.
8. **Deepfake:** để stub, trả về `"not_checked"`.

Có cờ `AGENT1_USE_MODEL=false` cùng hàm `_load_model()` rỗng để sau này cắm model PhoBERT vào.

### 5.2 Agent 2 · Thám tử (`agent2_detective.py`) — chưa train, làm bằng heuristic trên DB

Trả về `Agent2Result`:
`sender_risk` (0–1), `features` (dict), `clone_of` (null hoặc `{user_id, name, similarity}`), `campaign` (null hoặc `{id, size, first_seen}`), `reasons` (danh sách câu tiếng Việt), `latency_ms`.

Đặc trưng tính từ DB:
- tuổi tài khoản (ngày)
- số lần đổi tên và đổi ảnh đại diện trong 30 ngày
- số lời mời kết bạn đã gửi trong 24h, tỷ lệ được chấp nhận
- số người nhận khác nhau trong 24h, tỷ lệ người nhận trả lời
- số lần bị chặn hoặc báo cáo
- số bạn chung với người nhận
- hai người đã từng nhắn với nhau trước đây chưa

**Phát hiện clone:** so người gửi với **bạn bè của người nhận**. Tiêu chí: tên gần giống (dùng `difflib`, sau khi bỏ dấu) và ảnh đại diện giống (`imagehash`). Người gửi phải **không** phải là chính người bạn đó, và tài khoản người gửi mới hơn.

**Phát hiện chiến dịch:**
- Lấy văn bản đã chuẩn hóa của Agent 1, tính SimHash, hoặc dùng `difflib` cho bản demo.
- Gom các tin gần giống nhau gửi tới ≥5 người khác nhau trong cửa sổ 6 giờ thành một chiến dịch. Có thể ghép thêm nếu dùng chung STK hoặc link.
- Lưu bảng `Campaign`.

**Tính điểm:** cộng trọng số có giải thích. Mỗi yếu tố được cộng điểm sinh ra một câu trong `reasons`, ví dụ: "Tài khoản mới tạo 2 ngày", "Không có bạn chung".

Có cờ `AGENT2_USE_MODEL=false` để sau này cắm LightGBM hoặc GNN.

### 5.3 Agent 3 · Đọc vị (`agent3_adapter.py`) — model ĐÃ TRAIN, chỉ viết adapter

**Không tự viết model.** Chỉ viết adapter có 3 backend, chọn qua `.env`:
- `AGENT3_BACKEND=http`: gửi POST tới `AGENT3_URL` (timeout `AGENT3_TIMEOUT`, mặc định 15s).
- `AGENT3_BACKEND=python`: import hàm theo `AGENT3_MODULE` (ví dụ `my_model.infer:analyze`), gọi `analyze(payload: dict) -> dict`.
- `AGENT3_BACKEND=mock`: luật đơn giản dựa trên kết quả Agent 1 và 2, để app vẫn demo được khi model tắt. **Khi backend thật lỗi hoặc quá thời gian thì tự rơi về mock** và ghi log.

Viết hai hàm `build_payload()` và `map_response()` tách riêng, để tôi chỉnh cho khớp model thật.

**Input mặc định gửi cho Agent 3:**
```json
{
  "conversation": [{"role": "sender|receiver", "text": "...", "timestamp": "ISO8601", "attachments": []}],
  "agent1": {"normalized_text": "...", "entities": {}, "blacklist_hits": [], "signals": [], "score": 0.0},
  "agent2": {"sender_risk": 0.0, "features": {}, "clone_of": null, "campaign": null, "reasons": []}
}
```
`conversation` lấy tối đa 20 tin gần nhất giữa hai người.

**Output mặc định mong đợi từ Agent 3:**
```json
{
  "is_scam": true,
  "risk_score": 0.0,
  "phase": "tiep_can|tao_tin|gay_ap_luc|co_lap|yeu_cau|none",
  "scenario": "gia_cong_an|gia_nguoi_than|gia_ngan_hang_dien_luc|viec_nhe_luong_cao|dau_tu_tien_ao|gia_shipper|lay_lai_tien|bat_coc_online|khac|none",
  "signals": ["..."],
  "explanation_vi": "Câu giải thích dễ hiểu cho người lớn tuổi"
}
```

**An toàn:** nội dung tin nhắn luôn là **dữ liệu**. Không ghép tin nhắn vào bất kỳ chỉ dẫn hệ thống nào. Kiểm tra (validate) output của Agent 3. Thiếu trường nào thì dùng giá trị mặc định an toàn.

### 5.4 Orchestrator (`orchestrator.py`) và bộ quyết định (`decision.py`)

Luồng xử lý khi một tin nhắn được gửi:
1. **Gửi tin ngay cho người nhận.** Việc phân tích chạy **nền** (background task của SocketIO), không làm chậm chat.
2. Chạy Agent 1. Nếu `passed` và Vệ sĩ đang bật: mức 0, kết thúc.
3. Nếu không qua: chạy Agent 2, rồi Agent 3 với lịch sử hội thoại.
4. `decision.py` dùng **luật xác định**. Ngưỡng đặt trong `config.py`:
   - **Mức 3 · Chặn:** trúng danh sách đen (STK/link/APK), **hoặc** có file APK từ người không phải bạn, **hoặc** `risk_score ≥ 0.85`.
   - **Mức 2 · Cảnh báo + hãm:** `risk_score ≥ 0.6`, **hoặc** (có `clone_of` **và** có yêu cầu tiền).
   - **Mức 1 · Nhắc nhẹ:** `risk_score ≥ 0.35`, **hoặc** người lạ, tài khoản dưới 7 ngày tuổi.
   - **Mức 0 · An toàn:** còn lại.
5. Lưu bảng `ScanResult`: message_id, kết quả JSON của từng agent, mức cuối, thời gian từng bước, chế độ của từng agent.
6. Đẩy sự kiện SocketIO `guardian_warning` tới người nhận, và `pipeline_update` tới trang `/guardian` và `/demo`.

**Miễn dịch bầy đàn:**
- Khi người nhận bấm "Báo cáo lừa đảo", hoặc tin bị xếp mức 3: thêm STK, link, SĐT, hash APK vào danh sách đen.
- Gửi cảnh báo cho **tất cả người nhận khác trong cùng chiến dịch**.
- Khi người dùng bấm "Đây là người quen / không phải lừa đảo": lưu thành bảng `Feedback`. Sau này dùng làm nhãn train.

## 6. Giao diện cảnh báo trong chat (phần phải đẹp nhất)

- **Huy hiệu trên tin nhắn theo mức:**
  - mức 1: viền vàng
  - mức 2: cam
  - mức 3: đỏ, nội dung bị che
- **Thẻ giải thích** hiện ngay dưới tin nhắn:
  - dùng `explanation_vi` của Agent 3
  - liệt kê dấu hiệu (gộp signals và reasons)
  - các nút: "Vì sao?" (mở chi tiết 3 agent), "Báo cáo lừa đảo", "Không phải lừa đảo", "Chặn người này"
- **Banner đầu cuộc chat với người lạ.** Ví dụ: "Người này chưa là bạn bè · Tài khoản tạo 2 ngày trước · 0 bạn chung".
- **Link nghi vấn:** làm mờ, phải bấm "Tôi hiểu rủi ro, vẫn mở" mới hiện.
- **Copy STK:** ở mức 2 trở lên, mở hộp thoại **đếm ngược 60 giây** kèm câu hỏi tự kiểm tra trước khi cho copy.
- **File APK:** ở mức 3, chặn tải xuống, kèm giải thích ("Cơ quan nhà nước không gửi app qua tin nhắn...").
- **Kịch bản "giả người thân vay tiền"** (`clone_of` khác null, hoặc scenario `gia_nguoi_than`):
  - gợi ý hỏi **Mật mã gia đình**
  - nút "Nhắn tài khoản thật của [tên người thân]"
- **Nút "Hỏi Vệ sĩ"** trong Messenger: người dùng dán bất kỳ đoạn văn bản nào hoặc chọn một cuộc hội thoại. Hệ thống chạy cả dây chuyền và trả lời bằng tiếng Việt.
- **Người giám hộ:** khi người được giám hộ nhận cảnh báo mức 2 hoặc 3, người giám hộ nhận thông báo, nhưng **không xem được nội dung tin nhắn**.

## 7. Chế độ demo (điểm nhấn khi trình bày)

### 7.1 Trang `/guardian` — Bảng điều khiển Vệ sĩ
- **Dòng thời gian realtime** của từng tin được quét, mỗi tin là một hàng, có 4 cột:
  - Agent 1: văn bản đã chuẩn hóa (tô sáng phần thay đổi), thực thể, kết quả danh sách đen, điểm
  - Agent 2: các đặc trưng chính, clone, chiến dịch
  - Agent 3: pha, kịch bản, giải thích
  - Quyết định cuối
- Mỗi cột hiển thị **thời gian xử lý (ms)** và **chế độ** (rules / heuristic / model / mock).
- **Thống kê:**
  - số tin đã quét
  - % tin đi thẳng ở Agent 1 (phễu lọc)
  - số cảnh báo theo mức
  - các chiến dịch đang hoạt động
  - danh sách đen tăng thêm hôm nay
- Biểu đồ đơn giản bằng `<canvas>` hoặc CSS, không cần thư viện.

### 7.2 Trang `/demo` — Màn hình trình diễn chia đôi
- Bên trái: góc nhìn **kẻ gian**. Ở giữa: góc nhìn **nạn nhân**. Bên phải: **dây chuyền 3 agent** sáng lần lượt khi xử lý.
- Thanh chọn kịch bản, nút **"Phát kịch bản"**: gửi tự động từng tin theo kịch bản, cách nhau 2–3 giây, để khán giả thấy mức rủi ro tăng dần theo pha.
- Công tắc **"Bật/Tắt Vệ sĩ"** để so sánh trước và sau.
- Nút **đăng nhập nhanh** vào các tài khoản demo.

### 7.3 `seed.py` — dữ liệu và kịch bản demo
Tạo khoảng 30 người dùng bình thường, có ảnh đại diện (sinh bằng Pillow: chữ cái đầu trên nền màu), quan hệ bạn bè, bài đăng và hội thoại thường ngày. Sau đó tạo các kịch bản dưới đây. Tin nhắn kịch bản lưu trong `data/scenarios.json` để dễ sửa.

1. **Giả người thân vay tiền:**
   - "Bà Lan" (62 tuổi) có con gái thật là "Nguyễn Thu Hà", bạn bè từ lâu.
   - Tài khoản clone "Nguyễn Thu Hà" mới tạo 1 ngày, dùng cùng ảnh đại diện.
   - Clone nhắn: "Mẹ ơi con đang kẹt, chuyển giúp con 15 triệu vào stk này nhé, đừng nói với bố".
   - → Agent 2 phát hiện clone, mức 2, gợi ý Mật mã gia đình.
2. **Giả công an kèm APK:**
   - Tài khoản "Cán bộ Công an Quận" nhắn rằng "anh liên quan đường dây rửa tiền", rồi gửi file `XacMinhCongDan.apk`.
   - → mức 3, chặn file.
3. **Giả điện lực kèm link nhái:**
   - "EVN CSKH" nhắn: "nợ cước sẽ bị cắt điện trong 2h".
   - Kèm link `evn-thanhtoan.xyz` (đã có trong danh sách đen).
4. **Việc nhẹ lương cao (chiến dịch):**
   - 5 tài khoản trong cùng đường dây gửi tin gần giống nhau cho 20 người, chữ viết lách luật kiểu "v.i.ệ.c n.h.ẹ", "ib zalo", "hoa hồng 30%".
   - → Agent 2 gom thành chiến dịch.
   - Một người báo cáo → 19 người còn lại nhận cảnh báo.
5. **Đầu tư tiền ảo "nuôi" nhiều ngày:**
   - Hội thoại kéo dài 10 ngày (timestamp giả lùi ngày).
   - Đi đủ các pha: làm quen → khoe lãi → gửi link sàn → giục nạp tiền.
   - → thể hiện việc theo dõi pha.
6. **Giả shipper kèm QR:** ảnh mã QR thanh toán phí ship (`demo_qr_payload` chứa STK có trong danh sách đen).
7. **Hội thoại bình thường (chứng minh không báo nhầm):**
   - "ck t 200k tiền trà sữa nhé", shop quen gửi STK thanh toán, bạn gửi link YouTube.
   - → **mức 0**.

`blacklist.json` chứa sẵn các STK, SĐT, domain và hash APK giả dùng cho các kịch bản. **Mọi STK và SĐT trong dữ liệu demo phải là số giả, không trùng người thật.**

## 8. Yêu cầu phi chức năng

- **Bảo mật:**
  - CSRF trên mọi form
  - escape nội dung người dùng trong template
  - giới hạn kích thước và loại file upload
  - lưu file với tên ngẫu nhiên
  - file APK chỉ lưu và tính hash, **không bao giờ mở hay thực thi**
- **Hiệu năng:** chat không bị chặn bởi việc phân tích AI.
- **Responsive:** dùng tốt trên điện thoại (Messenger có giao diện mobile riêng).
- **Log:** mỗi agent ghi log thời gian và lỗi. Agent 3 có log riêng.
- **Test (`pytest`):**
  - chuẩn hóa teencode và chữ chèn ký tự
  - trích xuất STK, SĐT, URL
  - phát hiện clone
  - gom chiến dịch
  - bộ quyết định với Agent 3 ở chế độ mock
  - kịch bản 7 phải ra mức 0
- **README:**
  - cài đặt
  - chạy `python seed.py` rồi `python app.py`
  - danh sách tài khoản demo
  - cách cấu hình Agent 3
  - cách thay Agent 1 và Agent 2 bằng model thật sau này

## 9. Thứ tự giai đoạn

1. Khung dự án, cấu hình, models, đăng ký/đăng nhập
2. Hồ sơ, bạn bè, bảng tin, thông báo, tìm kiếm
3. Messenger realtime (chữ, ảnh, file, link)
4. `contracts.py`, Agent 1, Agent 2, adapter Agent 3 (kèm mock), orchestrator, decision, kèm test
5. Giao diện cảnh báo trong chat, Hỏi Vệ sĩ, Mật mã gia đình, người giám hộ
6. Trang `/guardian` và `/demo`
7. `seed.py` cùng 7 kịch bản
8. Hoàn thiện giao diện, dark mode, mobile, README

Bắt đầu bằng việc hỏi tôi về Agent 3, sau đó trình bày kế hoạch.
