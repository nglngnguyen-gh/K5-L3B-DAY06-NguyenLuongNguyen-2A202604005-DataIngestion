# Báo cáo cá nhân — Day 6

**Học viên:** Nguyễn Lương Nguyên · 2A202604005 · L3B
**Corpus:** The World Bank Group Annual Report 2026 · **Ngày chạy:** 2026-11-14

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  - Nguồn là *The World Bank Group Annual Report 2026* (World Bank Group, DOI 10.1596/AR2026, tải từ worldbank.org/en/about/annual-report). File PDF gốc, chưa chỉnh sửa, nằm tại `starter/data/`.
  - Giấy phép là **CC BY-NC-ND 3.0 IGO**, ghi ở trang PDF 45. Trước khi đọc kỹ, tôi tưởng là CC BY. Bài lab không nhằm mục đích thương mại. File PDF được giữ nguyên. Text đã trích, các chunk và embedding chỉ dùng cho thí nghiệm truy xuất và không được phát hành như một tác phẩm phái sinh (`starter/data/processed/` nằm trong `.gitignore`).
  - PDF có 46 trang vật lý. Từ trang 3 trở đi, mỗi trang là một trang đôi gồm 2 trang in, tổng cộng 87 trang in. **Đơn vị đếm là trang PDF vật lý**, cách đếm này thận trọng hơn đếm trang in.
  - Một trang được tính nếu trích xuất thành công, có ít nhất 500 ký tự sau chuẩn hóa, và không phải mục lục hay phần pháp lý cuối sách. Kết quả: **41 trang được tính, khoảng 183k ký tự**. Các trang bị loại: p1 (bìa), p2 (mục lục), p8 (trang ngăn chương), p45 (pháp lý, bản quyền, credits), p46 (bìa sau).
  - Chi tiết nằm trong [data/manifest.json](../../data/manifest.json), có kèm SHA-256 của file PDF.
- **Chuẩn hóa, lỗi và giới hạn:**
  - Text được đọc bằng `pypdf` 6.21.4, sau đó chuẩn hóa: NFKC, bỏ soft hyphen, bỏ footer chạy dọc trang (số trang in được giữ riêng trong metadata `printed_pages`), nối lại các từ bị ngắt bằng gạch nối cuối dòng, và gom khoảng trắng. Mọi trang đều có lớp text nên không cần OCR. Không có trang nào rỗng hoặc lỗi; số trang in đọc từ footer khớp với công thức ánh xạ trang ([ingestion_log.json](../../starter/results/ingestion_log.json)).
  - **Giới hạn lớn nhất là thứ tự đọc.** `pypdf` trả text theo thứ tự trong content stream của file, không theo vị trí hiển thị trên trang. Hậu quả: **11 câu bị cắt đôi trên 8/41 trang**, trong đó nửa sau của câu nằm cách xa nửa đầu (có chỗ tới khoảng 7.000 ký tự). Ngoài ra có 9 trang bị đảo thứ tự cả khối văn bản và 8 trang có heading bị đọc ra sau phần thân bài. Tôi phát hiện lỗi này **sau khi đã chạy test**, nên đã ghi lại nhưng không sửa pipeline ([reading_order_review.md](../../starter/results/reading_order_review.md), script [check_reading_order.py](../../starter/scripts/check_reading_order.py)).
