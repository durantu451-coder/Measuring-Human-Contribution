# Strict-CF3 Tiny Experiment — 本地黑盒压缩与表面启发式对照

> **状态：完成，但仅为 exploratory derivative，不是正式五-CF 结论，也不含 strict white-box φ。**  
> 生成时间：2026-09-09；本地评分阶段零新增 API、零 GPU。所有评分均来自已冻结的 detached Wave1。

## 1. 研究问题与结论摘要

本实验回答两个窄问题：

1. 将旧 shared-source CF 改为每个 actual output 独立构造的 output-conditioned strict CF 后，黑盒压缩分数是否仍与 lexical overlap 高度相似？
2. 黑盒分数是否表现出 simple overlap 或 simple length 无法解释的明显优势？

**结论：**

- strict CF3 后，黑盒压缩与 lexical overlap 仍高度相似；该模式跨生成模型、跨领域并在 common-source 平衡核心中复现。
- 没有发现黑盒在 designed-gradient、单调率或 η² 上优于 overlap。相反，多个 lexical heuristic 在这些描述性指标上明显更好。
- 因此，不能再声称黑盒方法“超越 overlap”或测到了 overlap 之外的独立语义构念。
- 黑盒也不是简单的 prompt 长度：CF3 contrast 的 macro within-level ρ 只有 `0.203`（prompt bytes）/`0.167`（prompt words），远低于 lexical overlap 的约 `0.91–0.92`。但 prompt/output 长度比仍与黑盒高度相关（`ρ≈0.867`），说明相对长度是机制的一部分。
- output-conditioned CF subtraction 并不自动提升 designed-gradient fidelity。本实验中 L2 CF baseline 的均值高于 L3，导致 pooled 黑盒 contrast 出现明显 L2→L3 reversal；这是描述性均值差异，不是单独的显著性检验。

最合适的贡献定位不是“精度优于 overlap/white-box”，而是：

> 一个确定性、无需训练、无需 tokenizer/logits/model weights、基于字节描述长度的 operational proxy；这个单一分数与多尺度 lexical retention 及相对长度信号共同变化，并具有模型内部访问和计算部署方面的结构性优势。

## 2. 冻结数据与可复现性

### 2.1 Wave1 主样本

- 1,449 model-items
- 7,245 actual level rows
- 21,735 CF pairs（每个 level 使用有序 CF1–CF3）
- 737 underlying source clusters

生成模型：

| 模型 | model-items |
|---|---:|
| Gemini-3.6-Flash | 456 |
| GPT-5.5 | 334 |
| GPT-5.6-sol | 659 |

领域：

| 领域 | model-items |
|---|---:|
| Arxiv | 298 |
| News | 550 |
| Patent | 273 |
| Poetry | 328 |

主样本是“冻结时五个 level 均已达到 reconstruction+CF1–CF3”的全部 item，故存在 completion-order imbalance。

### 2.2 Common-source 平衡核心

从 Arxiv、News、Patent 中，只选择同时存在于三个生成模型的 source hash，并在每个领域按冻结 SHA-256 rank 取相同数量：

- 每领域 14 个共同 source
- 42 source clusters
- 126 model-items（42×3 models）
- 630 level rows

可用共同 source 数：Arxiv 27、News 160、Patent 14，因此 quota 由 Patent 的 14 决定。

### 2.3 关键证据哈希

- detached checkpoint inventory：`7d3ff632b4076981f6ea8bbaee25f92b2877dc3bfd8ae6dbf6bc92b42e19bd9f`
- Wave1 snapshot root：`f38983983b558a4c0f1d2e25b90cf2ac95ba6bd6122b20d820050830b673c976`
- Wave1 rows：`a5e1aeebeb396bb810072a072abfed1bc067e0a1a21dbcef95d7ff4a29d38d4f`
- final output manifest：`3a8800265be88478dc2fa4a66e06d40b0ede40d661c9d349527fb28867a736c3`
- matched scored rows：`53c85773df36fde739f2463487838bbe13fb5301d9569f24adf335702be90b1e`
- postanalysis：`2f6ecea83059281a87878f83966370a3eae77a56185f925dea55d983bb848211`

