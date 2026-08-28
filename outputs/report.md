# NimbusAI — GPU Cost Optimization Report

**Period:** monthly  
**Baseline spend:** $27,133  
**Optimized spend:** $14,626  
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

## Recommended actions

1. Ưu tiên cascade + cache + batch cho inference; M2 giảm 82.6% và tiết kiệm khoảng $1,212/tháng.
2. Dùng spot có checkpoint cho workload interruptible và reserved cho workload ổn định; scenario purchasing tiết kiệm khoảng $10,040/tháng.
3. Theo dõi MFU/MBU thay vì chỉ GPU-Util, tắt GPU idle và cân nhắc right-sizing MBU ($914/tháng trong scenario riêng).

_Figures are June-2026 as-of snapshots; re-baseline before acting._