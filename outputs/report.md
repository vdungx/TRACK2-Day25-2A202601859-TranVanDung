# NimbusAI — GPU Cost Optimization Report

**Period:** monthly<br>
**Baseline spend:** $27,133<br>
**Optimized spend:** $14,626<br>
**Projected savings:** $12,507  (**46%**)

## Savings by lever

| Lever | Savings (USD) |
|---|---|
| Inference (cascade/cache/batch) | $1,212 |
| Purchasing (spot/reserved) | $10,040 |
| Right-size util-lies | $655 |
| Kill idle GPUs | $600 |

## Inference unit economics

- Token volume: 7,533,027 tokens/day
- Baseline: $6.488/1M-token
- Optimized: $1.126/1M-token
- Inference savings: 82.6%

## Sustainability

- Energy per query: 0.24 Wh
- Carbon per query: 0.091 gCO2e
- Cleanest region (carbon): europe-north1
- Cheapest electricity region: us-east-wa
- Electricity cost per query: $0.000029

## Extension 2 — MBU-aware right-sizing

Threshold: MBU <= 0.40. Candidates preserve HBM capacity and observed bandwidth.

| Workload | Current | Recommendation | MBU | $/GB current | $/GB target | Monthly savings |
|---|---|---|---:|---:|---:|---:|
| job-infer-chat | A10G | L4 | 0.268 | $0.0417 | $0.0333 | $864.00 |
| job-infer-rag | A100 | A100 | 0.262 | $0.0224 | $0.0224 | $0.00 |
| job-infer-search | L4 | L4 | 0.328 | $0.0333 | $0.0333 | $0.00 |
| job-batch-eval | H100 | MI300X | 0.372 | $0.0312 | $0.0102 | $49.50 |

Scenario savings: $913.50/month (reported separately from the M5 headline to avoid double-counting).

## Extension 4 — Reasoning budget

- Reasoning traffic: 201/2400 requests (8.4%), 16.5% of tokens
- Optimized reasoning cost: $1.40 (16.5% of optimized inference cost)
- Reasoning energy: 29,787.74 Wh (94.0% of total)
- 10% token-cap scenario: $0.33 and 11,630.82 Wh saved

## Extension 3 — KV-cache economics

- Cache policy enabled for 16/16 observed prefix groups
- Break-even: more than 1.11 repeat reads per prefix under the normalized write-cost assumption
- Measured cache savings: $1.1740/day

| Route tier | Groups | Enabled | Avg repeat reads | Break-even reads | Cache savings/day |
|---|---:|---:|---:|---:|---:|
| large | 8 | 8 | 61.25 | 1.11 | $0.9355 |
| small | 8 | 8 | 236.75 | 1.11 | $0.2385 |

## Extension 1 — Advanced purchasing policy

The advanced scenario adds GPU-specific interruption rates and selects the reserved term from observed job duration.

| Workload | GPU | Tier | Reserved term | Effective spot $/hr | Optimized/month |
|---|---|---|---|---:|---:|
| job-train-llm | H100 | spot | n/a | $1.5675 | $7,524 |
| job-train-embed | A100 | spot | n/a | $1.1605 | $1,393 |
| job-finetune | H100 | spot | n/a | $1.5675 | $564 |
| job-infer-chat | A10G | reserved | 1yr | n/a | $3,456 |
| job-infer-rag | A100 | reserved | 1yr | n/a | $3,024 |
| job-infer-search | L4 | reserved | 1yr | n/a | $1,296 |
| job-dev-sandbox | A10G | spot | n/a | $0.4280 | $205 |
| job-batch-eval | H100 | spot | n/a | $1.5675 | $141 |

Legacy savings: 39.1%; advanced savings: 31.4%; change: -7.7 percentage points.

## Extension 5 — Carbon-aware Scheduling

- Interruptible workload energy: 1,789.00 kWh
- Cleanest region: europe-north1; cheapest electricity: us-east-wa; balanced score: us-east-wa
- Moving interruptible jobs from us-east-1 to europe-north1 saves 626,150 gCO2e (92.1%) and changes electricity cost by $-53.67

| Region | $/kWh | gCO2/kWh | Electricity cost | Carbon |
|---|---:|---:|---:|---:|
| us-east-1 | $0.120 | 380 | $214.68 | 679,820 g |
| us-west-2 | $0.070 | 120 | $125.23 | 214,680 g |
| europe-north1 | $0.090 | 30 | $161.01 | 53,670 g |
| europe-central2 | $0.180 | 660 | $322.02 | 1,180,740 g |
| us-east-wa | $0.055 | 90 | $98.39 | 161,010 g |

| Interruptible job | GPU-hours | Baseline carbon | Clean carbon | Saved |
|---|---:|---:|---:|---:|
| job-train-llm | 2,240 | 595,840 g | 47,040 g | 548,800 g |
| job-train-embed | 200 | 30,400 g | 2,400 g | 28,000 g |
| job-finetune | 36 | 9,576 g | 756 g | 8,820 g |
| job-dev-sandbox | 352 | 20,064 g | 1,584 g | 18,480 g |
| job-batch-eval | 90 | 23,940 g | 1,890 g | 22,050 g |

## Recommended actions

1. Ưu tiên cascade + cache + batch cho inference; M2 giảm 82.6% và tiết kiệm khoảng $1,212/tháng.
2. Dùng spot có checkpoint cho workload interruptible và reserved cho workload ổn định; scenario purchasing tiết kiệm khoảng $10,040/tháng.
3. Theo dõi MFU/MBU thay vì chỉ GPU-Util, tắt GPU idle và cân nhắc right-sizing MBU ($914/tháng trong scenario riêng).
4. Bật cache theo prefix khi vượt break-even reads; M2 đo được $1.17/ngày cache savings.
5. Chuyển job interruptible sang europe-north1 có thể giảm 92.1% carbon; cân nhắc trade-off chi phí và latency.
6. Advanced purchasing thay đổi savings -7.7 điểm %, nên dùng duration và interruption rate thực tế trước khi commit.

_Figures are June-2026 as-of snapshots; re-baseline before acting._