> 注：final output manifest 的 SHA 应以文件当前字节复核为准；本报告 manifest 会再次绑定该输入。

## 3. Estimand

对黑盒分数 `B` 和每个 heuristic `H` 同时报两组匹配比较：

```text
raw/raw:
    B_actual vs H_actual

shared-CF3 matched contrast:
    B_actual - fmean(B_cf1, B_cf2, B_cf3)
    vs
    H_actual - fmean(H_cf1, H_cf2, H_cf3)
```

第二组称为 **shared-CF3 matched contrast**，不称为已验证的独立 adjustment。两个轴都减去了同一组三个 CF 文本的函数，共享控制可能诱导额外协方差。

## 4. 黑盒与 heuristic 的直接关系

### 4.1 全部 1,449 items

下表为黑盒与 heuristic 的 Spearman ρ。CI 是 1,000 次 domain-stratified source-cluster percentile bootstrap。

| Heuristic | Raw macro within-level ρ | CF3 contrast macro within-level ρ | 95% CI | CF3 item-centered ρ | 95% CI |
|---|---:|---:|---:|---:|---:|
| Word-type coverage | 0.9165 | **0.9170** | [0.9109, 0.9221] | 0.9440 | [0.9408, 0.9472] |
| Word-token coverage | 0.9209 | **0.9224** | [0.9164, 0.9270] | 0.8812 | [0.8750, 0.8877] |
| Word-bigram coverage | 0.7603 | 0.8079 | [0.7966, 0.8179] | 0.9215 | [0.9174, 0.9255] |
| Character-5 coverage | 0.9037 | **0.9164** | [0.9102, 0.9216] | 0.9440 | [0.9410, 0.9470] |
| ROUGE-L recall | 0.9186 | **0.9060** | [0.8989, 0.9116] | 0.9194 | [0.9153, 0.9238] |
| Prompt/output byte ratio | 0.8028 | 0.8670 | [0.8588, 0.8746] | 0.8135 | [0.8035, 0.8230] |
| Prompt bytes | 0.0324 | 0.2033 | — | 0.4280 | — |
| Prompt words | 0.0458 | 0.1670 | — | 0.4169 | — |

Pooled ρ 更高，例如 raw word-type `0.9835`，但它包含设计等级梯度，不能当作 within-level item agreement。上表将 macro within-level 作为主要机制诊断。

### 4.2 Common-source 平衡核心

| Heuristic | CF3 contrast macro within-level ρ | 95% CI | CF3 item-centered ρ | 95% CI |
|---|---:|---:|---:|---:|
| Word-type coverage | **0.9055** | [0.8824, 0.9182] | 0.9305 | [0.9124, 0.9434] |
| Word-token coverage | **0.9027** | [0.8749, 0.9189] | 0.8422 | [0.8146, 0.8680] |
| Word-bigram coverage | 0.7929 | [0.7502, 0.8237] | 0.8982 | [0.8774, 0.9162] |
| Character-5 coverage | **0.9094** | [0.8863, 0.9233] | 0.9228 | [0.9078, 0.9353] |
| ROUGE-L recall | 0.8868 | [0.8579, 0.9044] | 0.8872 | [0.8643, 0.9068] |
| Prompt/output byte ratio | 0.8757 | [0.8516, 0.8908] | 0.7594 | [0.7218, 0.7946] |
| Prompt bytes | 0.1657 | — | 0.3939 | — |
| Prompt words | 0.1389 | — | 0.3844 | — |

平衡核心与全样本的高相关结论一致，说明在共同 source 且模型/领域组成受控的敏感性子集中仍可复现；但该核心仍以 Wave1 CF3-ready 为条件，不能完全排除 completion-order selection。

## 5. 分层稳健性

以下是 1,449-item 全样本的描述性分层点估计，不是 common-source 平衡核心结果，也没有分层 bootstrap CI；不能把平衡核心的 42-cluster uncertainty 外推到这些表格。

### 5.1 按生成模型：CF3 contrast 与 word-token coverage 的 macro within-level ρ

| 模型 | ρ |
|---|---:|
| Gemini-3.6-Flash | 0.8659 |
| GPT-5.5 | 0.9034 |
| GPT-5.6-sol | 0.8980 |

