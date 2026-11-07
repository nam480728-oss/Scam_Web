# Lý thuyết mô hình TF-IDF + Linear SVM

Tài liệu giải thích **nền tảng lý thuyết** và **cách áp dụng cụ thể trong dự án DangNam** của mô hình TF-IDF + Linear SVM
(mô hình duy nhất của **AI 3 · Đọc vị**).

| | **TF-IDF + Linear SVM** |
| --- | --- |
| Dùng cho | **AI 3 · Đọc vị**: tin nhắn có phải lừa đảo không |
| Đầu vào | Văn bản (tin nhắn) |
| Đầu ra | Xác suất tin lừa đảo (0–1) |
| Loại mô hình | Học máy cổ điển: đặc trưng thủ công + bộ phân loại tuyến tính |
| Dữ liệu train | `ai_training/data/Data_Scam_*.xlsx` (tin nhắn tiếng Việt) |
| Mã nguồn | `ai_training/IDF_SVM/` |

Đây là bài toán **phân loại nhị phân**: nhãn 0 = bình thường, nhãn 1 = lừa đảo.

**Vai trò trong hệ thống:** mô hình **không tự ra quyết định cuối cùng**. Xác suất của nó được hiệu chỉnh theo ngữ cảnh cuộc trò
chuyện (`agents/agent3_adapter.py`) rồi đưa vào **luật 3 lần** (`agents/decision.py`): lần 1 cảnh báo, lần 2 che tin, lần 3 tự
động chặn (gỡ qua Khiếu nại).

---

# PHẦN A — TF-IDF + LINEAR SVM

## A1. Ý tưởng chung

Máy tính không hiểu chữ, chỉ hiểu số. Mô hình làm hai bước:

1. **TF-IDF** biến mỗi tin nhắn thành một **vector số** rất dài. Mỗi chiều ứng với một từ hoặc một cụm ký tự; giá trị cho biết từ đó **quan trọng** thế nào trong tin.
2. **Linear SVM** tìm một **siêu phẳng** (đường thẳng trong không gian nhiều chiều) chia vector tin lừa đảo và tin bình thường về hai phía, sao cho **khoảng cách an toàn** (margin) giữa hai nhóm là lớn nhất.

```text
"Chuyển khoản gấp vào STK 0123..."  ──tiền xử lý──►  "chuyen khoan gap vao stk sotktoken"
        ──TF-IDF──►  x = [0, 0.42, 0, …, 0.31, …]  (7.695 chiều)
        ──SVM──►     d = w·x + b = 0.83   ──Platt──►  p(lừa đảo) = 0.9999
```

## A2. Tiền xử lý văn bản (`IDF_SVM/preprocess.py`)

| Bước | Ví dụ | Lý do |
| --- | --- | --- |
| Thay link bằng `urltoken` | `evn-thanhtoan.xyz/pay` → `urltoken` | Mỗi link khác nhau là một từ "lạ"; gộp lại thì mô hình học được *"có link"* là dấu hiệu |
| Thay SĐT bằng `sdttoken` | `0912 345 678` → `sdttoken` | Tương tự: quan trọng là *có SĐT*, không phải số cụ thể |
| Thay dãy ≥ 9 chữ số bằng `sotktoken` | `99990001234567` → `sotktoken` | Số tài khoản |
| Thay số tiền bằng `tientoken` | `15tr`, `500.000đ` → `tientoken` | Số tiền |
| Chữ thường | `CHUYỂN` → `chuyển` | Gộp biến thể hoa / thường |
| Bỏ dấu | `chuyển khoản` → `chuyen khoan` | Tin không dấu và có dấu thành cùng một đặc trưng (kẻ gian hay viết không dấu) |
| Gộp khoảng trắng | | Làm sạch |

## A3. Biểu diễn túi từ (Bag of Words) và n-gram

**Túi từ** coi tin nhắn là một "túi" các từ: đếm số lần mỗi từ xuất hiện và **bỏ qua thứ tự**.

**n-gram** là chuỗi n đơn vị liên tiếp, giúp giữ lại một chút thứ tự:
- n-gram **từ**: `chuyen khoan gap` → 1-gram: `chuyen`, `khoan`, `gap`; 2-gram: `chuyen khoan`, `khoan gap`.
- n-gram **ký tự** (`char_wb`: chỉ lấy trong phạm vi một từ, có thêm dấu cách ở hai đầu):
  `ck` → ` c`, `ck`, `k `, ` ck`, `ck `, ` ck `.
  `chuyen` → ` c`, `ch`, `hu`, `uy`, `ye`, `en`, `n `, ` ch`, `chu`, …

