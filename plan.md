# Kế hoạch: Điểm uy tín · Truy vết IP · Chỉ giữ SVM · Dọn dẹp

> Trạng thái: **ĐÃ HOÀN THÀNH** (07/11/2026). Trước khi sửa: 72/72 test pass · Sau khi sửa: 84/84 test pass.

---

## 0. Kết quả quét: mô hình AI có chạy và tích hợp chưa?

**Có.** Mỗi tin nhắn → `agents/orchestrator.py` → `agent3_adapter.py` (backend `local`) → `services/ai_client.py`.

- SVM nạp + dự đoán thử: "trúng thưởng 50 triệu, bấm link…" → 0.99 · "tối nay đi ăn bún chả không" → 0.00.
- `logs/agent3.log` ghi `mode=model` (mô hình thật, không phải mock), lần gần nhất 07/11/2026.
- Mô hình lỗi → tự rơi về `mock`, app không crash.

---

## 1. Chỉ giữ TF-IDF + SVM (bỏ PhoBERT, ViSoBERT)

Cách làm: **SVM cố định**, giữ cột `model_key` (luôn là `"svm"`) để không phải sửa lớn.

1. Xóa `ai_training/phobert/`, `ai_training/VISO/` (code + kết quả train, ~1.85 GB).
2. `config.py`: `model_specs()` chỉ còn `svm`; bỏ `AI_THRESHOLD`, `MODEL_PHOBERT_PATH`, `MODEL_VISO_PATH`.
3. `services/ai_client.py`: bỏ `TransformerPredictor`; `app.py`: bỏ `import torch`; `requirements.txt`: bỏ `torch`,
   `transformers`, `sentencepiece`, `pyvi`.
4. **Tự nạp SVM khi khởi động**; bỏ màn hình chọn mô hình (`/` → đăng nhập / bảng tin; xóa `select_model.html`,
   API `/api/models/select`). `/admin` trở thành **trang quản trị** (mục 2.4 + 3.4).
5. Migration: xóa tài khoản + nhật ký thuộc thế giới `phobert` / `viso` trong CSDL.
6. `seed.py`: bỏ `--model`, chỉ tạo dữ liệu cho SVM.
7. Cập nhật `README.md`, `.env.example`, `CLAUDE.md`, tên giao diện ("AI 3 · TF-IDF + SVM").

---

## 2. Chức năng 1 — Độ uy tín người gửi lời mời kết bạn

Luật riêng, **không ảnh hưởng** tới mô hình phát hiện tin nhắn / luật 3 lần.

### 2.1 Công thức

Điểm gốc **70**, cộng/trừ theo 3 tiêu chí, kẹp trong **0–100**.

| Tiêu chí | Điều kiện | Điểm |
| --- | --- | --- |
| Tuổi tài khoản (`users.created_at`) | < 1 ngày / 1–7 ngày / 7–30 ngày | −25 / −15 / −5 |
| | 30–180 ngày / 180 ngày–1 năm / > 1 năm | +5 / +10 / +20 |
| Bạn chung với người xem | 0 / 1–2 / 3–5 / 6–10 / > 10 | −10 / 0 / +10 / +15 / +20 |
| Số lần đổi tên (`name_history`) | 0 / 1 / 2 / 3–4 / ≥ 5 | +5 / 0 / −5 / −15 / −25 |

Màu: **Xanh ≥ 80** · **Vàng 50–79** · **Đỏ < 50**. Các ngưỡng đặt trong `config.py` (`REPUTATION_*`).
Điểm tính theo cặp (người gửi, người xem) vì bạn chung khác nhau với mỗi người → tính lúc xem, không lưu cứng.

### 2.2 Ai thấy gì

| | Thấy |
| --- | --- |
| **Người dùng** | Chỉ **huy hiệu màu** + nhãn ("Đáng tin" / "Cân nhắc" / "Cảnh giác"). **Không** thấy điểm số, không thấy chi tiết cộng/trừ. |
| **Admin** | Điểm số + bảng cộng/trừ từng tiêu chí. |

Chỗ hiện huy hiệu (với người khác, không hiện với chính mình):
1. Thẻ **lời mời kết bạn đến** ở `/friends`.
2. **Trang hồ sơ** `/u/<username>`.
3. **Đầu khung chat với người lạ / Tin nhắn chờ** (chưa là bạn bè).

### 2.3 Việc cần làm

- `services/reputation_service.py`: `evaluate(target, viewer)` (đầy đủ, cho admin) và `badge(target, viewer)` (chỉ màu + nhãn).
- API trả `reputation` (chỉ badge) trong: `/api/friend-requests` (incoming), dữ liệu trang hồ sơ, `conversation_dto` khi chưa là bạn.
- Giao diện: `static/js/social.js`, `templates/profile.html`, `static/js/chat.js`, CSS huy hiệu 3 màu.
- Dữ liệu demo: lịch sử đổi tên cho tài khoản lừa đảo (vd `nguyenthuha.2025`: 1 ngày, 0 bạn chung, đổi tên 2 lần → 40 điểm, đỏ).

### 2.4 Admin

`/admin` → tab **Uy tín**: danh sách lời mời kết bạn gần đây (người gửi → người nhận), điểm, màu, chi tiết cộng/trừ.