### 5.2 按领域

| 领域 | ρ |
|---|---:|
| Arxiv | 0.8885 |
| News | 0.9455 |
| Patent | 0.9101 |
| Poetry | 0.9131 |

所有分层均为强正相关，不能把总体结果归因于单一模型或领域。

## 6. Designed-gradient：overlap 优于黑盒，而非相反

### 6.1 全样本 CF3 contrast

| 指标 | Designed-level ρ | η² | 完全非递增率 | mean per-item τ-b |
|---|---:|---:|---:|---:|
| **黑盒压缩** | 0.6341 | 0.5317 | 22.08% | 0.6073 |
| Word-type coverage | 0.7928 | 0.6609 | 33.54% | 0.7684 |
| Word-token coverage | **0.8544** | **0.6924** | **48.03%** | **0.8374** |
| Character-5 coverage | 0.7918 | 0.6451 | 37.47% | 0.7727 |
| ROUGE-L recall | 0.8191 | 0.6621 | 39.68% | 0.7941 |

### 6.2 Common-source 核心

| 指标 | Designed-level ρ | η² | 完全非递增率 | mean per-item τ-b |
|---|---:|---:|---:|---:|
| **黑盒压缩** | 0.6049 | 0.5338 | 16.67% | 0.5683 |
| Word-type coverage | 0.7818 | 0.6492 | 27.78% | 0.7381 |
| Word-token coverage | **0.8693** | **0.6983** | **47.62%** | **0.8365** |
| Character-5 coverage | 0.8074 | 0.6557 | 34.92% | 0.7746 |
| ROUGE-L recall | 0.8259 | 0.6428 | 34.92% | 0.7794 |

这些是 investigator-designed treatment gradient 的描述性指标，不是人工标签或外部有效性标准。它们不支持“黑盒在该实验设计下具有更高 designed-gradient concordance”的主张，并与基于这些 observables 的精度优势叙事相反。

## 7. Strict CF baseline 与 L2→L3 reversal

### 7.1 黑盒 level means（全样本）

| Level | Actual mean | CF1 | CF2 | CF3 | CF mean | CF3 contrast |
|---|---:|---:|---:|---:|---:|---:|
| L1 | 0.5613 | 0.1862 | 0.1840 | 0.1764 | 0.1822 | 0.3791 |
| L2 | 0.3448 | 0.2927 | 0.2418 | 0.2427 | **0.2591** | **0.0857** |
| L3 | 0.3371 | 0.1592 | 0.1480 | 0.1513 | **0.1529** | **0.1842** |
| L4 | 0.1598 | 0.1196 | 0.1071 | 0.1021 | 0.1096 | 0.0502 |
| L5 | 0.0864 | 0.1208 | 0.1175 | 0.1162 | 0.1182 | −0.0318 |

Actual L2 与 L3 很接近但仍是 L2>L3；CF subtraction 后变成 L2≪L3。直接原因是 L2 的 output-conditioned CF baseline 比 L3 高约 `0.1062`。

L2 的 CF1 槽位均值确实较高（0.2927），但 CF2/CF3 约 0.242，仍明显高于 L3 的约 0.148–0.151，因此 pooled reversal 不是由单一 CF1 槽造成。由于 CF1–CF3 是有序且非随机的，不能将该槽位差异解释为已识别的因果位置效应。

### 7.2 按模型

| 模型 | Actual L2 | Actual L3 | Contrast L2 | Contrast L3 | 解释 |
|---|---:|---:|---:|---:|---|
| Gemini | 0.2537 | 0.2484 | −0.0349 | 0.1577 | subtraction 诱发 reversal |
| GPT-5.5 | 0.4267 | 0.3161 | 0.2106 | 0.1639 | 无 reversal |
| GPT-5.6-sol | 0.3663 | 0.4090 | 0.1060 | 0.2129 | actual 已 reversal，subtraction 放大 |

pooled reversal 与 Gemini 中的 subtraction-induced reversal 成立；GPT-5.6-sol 的 actual 已有 L2<L3，不能将其 reversal 归因于 CF subtraction。

