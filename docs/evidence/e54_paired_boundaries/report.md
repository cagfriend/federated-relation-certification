# STL-10 同场景配对与规模边界

全图边核对 270,950,400 次，Demand 请求边核对 16,603,500 次。通过核对的计时进程 384 次，含补测。

| 配置 | 种子组 | 有效块 | 完整头部均值最低 | D 对 B 省时 | D 对 E 省时 | Demand 对 D 省时 |
|---|---|---:|---|---:|---:|---:|
| 2021_iid_m512 | historical | 4/4 | B | -2.68% | -0.27% | -0.36% |
| 2021_iid_m4096 | historical | 4/4 | Demand | +13.70% | +4.67% | +2.39% |
| 2021_iid_m16384 | historical | 4/4 | Demand | -6.94% | -0.83% | +57.21% |
| 2021_dirichlet_0.1_m512 | historical | 4/4 | Demand | +2.89% | +2.67% | +2.30% |
| 2021_dirichlet_0.1_m4096 | historical | 4/4 | Demand | +5.52% | +4.69% | +5.56% |
| 2021_dirichlet_0.1_m16384 | historical | 4/4 | Demand | -11.66% | -0.65% | +59.17% |
| 2022_iid_m512 | historical | 4/4 | B | -10.05% | -3.29% | +7.94% |
| 2022_iid_m4096 | historical | 4/4 | Demand | +8.88% | +5.15% | +1.58% |
| 2022_iid_m16384 | historical | 4/4 | Demand | -13.08% | +2.62% | +59.65% |
| 2022_dirichlet_0.1_m512 | historical | 4/4 | Demand | +3.03% | +2.75% | +3.24% |
| 2022_dirichlet_0.1_m4096 | historical | 4/4 | Demand | +5.11% | +7.53% | +11.49% |
| 2022_dirichlet_0.1_m16384 | historical | 4/4 | Demand | -9.27% | -2.13% | +57.54% |
| 2023_iid_m512 | historical | 4/4 | B | -8.61% | -1.64% | +6.87% |
| 2023_iid_m4096 | historical | 4/4 | Demand | +7.34% | +1.74% | +5.45% |
| 2023_iid_m16384 | historical | 4/4 | Demand | -5.20% | +5.24% | +55.34% |
| 2023_dirichlet_0.1_m512 | historical | 4/4 | B | -7.13% | -3.33% | +4.25% |
| 2023_dirichlet_0.1_m4096 | historical | 4/4 | D | +10.25% | +7.18% | -3.47% |
| 2023_dirichlet_0.1_m16384 | historical | 4/4 | Demand | -20.63% | -7.60% | +60.98% |
| 2024_iid_m4096 | fresh | 4/4 | Demand | +10.00% | +2.82% | +0.97% |
| 2024_dirichlet_0.1_m4096 | fresh | 4/4 | Demand | +8.74% | +3.54% | +4.47% |
| 2025_iid_m4096 | fresh | 4/4 | Demand | +1.29% | +1.05% | +6.76% |
| 2025_dirichlet_0.1_m4096 | fresh | 4/4 | Demand | +11.32% | +8.05% | +10.80% |
| 2026_iid_m4096 | fresh | 4/4 | Demand | +9.20% | +2.35% | +6.09% |
| 2026_dirichlet_0.1_m4096 | fresh | 4/4 | Demand | +7.81% | +4.47% | +6.19% |

## M4096 新种子确认

- iid，D/B 达标种子 2/3，划分判定达标。
- iid，D/E 达标种子 0/3，划分判定未达标。
- dirichlet_0.1，D/B 达标种子 3/3，划分判定达标。
- dirichlet_0.1，D/E 达标种子 3/3，划分判定达标。

完整头部包含初始化和全部训练轮。省时为右侧方法耗时减左侧方法耗时。完整头部是整个配置的耗时。client_widths.csv 报告逐客户端教师端点及对应打分 MACs。出于可重复性，进程峰值和计时筛选记录保留在 runs.csv。