Vì sao dùng **n-gram ký tự**? Kẻ gian cố tình viết lệch để lách bộ lọc (`chuyen khoan`, `chuyển khỏan`, `ck`, `v.i.ệ.c n.h.ẹ`).
Các biến thể này **chung nhiều cụm ký tự**, nên mô hình vẫn nhận ra dù từ bị viết sai.

Dự án **ghép cả hai** loại đặc trưng (`FeatureUnion`). Bộ tham số tốt nhất tìm được:
n-gram từ (1, 1) + n-gram ký tự (2, 4) → **7.695 đặc trưng**.

| Cấu hình (bảng ablation trong `outputs/.../ablation.csv`) | Số đặc trưng | Macro-F1 val | Macro-F1 test |
| --- | --- | --- | --- |
| Chỉ TF-IDF từ | 1.076 | 0,9848 | 0,9847 |
| Chỉ TF-IDF ký tự | 6.619 | 0,9725 | 0,9909 |
| **Từ + ký tự (đang dùng)** | **7.695** | **0,9848** | **0,9878** |

## A4. TF-IDF

Một từ quan trọng với một tin khi nó **xuất hiện nhiều trong tin đó** (TF cao) nhưng **hiếm trong toàn bộ dữ liệu** (IDF cao).
Từ như `ban` (bạn) có mặt khắp nơi nên ít giá trị phân biệt; `sotktoken` hiếm hơn nên đáng chú ý hơn.

**Term Frequency.** Dự án bật `sublinear_tf`, tức dùng log để một từ lặp 10 lần không "nặng gấp 10":

$$\text{tf}(t, d) = 1 + \ln\big(\text{số lần } t \text{ xuất hiện trong } d\big)$$

**Inverse Document Frequency** (công thức có làm mượt của scikit-learn):

$$\text{idf}(t) = \ln\frac{1 + n}{1 + \text{df}(t)} + 1$$

trong đó $n$ là tổng số tin, $\text{df}(t)$ là số tin chứa $t$.

**Trọng số** $\;w_{t,d} = \text{tf}(t,d) \times \text{idf}(t)$, sau đó **chuẩn hóa L2** để vector dài 1. Nhờ vậy tin dài và tin ngắn so sánh được với nhau:

$$\hat{x}_d = \frac{x_d}{\lVert x_d \rVert_2}$$

**Ví dụ tính tay** với 3 tin (đã tiền xử lý):

| Tin | Nội dung |
| --- | --- |
| d1 | `chuyen khoan gap` |
| d2 | `chuyen khoan tien tra sua` |
| d3 | `di an com khong` |

- $n = 3$. Từ `chuyen` xuất hiện ở 2 tin → $\text{idf} = \ln\frac{4}{3} + 1 = 1{,}288$. Tương tự `khoan` = 1,288.
- Từ `gap` chỉ ở 1 tin → $\text{idf} = \ln\frac{4}{2} + 1 = 1{,}693$ (hiếm hơn nên quan trọng hơn).
- Vector d1 trước chuẩn hóa: (chuyen 1,288; khoan 1,288; gap 1,693), độ dài $\sqrt{1{,}288^2 + 1{,}288^2 + 1{,}693^2} = 2{,}487$.
- Sau chuẩn hóa: **(0,518; 0,518; 0,681)**: từ `gap` ("gấp") có trọng số lớn nhất trong d1.

**Lọc từ:** `min_df = 2` bỏ cụm xuất hiện trong ít hơn 2 tin (thường là lỗi gõ, nhiễu); `max_df = 0,95` bỏ cụm xuất hiện trong hơn 95% số tin (vô nghĩa).

## A5. Support Vector Machine (SVM) tuyến tính

### Hàm quyết định

$$d(x) = w \cdot x + b \qquad \hat{y} = \begin{cases} 1 \;(\text{lừa đảo}) & d(x) > 0 \\ 0 \;(\text{bình thường}) & d(x) \le 0 \end{cases}$$

- $w$: vector trọng số, mỗi đặc trưng một con số. Trọng số dương đẩy về "lừa đảo", âm đẩy về "bình thường".
- $b$: hệ số chặn (bias). Trong mô hình hiện tại $b = -0{,}317$.
- Mặt phẳng $w \cdot x + b = 0$ là **siêu phẳng phân tách**.