## 8. 对“优势/贡献”的最终判断

### 8.1 不再成立的优势

不能声称：

- 黑盒压缩测量了 lexical overlap 之外的明显独立结构；
- 黑盒比 overlap 更符合 L1–L5 设计梯度；
- strict CF subtraction 已被证明提高测量有效性；
- 当前 CF3 contrast 与 human contribution ground truth 一致；
- 1,449 条 partial-completion 样本代表完整五模型正式 cohort。

### 8.2 仍然成立、且与全文 storyline 兼容的贡献

1. **Access contribution**：raw compression scorer 在 prompt/output 文本已经可用后，不需要 logits、token probabilities、model weights、tokenizer 或 evaluator GPU；本报告的 strict contrast 还需要预先生成三条 CF 文本，但对这些文本做评分时同样不调用 learned evaluator。
2. **Training-free operational proxy**：没有训练一个 learned overlap model，也不依赖人工标注；固定压缩器和 framing 即可确定性重算。
3. **多尺度描述长度视角**：单一 byte-level score 与 word type、word token、word bigram、character n-gram、ROUGE-L 和相对长度共同变化，不需要在评分阶段固定某个模型 tokenizer；这是一种 observed co-variation，不是已识别的信号分解或因果整合。
4. **跨模型/领域 subgroup robustness**：黑盒–overlap 关系在三个生成模型和四个领域中都保持强正相关，说明该共变模式不是只出现在单一已观察切片；这不是对未观察模型/领域的 transportability 证明，也不单独确立机制或构念有效性。
5. **不是单一绝对长度代理**：prompt bytes/words 的 within-level 解释力很低；但相对长度比很重要，应诚实纳入关联模式解释。
6. **Counterfactual methodology contribution**：本样本显示 output-conditioned CF 不是无害的“去偏”步骤；CF construction 改变 estimand，并可能削弱原设计梯度。论文应将 raw score 与 strict contrast 并列，而不是默认后者必然更有效。
7. **Reproducibility contribution**：完整 frozen roster、eligibility ledger、detached inventories、wave chain、exact compressor arithmetic 与 source-cluster bootstrap 均有哈希约束。

## 9. 推荐论文叙事

建议写成：

> We introduce a deterministic description-length proxy for human guidance in AI-assisted generation. Once prompt and output texts are available, raw scoring avoids learned evaluators, token probabilities, model weights, and tokenizer-specific instrumentation; the strict contrast additionally consumes three pre-generated counterfactual texts per level. Across the three sampled generators and four sampled domains, the score co-varies strongly with several lexical-retention measures within designed levels. This convergence characterizes an observed association rather than establishing superiority, causal mechanism, or transportability: simple lexical measures equal or exceed its designed-gradient concordance. Its contribution therefore lies in byte-level operationalization, scoring-stage access independence, reproducibility, and model-size-independent scoring—not in demonstrated semantic or criterion-validity dominance.

中文主线：

> 本文的 raw 黑盒压缩评分不是为了在所有统计指标上击败简单 overlap 或白盒模型，而是提供一个在文本已可用后无需模型内部访问、无需训练、可确定性复算的 operational measure；strict contrast 另需预先生成 CF 文本。机制诊断显示该分数在当前样本中与多尺度 lexical retention 和相对长度强烈共变；这一关联界定了方法可能在追踪什么，同时也约束了不能提出的构念有效性、因果机制与跨分布可移植性主张。

## 10. 局限与后续

- 当前没有 strict white-box φ，因此不能比较黑盒与白盒谁更接近共同构念。
- 两个 contrast 轴共享相同 CF 文本，相关性可能包含 shared-control covariance。
- 只使用有序 CF1–CF3；L2 的 CF1 槽位均值较高，但因槽位非随机，位置敏感性尚未被识别。
- 全样本 completion-order 不平衡；common-source 核心只有 42 个 source clusters，CI 更宽。
- L1–L5 是 investigator-designed treatments，不是 human labels。
- 正式五-CF campaign 完成后，应在 immutable final lineage 上复算同样的 raw/strict 对照，并加入 strict white-box evaluator；在此之前，本报告只能作为机制与方向筛选证据。
