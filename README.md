# Day 06 · Data Ingestion Engineering

## Bài nộp

**Nguyễn Lương Nguyên · 2A202604005 · L3B**. Corpus: *The World Bank Group Annual Report 2026* (CC BY-NC-ND 3.0 IGO).

Báo cáo: [report/individual/2A202604005_NguyenLuongNguyen.md](report/individual/2A202604005_NguyenLuongNguyen.md). Tổng hợp kết quả: [starter/results/metrics_summary.md](starter/results/metrics_summary.md).

| Thành phần | Vị trí |
|---|---|
| Dữ liệu và manifest | `starter/data/The World Bank Group Annual Report 2026.pdf` (bản gốc, chưa chỉnh sửa) · [data/manifest.json](data/manifest.json) |
| Benchmark | [benchmark/questions.json](benchmark/questions.json) (15 dev / 5 test) · [benchmark/verification.json](benchmark/verification.json) · [benchmark/README.md](benchmark/README.md) |
| Code | [starter/src/](starter/src/) (ingestion, chunking, embeddings, store, evaluation, run) · [starter/scripts/](starter/scripts/) |
| Cấu hình A/B/C | [starter/results/strategies.json](starter/results/strategies.json) · [artifacts/experiment_log.csv](artifacts/experiment_log.csv) |
| Trace và chỉ số | `starter/results/traces/{dev,test}.jsonl` · `starter/results/metrics_{dev,test}.json` · [selection.json](starter/results/selection.json) |
| Nhãn thủ công và log lỗi | [starter/results/audit/](starter/results/audit/) · [ingestion_log.json](starter/results/ingestion_log.json) · [reading_order_review.md](starter/results/reading_order_review.md) |

**Môi trường đã dùng:**
- Python 3.15.2: pypdf 6.21.4, psycopg 3.3.8, python-dotenv 1.2.4, google-genai 3.3.0
- Docker: PostgreSQL 16.16 + pgvector 0.8.7
- Embedding: `gemini-embedding-001`, 768 chiều, metric cosine, tìm kiếm exact

**Tái lập** (chạy trong thư mục `starter/`, Windows PowerShell; trên macOS/Linux dùng `source .venv/bin/activate` và `cp`):

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env        # điền GEMINI_API_KEY; EMBEDDING_MODEL để trống thì mặc định là gemini-embedding-001
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py      # kỳ vọng: Setup OK

python -m scripts.build_manifest       # đọc PDF, đếm trang, tạo ../data/manifest.json và data/processed/pages.jsonl
python -m scripts.verify_benchmark     # kiểm chứng evidence của 20 câu trên text đã chuẩn hóa
python -m src.run ingest               # chunk A/B, embed, upsert A/B/C (chạy lại: 0 lần gọi API, không nhân đôi)
python -m src.run retrieve --split dev
python -m src.run retrieve --split test  # chỉ chạy được khi đã có results/selection.json
python -m scripts.check_reading_order  # rà soát thứ tự đọc của pypdf
python -m src.run search "câu hỏi" --strategy C --section IFC   # truy vấn thử
```

Ghi chú: lệnh `retrieve` ghi đè trace và chỉ số trong `results/`. Kết quả gốc của bài nộp là bản đã commit. Nạp lại dùng `embedding_cache` trong PostgreSQL, nên một database mới sẽ phải gọi lại API (khoảng 13 lần cho tài liệu và 20 lần cho câu hỏi).

---

## Đề bài

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.