### Lề cực đại (maximum margin)

Có vô số siêu phẳng chia được hai nhóm. SVM chọn siêu phẳng **xa các điểm gần nhất của cả hai nhóm nhất**. Các điểm nằm sát lề gọi là
**support vectors**; chỉ chúng quyết định vị trí siêu phẳng. Độ rộng lề là $\frac{2}{\lVert w \rVert}$, nên **lề lớn** ⇔ **$\lVert w \rVert$ nhỏ**.
Lề lớn giúp mô hình **tổng quát tốt** hơn trên tin chưa thấy.

### Lề mềm (soft margin) và tham số C

Dữ liệu thật có nhiễu (tin bị gán nhãn nhầm, tin mơ hồ), nên SVM cho phép một số điểm vi phạm lề và phạt chúng.
Dự án dùng `LinearSVC` với hàm mất mát **squared hinge**:

$$\min_{w,b}\;\; \frac{1}{2}\lVert w\rVert^2 \;+\; C \sum_{i=1}^{N} c_{y_i}\,\big[\max\big(0,\; 1 - y_i\,(w\cdot x_i + b)\big)\big]^2 \qquad (y_i \in \{-1, +1\})$$

- Số hạng thứ nhất làm **lề rộng** (chính quy hóa).
- Số hạng thứ hai phạt điểm **nằm sai phía hoặc lọt vào lề**. Điểm nằm đúng phía và ngoài lề có lỗi = 0.
- **C** cân bằng hai mục tiêu. C lớn: cố phân loại đúng mọi điểm train, dễ **quá khớp**. C nhỏ: lề rộng, chấp nhận sai vài điểm, **tổng quát hơn**.
  Đã thử C ∈ {0,03; 0,1; 0,3; 1; 3; 10}, **chọn C = 0,3**.

### Trọng số lớp (`class_weight = balanced`)

Dữ liệu train có 926 tin bình thường và 655 tin lừa đảo. Để mô hình không thiên về lớp đông hơn, mỗi lớp $k$ có hệ số phạt:

$$c_k = \frac{N}{K \cdot N_k}: \qquad c_{\text{lừa đảo}} = \frac{1581}{2 \times 655} = 1{,}21 \qquad c_{\text{bình thường}} = \frac{1581}{2 \times 926} = 0{,}85$$

Bỏ sót một tin lừa đảo bị phạt nặng hơn báo nhầm một tin bình thường.

### Vì sao SVM **tuyến tính** hợp với TF-IDF?

- Vector TF-IDF có **rất nhiều chiều** (7.695) nhưng **thưa** (mỗi tin chỉ có vài chục chiều khác 0). Trong không gian nhiều chiều như vậy, hai lớp **thường tách được bằng siêu phẳng** (Joachims, 1998), nên không cần kernel phi tuyến.
- Huấn luyện **nhanh** (mô hình hiện tại hội tụ sau 24 vòng lặp), dự đoán khoảng 1 ms/tin, file mô hình nhỏ.
- **Giải thích được**: mỗi đặc trưng có một trọng số, xem trực tiếp được.

## A6. Từ điểm SVM sang xác suất: Platt scaling

SVM chỉ cho **điểm quyết định** $d$, không phải xác suất. Dự án dùng **Platt scaling** (huấn luyện trên tập validation) để đổi $d$ thành xác suất:

$$p(\text{lừa đảo} \mid x) = \sigma(a\,d + c) = \frac{1}{1 + e^{-(a\,d + c)}}$$

Mô hình hiện tại có $a = 11{,}51$ và $c = 0{,}717$:

| Điểm SVM $d$ | Xác suất |
| --- | --- |
| −0,5 | 0,006 |
| 0 (đúng trên siêu phẳng) | 0,672 |
| +0,3 | 0,985 |

App dùng **nhãn gốc của SVM** ($d > 0$) để gắn cờ, và dùng **xác suất Platt** làm `risk_score` cho Agent 3
(trước khi hiệu chỉnh theo ngữ cảnh, xem README chính, mục 5).

## A7. Chọn siêu tham số

Grid search trong `config.yaml`:

| Siêu tham số | Các giá trị thử |
| --- | --- |
| C | 0,03 / 0,1 / 0,3 / 1 / 3 / 10 |
| class_weight | không có / balanced |
| Bỏ dấu | có / không |
| n-gram từ | (1, 1) / (1, 2) |
| n-gram ký tự | (2, 4) / (2, 5) |

