# Actual-only 增量与敏感性分析报告

## 冻结的主要分析

- Llama↔Mixtral 的五层宏平均：Spearman rho=0.909605，`pairwise_continuous_alpha_z`=0.921605。
- Llama↔Mixtral 的item-centered结果：Spearman rho=0.991600，`pairwise_continuous_alpha_z`=0.992186。
- Ridge中H+R相对H的冻结分类：`stable_positive`。
- R相对raw G的总体分类：`stable_positive`（white-box convergence：`stable_positive`；treatment construct：`stable_positive`）。

## 次要分析

归一化R、raw gain、冻结heuristics、evaluator ordering、pooled结果和预声明subgroup均完整报告，不按结果筛选。
strongest-single模型明确属于辅助分析，不是六个冻结primary predictor sets之一；其R-only差值也使用同一paired source-cluster bootstrap。

## 稳健性分析

- 固定HGB中H+R相对H的分类：`mixed_or_inconclusive`。
- byte output-only长度残差化是主要稳健性规格；full-byte以及word-length规格是敏感性检查。`residual_candidate_vs_raw_treatment_ordinal`保持treatment labels不变，仅残差化R；它不是双侧partial correlation。
- byte L_out下R相对raw G：`stable_positive`，相对未调整结论为`persists`。

## 探索性分析

- all-five 1.25 common-support推断策略：`coverage_only`。

## 不支持的主张

这些结果不建立criterion truth、语义效度、因果效度、普遍优越性，也不代表相对于独立人工标注ground truth的可靠性。L1–L5是investigator-specified ordinal treatment labels。

本分析未调用API、未联网、未使用GPU、未生成或重生成文本、未读取完整prompt/output正文、未重新压缩、未使用counterfactual字段，也未修改Word。资源约束为`sampled_process_rss_hard_limit`（50 ms采样并在退出时同步复测），不声称捕获采样间隔内所有瞬时峰值。