- **Embedding, vector store, metric, lệnh chạy và chi phí:**
  - Model `gemini-embedding-001` qua Google Gemini API (SDK `google-genai` 3.3.0), cắt còn **768 chiều** rồi chuẩn hóa L2. Tài liệu được embed với `task_type=RETRIEVAL_DOCUMENT`, câu hỏi với `RETRIEVAL_QUERY`. Nếu API lỗi, chương trình thử lại khi gặp 429/5xx rồi báo lỗi, **không fallback sang vector giả**.
  - Vector store là **PostgreSQL 16.16 + pgvector 0.8.7** chạy bằng Docker. Metric là **cosine** (`<=>`), tìm kiếm **exact** (quét toàn bộ, không dùng index xấp xỉ). Filter được áp dụng bằng SQL `WHERE` trước khi xếp hạng.
  - Lệnh chạy: xem [README](../../README.md#bài-nộp).
  - Tài nguyên:
    - Lần embed tài liệu đầu tiên: 13 lần gọi API, 607 đoạn text, 389.582 ký tự.
    - Embed câu hỏi: 20 lần gọi API.
    - Nạp lại: 0 lần gọi API, nhờ bảng `embedding_cache`.
  - **Số token** đếm bằng API `countTokens` của chính model này: A 46.348, B 41.579, câu hỏi 452, **tổng 88.379 token**. Trang hạn mức trong AI Studio cho thấy mức cao nhất 85,08K TPM, khớp với việc phần embed tài liệu chạy xong trong chưa đầy 1 phút.
  - **Chi phí:** trang hạn mức hiển thị 3K RPM, tương ứng gói trả phí (Tier 1). Tính theo giá niêm yết $0,15/1M token đầu vào ([bảng giá Gemini API](https://ai.google.dev/gemini-api/docs/pricing), tra ngày 2026-11-14), chi phí **ước tính khoảng $0,013** (A ≈ $0,0070, B ≈ $0,0062, C $0, câu hỏi ≈ $0,0001). Đây là số tính lại từ token và đơn giá, không phải số đọc từ hóa đơn; trang hạn mức không hiển thị chi phí.
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  - Mỗi chunk có `document_id`, `source` (đường dẫn file PDF) và `page` (trang PDF bắt đầu từ 1), cộng thêm `printed_pages` (số trang in), `chunk_index`, `heading` (chỉ B và C có) và `content_hash`.
  - **Trường lọc là `sections`** (kiểu `text[]`). Giá trị được lấy nguyên văn từ **mục lục in ở trang PDF 2**, ánh xạ theo số trang in. Có 13 giá trị, trong đó 5 chương theo tổ chức là One World Bank Group, World Bank (IBRD/IDA), IFC, MIGA, ICSID. Một trang đôi nằm ở ranh giới hai chương mang cả hai giá trị (p26, p32).
  - Lý do chọn trường này: báo cáo đặt **cùng loại số liệu cho nhiều tổ chức khác nhau** (bảo lãnh, trái phiếu, số "case"...), nên lọc theo chương là phạm vi tự nhiên khi người dùng đang đọc một chương cụ thể.

## Cấu hình và benchmark

- **A / B / C:** cả ba dùng cùng corpus, cùng model và cùng store. Chunk luôn nằm gọn trong một trang. Tham số đầy đủ ở [strategies.json](../../starter/results/strategies.json) và [experiment_log.csv](../../artifacts/experiment_log.csv).

  | | A | B | C |
  |---|---|---|---|
  | Chunking | Cửa sổ cố định **800 ký tự, overlap 100**, không căn theo ranh giới câu | Dựng lại đoạn văn từ các dòng bị xuống dòng theo cột, heading viết HOA mở chunk mới, gộp tối đa **800 ký tự**, tách theo câu nếu đoạn quá dài, gộp chunk dưới 200 ký tự | **Giống hệt B** (dùng lại cả vector) |
  | Truy xuất | top-3, không lọc | top-3, không lọc | top-3, **có filter `section`** nếu câu hỏi có cung cấp |
  | Số chunk | 276 | 331 | 331 |

  A và B có cùng ngân sách 800 ký tự, nên **so sánh A với B chỉ khác ranh giới chunk**. **B và C chỉ khác ở filter.**
- **Benchmark ≥20 câu:**
  - 20 câu, chia **15 dev / 5 test** trước khi chạy bất kỳ thí nghiệm nào. Loại câu: 8 trực tiếp, 5 diễn đạt lại, 3 có điều kiện hoặc ngoại lệ, 4 có metadata filter (d11, d12, d14 thuộc dev; **t03** thuộc test).
  - Mỗi câu filter hỏi một con số **dễ nhầm giữa các tổ chức**. Ví dụ t03 hỏi số "case": ICSID có 363, CAO có 63, INT có 54. Giá trị filter là ngữ cảnh người dùng cung cấp trước ("đang đọc chương X"), không suy ra từ đáp án.
  - Script [verify_benchmark.py](../../starter/scripts/verify_benchmark.py) kiểm chứng tự động: evidence có nguyên văn trên trang gold (sau chuẩn hóa) không, trang gold có được tính không, giá trị filter có trên trang đó không, và evidence còn xuất hiện ở trang nào khác. Script phát hiện evidence của t02 lặp lại ở p29 và p30, nên hai trang này được thêm làm gold thay thế.
  - Hash của bộ câu hỏi lưu trong [verification.json](../../benchmark/verification.json). Bộ câu hỏi được commit tại `53aa324`, trước khi có code truy xuất.
- **Tiêu chí chọn đã chốt trước khi xem test:** ưu tiên dev Evidence Hit@3 cao nhất; nếu hòa thì xét dev Hit@1; tiếp theo là grounding trên dev; cuối cùng là ít chunk hơn hoặc ingest nhanh hơn. Tiêu chí này ghi trong [questions.json](../../benchmark/questions.json). Lựa chọn được khóa trong [selection.json](../../starter/results/selection.json) và **commit `547b93a` (2026-11-14 10:54 +07) trước lần chạy test duy nhất**. Code cũng từ chối chạy test khi chưa có file khóa này.

## Kết quả

Hit (truy xuất chính xác) chỉ được tính khi chunk thuộc trang gold **và chứa đủ** evidence. Thời gian là thời gian embed tài liệu của lần ingest đầu tiên, cộng thời gian ghi vào DB.

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | **14/15** | 14/15 | 276 | embed 9,5 s + DB 0,7 s | 46.348 token ≈ $0,0070 |
| A | test | 4/5 | 5/5 | 276 | ″ | ″ |
| B | dev | 13/15 | 14/15 | 331 | embed 10,0 s + DB 0,7 s | 41.579 token ≈ $0,0062 |
| B | test | **5/5** | 5/5 | 331 | ″ | ″ |
| C | dev | 13/15 | 14/15 | 331 | embed 0,1 s (cache) + DB 0,8 s | $0 (dùng lại vector của B) |
| C | test | **5/5** | 5/5 | 331 | ″ | ″ |

Câu hỏi (20 câu, dùng chung cho cả 3 cấu hình): 452 token ≈ $0,0001. Chi phí là ước tính theo giá $0,15/1M token của gói trả phí.

Thời gian tìm kiếm (trung vị trên dev) khoảng 4,5 ms/câu cho cả ba cấu hình. Độ dài chunk (min / trung vị / max): A 102 / 800 / 800; B và C 80 / 578 / 800.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 1,0 (n=10) | 15/15 | dev 1/3 · test 1/1 (không lọc) | 0/0/5 · 2,0 |
| B | 1,8 (n=10) | 15/15 | dev 1/3 · test 1/1 (không lọc) | 0/0/5 · 2,0 |
| C | 1,8 (n=10) | 15/15 | **dev 3/3** · test 1/1 | 0/0/5 · 2,0 |

Với A và B, cột filter đo xem khi **không lọc** thì top-3 có tự nằm trong section được yêu cầu không. Số liệu này dùng để so sánh B với C.

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
- Trace top-3 đầy đủ (text, score, metadata, nhãn hit): [traces/dev.jsonl](../../starter/results/traces/dev.jsonl), [traces/test.jsonl](../../starter/results/traces/test.jsonl). Chỉ số: [metrics_dev.json](../../starter/results/metrics_dev.json), [metrics_test.json](../../starter/results/metrics_test.json).
- **Coherence:** lấy 10 trang được tính đầu tiên theo thứ tự (p3–7, p9–13). Vị trí chấm là đoạn 40 ký tự bắt đầu ở ranh giới từ đầu tiên sau điểm giữa trang. Mẫu này được xác định trước khi chấm ([coherence_sample.json](../../starter/results/audit/coherence_sample.json), [coherence_labels.csv](../../starter/results/audit/coherence_labels.csv)).
- **Grounding:** chấm top-3 của 5 câu test cho cả 3 cấu hình ([grounding_labels.csv](../../starter/results/audit/grounding_labels.csv)).
- **Metadata:** đối chiếu tự động 45 bản ghi (5 câu test × top-3 × 3 cấu hình). Trang được kiểm bằng cách xác nhận text của chunk nằm nguyên văn trong text trích lại của đúng trang PDF đó ([metadata_audit.csv](../../starter/results/audit/metadata_audit.csv)). Phương pháp và thang điểm: [audit/README.md](../../starter/results/audit/README.md).
- **Nhãn thủ công:** AI (Claude) chấm nháp cả 45 nhãn (30 coherence, 15 grounding), có ghi lý do cho từng nhãn (cột `labeler`). Tôi duyệt lại từng nhãn theo PDF (cột `reviewed_by`). Kết quả: **giữ nguyên toàn bộ điểm số**; **sửa lý do của 6 nhãn** (pos01 và pos02, mỗi vị trí 3 cấu hình) sau khi phát hiện lỗi thứ tự đọc của `pypdf`. Lý do cũ của pos02 ("câu tiếp tục sau một heading chen vào") là không chính xác.

## Phân tích và kết luận

- **So sánh A với B (chỉ khác ranh giới chunk):**
  - **Coherence cải thiện rõ, từ 1,0 lên 1,8.** Cả 10 chunk của A đều bắt đầu hoặc kết thúc giữa từ, nhưng nhờ overlap 100 ký tự nên câu tại vị trí lấy mẫu chưa lần nào bị cắt (không có điểm 0).
  - **Độ chính xác truy xuất không khác biệt có ý nghĩa.** Hit@3 bằng nhau; Hit@1 của A hơn B 1 câu trên dev nhưng kém B 1 câu trên test. Với 15 và 5 câu, chênh lệch 1 câu nằm trong sai số.
  - B embed ít hơn 12% số ký tự (vì không có overlap) nhưng tạo nhiều hơn 20% số chunk.
  - Trên test, chunk ngắn và gọn của B giúp xếp đúng hạng: ở t03, B đặt đoạn Figure 5 lên hạng 1, còn A xếp ở hạng 3 sau hai đoạn khác cũng nói về ICSID.
- **So sánh B với C (chỉ khác filter):**
  - **Hit không đổi.** Câu hỏi có filter đạt Hit@3 3/3 và 1/1 ngay cả khi không lọc.
  - Lợi ích của filter là làm sạch hạng 2–3, với chi phí bằng 0: tỷ lệ tuân thủ trên dev tăng từ 1/3 lên 3/3. Không lọc thì d11 kéo theo p19 (số liệu trái phiếu của IBRD/IFC), d12 kéo theo p5 và p18 (số vốn tư nhân của toàn Nhóm).
  - **Hạn chế:** `sections` được gán theo trang, nên p32 mang cả "World Bank (IBRD/IDA)" lẫn "IFC". Kết quả là một chunk về hoạt động mua sắm (procurement) của World Bank vẫn lọt qua filter IFC.
- **Ví dụ sai:**
  1. **d02** (dev, gold p6, hỏi "$25 billion in guarantees"): **cả ba cấu hình đều trượt.** Top-3 trả về p4 ("surpassed its goal of $20 billion … four years ahead") và p38. Trang p4 nói đúng là đã vượt mục tiêu nhưng **không có con số 25 tỷ**. Ở p17, con số trong infographic bị tách khỏi nhãn khi trích text. Đây là lỗi truy xuất thật.
  2. **d01** (dev, gold p6): hạng 1 của B và C là **p5** ("shortened average project preparation and approval times from 19 months to nine"). Đoạn này nêu đúng thông tin chính nhưng **thiếu điều kiện** "dự án rủi ro thấp chỉ cần 60 ngày", nên theo định nghĩa strict thì không phải hit. Đoạn gold nằm ở hạng 2. Bài học là bộ gold chưa liệt kê các trang có thông tin tương đương, vì bước kiểm chứng chỉ tìm câu trùng nguyên văn.
  3. **Lỗi trích xuất (pos02, p4):** câu "…consolidation of the Environmental and Social" bị cắt, và phần tiếp theo "function, this critical milestone…" nằm cách khoảng 2.000 ký tự. Không cách chunk nào giữ được trọn câu, nên lỗi này phải sửa ở bước đọc PDF.
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
  - Theo quy tắc đã chốt trước, **chọn A**: dev Hit@3 hòa 14/15, rồi Hit@1 của A là 14/15 so với 13/15 của B và C.
  - Tôi ghi nhận trung thực rằng lựa chọn này dựa trên **chênh lệch đúng 1 câu**, và kết quả test cho chiều ngược lại.
  - Nếu chunk được đưa cho LLM đọc, các bằng chứng cùng chỉ về **C**: coherence 1,8, filter loại bỏ chunk gây nhiễu từ các tổ chức khác, chi phí như B. Tuy nhiên nhận định này hình thành **sau khi đã xem test**, nên không phải kết quả kiểm tra độc lập. Muốn xác nhận cần một bộ test mới.
  - C chỉ có ích khi người dùng hoặc ngữ cảnh thật sự cung cấp được section, và khi nhãn section đáng tin.
- **Hạn chế:**
  - Chỉ có **một tài liệu**; bộ câu hỏi chỉ có 20 câu, test chỉ 5 câu.
  - **Grounding đạt 2,0 ở cả ba cấu hình** (hiệu ứng trần), nên test quá dễ để phân biệt các cấu hình.
  - Câu hỏi, gold và nhãn đều do một người làm, có AI hỗ trợ soạn nháp, nên có nguy cơ thiên lệch. Người chấm biết chunk thuộc cấu hình nào.
  - Benchmark **không phát hiện được** lỗi thứ tự đọc, vì không câu hỏi nào nhắm vào đoạn bị cắt.
  - Metadata `heading` sai ở 8 trang (không dùng cho filter).
  - Thời gian chỉ đo một lần trên máy cá nhân. Chi phí là số tính lại từ token và đơn giá, chưa đối chiếu với hóa đơn.
  - Dev và test có chung một số chương; gold thay thế của d14 (p39) trùng trang gold của t04.
- **Nếu làm lại hoặc mở rộng:**
  1. Đọc PDF theo bố cục (ví dụ PyMuPDF text blocks sắp theo cột) và kiểm tra bằng `check_reading_order.py` **trước** khi viết benchmark.
  2. Trong bước kiểm chứng gold, tìm thêm các trang chứa thông tin tương đương bằng tìm kiếm ngữ nghĩa, không chỉ khớp nguyên văn.
  3. Viết thêm câu test khó hơn: đáp án nằm rải trên nhiều chunk, hoặc nhắm vào bảng và infographic.
  4. Gán section ở mức chunk theo heading, sau khi đã sửa thứ tự đọc.
  5. Thử hybrid BM25 cộng dense cho các câu nhiều con số.

### Công cụ AI và cách kiểm tra
Tôi dùng Claude Code (Claude Opus 5.5) để viết code pipeline, soạn nháp câu hỏi benchmark và chấm nháp các nhãn thủ công. Cách tôi kiểm tra:
- Evidence được script kiểm chứng nguyên văn trên trang gold.
- Lựa chọn cấu hình được khóa và commit trước khi chạy test.
- Metadata được đối chiếu tự động với PDF.
- Các nhãn coherence và grounding được tôi duyệt lại theo PDF.
- Lỗi thứ tự đọc do tôi phát hiện khi duyệt pos01, sau đó được kiểm tra trên toàn corpus.
