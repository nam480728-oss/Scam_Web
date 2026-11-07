# CLAUDE.md

Mạng xã hội demo **DangNam** (Flask + Jinja2 + JS thuần + Socket.IO) có **Vệ sĩ AI 3** đọc tin nhắn gửi đến người dùng
để phát hiện lừa đảo, áp dụng **luật 3 lần** (lần 1 cảnh báo, lần 2 che tin, lần 3 tự chặn) và **Khiếu nại gỡ chặn**.
Kèm **Độ uy tín** tài khoản (luật riêng) và **Truy vết IP** kẻ lừa đảo (chỉ quản trị viên). Tài liệu đầy đủ: `README.md`.

## Lệnh thường dùng (Windows, PowerShell)

```powershell
python -m flask --app app db upgrade          # chạy migration (MySQL/MariaDB XAMPP, CSDL data_scam)
python -m flask --app app db migrate -m "..." # tạo migration mới sau khi sửa db/models.py
python seed.py [--reset] [--no-scan]          # dữ liệu demo + 8 kịch bản (data/scenarios.json)
python app.py                                 # http://127.0.0.1:5000  (/admin: mật khẩu ADMIN_PASSWORD)
python -m pytest tests -q                     # ~3-5 phút, tạo CSDL tạm data_scam_test, AI 3 giả lập (FakePredictor)
python -m pytest tests/test_ip_trace.py -q -k ten_test
```

Cần MySQL đang chạy ở `127.0.0.1:3306` (root, không mật khẩu) cho cả app lẫn test.

## Kiến trúc

- `app.py`: `create_app()` đăng ký blueprint, `trace_service.init` (ghi IP đăng nhập qua tín hiệu `user_logged_in`),
  `ProxyFix` khi `TRUST_PROXY=true`. `__main__` gọi `manager.preload()`.
- `config.py`: `Config` + `MODEL_KEY = "svm"` + `model_specs()` (tự tìm lần train mới nhất `ai_training/IDF_SVM/outputs/`,
  bỏ qua `*smoke*`). Ngưỡng độ uy tín `REPUTATION_*`, truy vết `IP_RETENTION_DAYS`, `GEOIP_*`.
- `db/models.py`: toàn bộ bảng. Mỗi thay đổi schema **phải có migration Alembic** trong `migrations/versions/`
  (test chạy migration thật, không dùng `create_all`). Bảng mới cũng phải thêm vào danh sách TRUNCATE trong `tests/conftest.py`.
- `routes/`: blueprint mỏng; logic ở `services/`. API `/api/...` trả JSON, lỗi nghiệp vụ ném `ChatError(msg, status)`.
  `routes/admin.py` = trang `/admin` (tab model / traces / requests / reputation, kiểm tra bằng `session["is_admin"]`).
- `services/ai_client.py`: `manager` — chỉ 1 mô hình **TF-IDF + Linear SVM**; `manager.active` luôn `"svm"`; nạp lười ở lần
  `predict()` đầu tiên, lỗi thì trả `None` → adapter rơi về mock. Test gắn mô hình giả bằng `manager.set_predictor(obj)`.
- `agents/` = dây chuyền Vệ sĩ, chạy nền sau mỗi tin nhắn (`orchestrator.on_message` → `process_message`):
  `agent3_text.py` (tiền xử lý) → `agent3_adapter.py` (backend `local|http|python|mock`, log `logs/agent3.log`) →
  `decision.py` (luật 3 lần) → `ScamCounter`, `GuardianEvent`, `auto_block()` (lần 3: chặn + `trace_service.create_trace`).
- `services/reputation_service.py`: `evaluate(target, viewer_id)` (điểm + chi tiết, CHỈ admin) và `badge()` (chỉ màu + nhãn,
  cho người dùng). Không ảnh hưởng AI 3.
- `services/trace_service.py` + `services/ip_geo.py`: IP lưu ở `messages.sender_ip` / `login_logs` (tự xóa sau N ngày),
  hồ sơ `scam_traces` (lần 3), `trace_requests` (nạn nhân xin → admin duyệt). Định vị: demo → nội bộ → `.mmdb` → ip-api (tắt mặc định).
- Realtime: `services/realtime.py` (`emit_to(user_id, event, data)`), sự kiện `guardian:message`.

## Quy ước quan trọng

- Vệ sĩ **chỉ bảo vệ người nhận**: kết quả AI chỉ hiện cho người nhận; người gửi không biết cho tới lần 3.
- **IP và điểm uy tín không bao giờ xuất hiện trong API / trang của người dùng** (trừ `victim_view` khi yêu cầu truy vết được duyệt).
  Thêm trường vào `message_dto` / `conversation_dto` / `user_dto` phải giữ nguyên quy tắc này (có test kiểm tra).
- Cột `users.model_key` vẫn còn (luôn `"svm"`); truy vấn người dùng vẫn lọc theo `manager.active`.
- Ngôn ngữ: giao diện **tiếng Việt có dấu**; comment/docstring trong code **tiếng Việt không dấu**; tên biến/hàm tiếng Anh.
- Bảo mật: CSRF trên mọi form / API ghi, JS dựng DOM bằng `textContent`, file upload tên ngẫu nhiên, `.apk` lưu `.bin`.
- Trong test: `GUARDIAN_ASYNC=False` (Vệ sĩ chạy đồng bộ); IP của test client là `127.0.0.1` (đổi bằng `environ_base`).
- Dữ liệu demo: `data/scenarios.json` (`old_names` = lịch sử đổi tên, `demo_ip` + `demo_ip_geo` = IP demo dải RFC 5737),
  dựng bởi `services/demo_service.py`. Mọi STK / SĐT / tên miền / IP demo đều giả.