Tổng cộng 96 tổ hợp. Mỗi tổ hợp được train trên tập train, rồi **chọn theo macro-F1 trên tập validation**. Tập test **chỉ dùng một lần** để báo cáo kết quả cuối cùng,
nên con số trên test không bị "nhìn trộm".

**Bộ tốt nhất:** C = 0,3 · balanced · bỏ dấu · n-gram từ (1, 1) · n-gram ký tự (2, 4).

## A8. Đọc mô hình: những đặc trưng quan trọng nhất

Vì mô hình tuyến tính, có thể xem đặc trưng nào đẩy về phía nào (`outputs/.../top_features.csv`):

| Đẩy về **lừa đảo** (trọng số dương) | Trọng số | Đẩy về **bình thường** (trọng số âm) | Trọng số |
| --- | --- | --- | --- |
| `tai` (tài khoản, tải, tại) | +0,89 | `di` (đi) | −0,80 |
| `ten` (tên) | +0,68 | `chao` (chào) | −0,72 |
| `hang` (ngân hàng, hàng) | +0,66 | `nay` (này) | −0,62 |
| `tientoken` (có số tiền) | +0,60 | | |
| `khoan` (khoản) | +0,56 | | |
| `urltoken` (có link) | +0,55 | | |

Các token thay thế `tientoken`, `urltoken` lọt vào nhóm mạnh nhất, cho thấy bước tiền xử lý có tác dụng.

## A9. Kết quả (lần train `tfidf_linear_svm_20261013_001417`, tập test 339 tin)

| Accuracy | Macro-F1 | Precision (lừa đảo) | Recall (lừa đảo) | ROC-AUC |
| --- | --- | --- | --- | --- |
| 98,82% | 0,9878 | 100% | 97,16% | 0,9998 |

## A10. Ưu điểm và hạn chế

**Ưu điểm:** nhanh, nhẹ, chạy CPU tốt, giải thích được, ít cần dữ liệu, chịu được viết sai / lách luật nhờ n-gram ký tự.

**Hạn chế:**
- **Không hiểu ngữ cảnh và ngữ nghĩa sâu.** Mô hình chỉ thấy *cụm chữ nào có mặt*, không hiểu ai nói với ai, nói để làm gì.
  Ví dụ trong app: `ck t 200k tiền trà sữa nhé` (bạn bè trả tiền trà sữa) bị chấm **0,85**, vì có `chuyen khoan` + `tientoken`, giống tin lừa đảo.
  Đó là lý do adapter Agent 3 nhân xác suất với **hệ số ngữ cảnh** (bạn quen + điểm tín nhiệm cao + không có dấu hiệu gây áp lực → ×0,25).
- **Lệch miền dữ liệu:** train trên **SMS**, nhưng app nhận **tin chat**.
- Gặp từ hoàn toàn mới (không có trong tập train) thì mô hình không có trọng số cho từ đó.

---

## Thuật ngữ

| Thuật ngữ | Nghĩa |
| --- | --- |
| Siêu phẳng | "Đường thẳng" chia đôi không gian nhiều chiều |
| Margin (lề) | Khoảng cách từ siêu phẳng đến điểm dữ liệu gần nhất |
| Chính quy hóa | Phạt mô hình quá phức tạp để tránh quá khớp |
| Quá khớp (overfitting) | Học thuộc tập train nhưng kém trên dữ liệu mới |
| ROC-AUC | Xác suất mô hình chấm mẫu dương cao hơn mẫu âm (1 = hoàn hảo, 0,5 = đoán bừa) |
| Precision / Recall | Trong số báo "lừa đảo" có bao nhiêu đúng / trong số "lừa đảo" thật bắt được bao nhiêu |
| FPR | Tỷ lệ mẫu bình thường bị báo nhầm |

## Tài liệu tham khảo
1. Salton, G., Buckley, C. (1988). *Term-weighting approaches in automatic text retrieval*. Information Processing & Management.
2. Cortes, C., Vapnik, V. (1995). *Support-vector networks*. Machine Learning.
3. Joachims, T. (1998). *Text categorization with Support Vector Machines: Learning with many relevant features*. ECML.
4. Platt, J. (1999). *Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods*.
5. Fan, R.-E. et al. (2008). *LIBLINEAR: A library for large linear classification*. JMLR.
