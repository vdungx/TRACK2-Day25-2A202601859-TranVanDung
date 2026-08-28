# Lab 25 — GPU FinOps Optimization Write-up

## 1. Kết quả tổng quan

Trên snapshot dữ liệu tháng 6/2026, chi phí baseline của NimbusAI là **$27,133/tháng**. Sau khi áp dụng các core lever, chi phí optimized còn **$14,626/tháng**, tiết kiệm **$12,507 (46.1%)**.

Đối với inference, tổng traffic là 7,533,027 token/ngày. Chi phí giảm từ **$6.488 xuống $1.126/1M-token**, tương đương **82.6%**. Đây là thước đo phù hợp hơn `$ / GPU-hour` vì phản ánh cả giá GPU và số token thực sự phục vụ.

| Lever | Savings/tháng |
|---|---:|
| Inference: cascade + cache + batch | $1,212 |
| Purchasing: spot + reserved | $10,040 |
| Right-size GPU-Util lies | $655 |
| Tắt GPU idle | $600 |
| **Tổng** | **$12,507** |

Inference tạo ra unit economics tốt nhất, còn purchasing là khoản tiết kiệm tuyệt đối lớn nhất do các workload GPU chạy nhiều giờ.

## 2. Phân tích M1: GPU-Util không phải hiệu quả

`gpu-h100-4` báo GPU-Util khoảng 98.2% nhưng MFU chỉ 0.194. `gpu-a10g-1` cũng là một util-lie với GPU-Util 96.9% và MFU 0.268. GPU-Util chỉ cho biết thời gian GPU đang active; nó không chứng minh tensor cores đang đạt gần peak FLOPs. Memory stall, kernel launch overhead hoặc pipeline không đủ việc có thể làm GPU “bận” nhưng tạo ra ít FLOPs hữu ích.

GPU `gpu-h100-5` có 8 giờ idle/ngày. Với giá on-demand H100 $2.50/giờ, phần lãng phí là **$20/ngày**, tương đương **$600/tháng**. Vì vậy cần theo dõi MFU/MBU và lịch bật/tắt instance thay vì chỉ nhìn `nvidia-smi`.

## 3. Extension 2: MBU-aware right-sizing

Mình dùng ngưỡng MBU `<= 0.40` cho nhóm inference cần xem xét, sau đó chỉ chấp nhận GPU thay thế có HBM không thấp hơn GPU hiện tại, bandwidth peak đủ đáp ứng bandwidth quan sát được và giá giờ thấp hơn.

Kết quả scenario:

- `job-infer-chat`: A10G → L4; `$ / GB` giảm từ 0.0417 xuống 0.0333, tiết kiệm **$864/tháng**.
- `job-batch-eval`: H100 → MI300X; `$ / GB` giảm từ 0.0312 xuống 0.0102, tiết kiệm **$49.50/tháng** theo catalog. Đây là đề xuất cần kiểm tra thêm compatibility/runtime trước khi triển khai thật.
- `job-infer-rag` và `job-infer-search` không có GPU rẻ hơn thỏa đồng thời điều kiện HBM và bandwidth nên giữ nguyên.

Tổng scenario MBU savings là **$913.50/tháng**. Khoản này được báo cáo riêng, không cộng vào headline M5 vì có thể chồng lấn với lever right-sizing util-lies.

## 4. Extension 4: Ngân sách Reasoning

Reasoning traffic gồm 201/2,400 request (**8.4%**) nhưng chiếm 1,241,156/7,533,027 token (**16.5%**). Nó tạo ra **$1.40**, tương đương 16.5% chi phí inference optimized, nhưng tiêu thụ **29,787.74 Wh**, khoảng **94.0%** tổng năng lượng. Nguyên nhân là `wh_per_query()` áp dụng hệ số năng lượng 80× cho reasoning.

Mình mô phỏng policy cap ở **10% tổng token**: giữ các request reasoning có tổng token lớn nhất và chuyển phần còn lại sang non-reasoning. Theo cách generator tạo dữ liệu, output reasoning được quy đổi về 1/6 trong counterfactual. Scenario này tiết kiệm khoảng **$0.33** và **11,630.82 Wh** trên traffic một ngày. Policy thực tế nên chỉ bật reasoning cho task có độ phức tạp hoặc độ tin cậy thấp, thay vì bật mặc định.

## 5. Sustainability và khuyến nghị

Một query 800 token tương ứng khoảng **0.24 Wh** và **0.091 gCO2e** ở `us-east-1`. `europe-north1` là vùng sạch nhất theo carbon intensity; `us-east-wa` có giá điện thấp nhất. Vì hai mục tiêu không trùng nhau, workload interruptible có thể ưu tiên vùng sạch khi mục tiêu là giảm phát thải, còn lựa chọn cuối cùng cần cân nhắc thêm latency và vị trí người dùng.

Ba hành động ưu tiên:

1. Bật cascade cho request dễ, prompt caching cho prefix lặp lại và Batch API cho traffic không yêu cầu realtime.
2. Dùng spot kèm checkpoint cho job interruptible, reserved cho workload có duty cycle ổn định; không commit reserved trước khi kiểm tra điểm hòa vốn.
3. Đưa MFU/MBU, idle hours, reasoning token share và tag coverage vào dashboard FinOps; dùng chúng làm điều kiện trước khi right-size hoặc chargeback.

> Tất cả số liệu là snapshot synthetic tháng 6/2026. Cần re-baseline giá, interruption rate, compatibility và carbon intensity trước khi áp dụng production.