---

## 3. Chức năng 2 — Truy vết IP kẻ lừa đảo

### 3.1 Luồng

1. **Mỗi tin nhắn** lưu IP + trình duyệt của người gửi lúc gửi (`messages.sender_ip`, `sender_user_agent`) — vì Vệ sĩ chạy nền,
   không còn request. **Mỗi lần đăng nhập** ghi `login_logs`. Hai loại này **tự xóa sau 30 ngày** (`IP_RETENTION_DAYS`).
2. **Chỉ khi Vệ sĩ tự chặn (lần 3)** → tạo bản ghi **`scam_traces`** (giữ lâu dài): kẻ gửi, nạn nhân, cuộc chat, IP của các tin
   bị gắn cờ + IP đăng nhập gần nhất, vị trí gần đúng (quốc gia, tỉnh/thành, nhà mạng), trình duyệt, thời gian.
3. **Định vị IP** (`services/ip_geo.py`), theo thứ tự:
   - IP demo (bảng IP giả lập trong `data/scenarios.json`) → vị trí demo, gắn nhãn "IP demo".
   - IP nội bộ (`127.0.0.1`, `192.168.x.x`…) → "Mạng nội bộ".
   - Có file `.mmdb` (`GEOIP_DB_PATH`, DB-IP Lite / GeoLite2) → tra offline (thư viện `maxminddb`).
   - `GEOIP_ONLINE=true` → gọi ip-api.com (timeout 3 giây). **Mặc định tắt.**
   - Không tra được → "Không xác định" (không làm hỏng luồng chat).
4. Chỉ tin `X-Forwarded-For` khi `TRUST_PROXY=true` (dùng `ProxyFix`), tránh giả mạo IP.

### 3.2 Quyền xem

- **Admin**: xem toàn bộ ở `/admin` → tab **Truy vết**, lọc theo tài khoản / IP, **xuất CSV**.
- **Người dùng không bao giờ thấy IP**, trừ khi gửi yêu cầu và được duyệt:
  - Chỉ **nạn nhân** (người đã bị Vệ sĩ tự chặn kẻ đó giúp) mới gửi được: nút **"Yêu cầu thông tin truy vết"** ở thanh
    "⛔ Vệ sĩ đã tự động chặn" và tab Đã chặn, kèm lý do.
  - Admin → tab **Yêu cầu**: Duyệt / Từ chối + ghi chú. Người dùng nhận thông báo.
  - Duyệt → nạn nhân xem được IP + vị trí gần đúng + thời gian **chỉ của vụ liên quan tới mình** (trang `/trace-requests`).

### 3.3 Việc cần làm

- Migration: `messages.sender_ip`, `messages.sender_user_agent`; bảng `login_logs`, `scam_traces`, `trace_requests`.
- `services/ip_geo.py`, `services/trace_service.py`; ghi IP ở `routes/chat.py` + `routes/auth.py`; tạo trace trong
  `orchestrator.auto_block()`.
- Admin: tab Truy vết / Yêu cầu / Uy tín; người dùng: nút gửi yêu cầu + trang `/trace-requests`.
- Seed: IP demo (dải dành cho tài liệu `203.0.113.x`, `198.51.100.x` — không trùng IP thật của ai) cho tài khoản lừa đảo.

---

## 4. Dọn thư mục / file rác (xóa hết)

| Đường dẫn | Lý do |
| --- | --- |
| `ai_training/phobert/`, `ai_training/VISO/` | Bỏ 2 mô hình (mục 1) |
| `ai_training/IDF_SVM/outputs/tfidf_linear_svm_smoke_*` | Lần chạy thử |
| `ai_training/data/agent1_sample_ff/`, `agent1_sample_faces/` | Dữ liệu chống deepfake đã bỏ |
| `ai_training/src/`, `configs/`, `notebooks/`, `README.md`, `requirements.txt`, `data/README.md`, `docs/labeling_guideline.md`, `docs/scam_scenarios.md` | File rỗng 0 byte |
| `ai_training/saved_models/`, `ai_training/reports/`, `docs/`, `instance/` | Thư mục rỗng |
| `ai_training/test_data.py` | Đọc file không tồn tại |
| `ai_training/data/~$Data_vi_Scam.xlsx` | File khóa tạm của Excel |
| `ai_training/data/old/` | Dữ liệu cũ |
| `prompt_claude_code.md`, `prompt_claude_code_v2.md` | Prompt cũ, lỗi thời |
| `logs/agent3.log`, `uploads/appeals/2/`, mọi `__pycache__/`, `.pytest_cache/` | Log / ảnh khiếu nại sót / cache |
| `.gitignore` | Bỏ các dòng `agent1`, `FaceForensics`, `stt`, `demo_media` |

---

## 5. Thứ tự thực hiện

1. Dọn rác + bỏ 2 mô hình → chạy test + nạp thử SVM.
2. Điểm uy tín → test (`tests/test_reputation.py`).
3. Truy vết IP + yêu cầu truy vết → migration → test (`tests/test_ip_trace.py`).
4. Cập nhật tài liệu; chạy toàn bộ test; seed lại, kiểm tra trên trình duyệt.
