# Table 3. White-box evaluator sensitivity and consensus

| Scope | Spearman rho | pairwise_continuous_alpha_z | N |
|---|---:|---:|---:|
| pooled | 0.987569 | 0.990289 | 56,110 |
| macro_within_level | 0.909605 | 0.921605 | 11,222 |
| item_centered | 0.991600 | 0.992186 | 56,110 |
| level:L1 | 0.964287 | 0.974955 | 11,222 |
| level:L2 | 0.923119 | 0.931460 | 11,222 |
| level:L3 | 0.965545 | 0.970754 | 11,222 |
| level:L4 | 0.952128 | 0.948531 | 11,222 |
| level:L5 | 0.742944 | 0.782323 | 11,222 |
| by_domain:arxiv | 0.987832 | 0.990991 | 14,685 |
| by_domain:news | 0.988877 | 0.992077 | 14,280 |
| by_domain:patent | 0.989549 | 0.989878 | 13,800 |
| by_domain:poetry | 0.984055 | 0.990305 | 13,345 |
| by_generation_model:claude-opus-4-8 | 0.987002 | 0.990128 | 9,460 |
| by_generation_model:claude-sonnet-5 | 0.985174 | 0.990946 | 11,600 |
| by_generation_model:gemini-3.6-flash | 0.982932 | 0.988554 | 11,200 |
| by_generation_model:gpt-5.5 | 0.987506 | 0.991440 | 12,230 |
| by_generation_model:gpt-5.6-sol | 0.984109 | 0.988299 | 11,620 |

## Exact evaluator ordering

| Pair | Concordant | Discordant | Tied either | Inversion rate (all / non-tie) | R same-sign on concordant non-ties |
|---|---:|---:|---:|---:|---:|
| all_ten:L1-L2 | 10,748 | 474 | 0 | 0.042238 / 0.042238 | 0.950130 |
| all_ten:L1-L3 | 11,094 | 128 | 0 | 0.011406 / 0.011406 | 0.981522 |
| all_ten:L1-L4 | 11,196 | 26 | 0 | 0.002317 / 0.002317 | 0.998035 |
| all_ten:L1-L5 | 11,203 | 19 | 0 | 0.001693 / 0.001693 | 0.999464 |
| all_ten:L2-L3 | 10,746 | 476 | 0 | 0.042417 / 0.042417 | 0.878373 |
| all_ten:L2-L4 | 11,220 | 2 | 0 | 0.000178 / 0.000178 | 0.995722 |
| all_ten:L2-L5 | 11,220 | 2 | 0 | 0.000178 / 0.000178 | 0.998307 |
| all_ten:L3-L4 | 11,143 | 79 | 0 | 0.007040 / 0.007040 | 0.986718 |
| all_ten:L3-L5 | 11,160 | 62 | 0 | 0.005525 / 0.005525 | 0.997133 |
| all_ten:L4-L5 | 9,979 | 1,243 | 0 | 0.110765 / 0.110765 | 0.916725 |
| adjacent_four:L1-L2 | 10,748 | 474 | 0 | 0.042238 / 0.042238 | 0.950130 |
| adjacent_four:L2-L3 | 10,746 | 476 | 0 | 0.042417 / 0.042417 | 0.878373 |
| adjacent_four:L3-L4 | 11,143 | 79 | 0 | 0.007040 / 0.007040 | 0.986718 |
| adjacent_four:L4-L5 | 9,979 | 1,243 | 0 | 0.110765 / 0.110765 | 0.916725 |

## Strict L1>L2>L3>L4>L5 monotonicity

| Evaluator condition | Strictly monotonic items | Denominator | Rate |
|---|---:|---:|---:|
| Llama | 6,942 | 11,222 | 0.618606 |
| Mixtral | 7,062 | 11,222 | 0.629300 |
| Both | 6,158 | 11,222 | 0.548744 |

## Standardized evaluator disagreement

Global-z absolute difference: mean=0.101244; sample SD=0.095768. All subgroups reuse the one global z-standardization (`subgroups_use_global_z_not_restandardized=True`).

Quantiles (`method=linear`): q=0.00: 0.000002, q=0.10: 0.014126, q=0.25: 0.036699, q=0.50: 0.079225, q=0.75: 0.140349, q=0.90: 0.211236, q=0.95: 0.264608, q=0.99: 0.397641, q=1.00: 2.474593

| Subgroup | Mean absolute global-z difference |
|---|---:|
| level:L1 | 0.115753 |
| level:L2 | 0.128498 |
| level:L3 | 0.093556 |
| level:L4 | 0.068042 |
| level:L5 | 0.100370 |
| domain:arxiv | 0.098247 |
| domain:news | 0.103299 |
| domain:patent | 0.103598 |
| domain:poetry | 0.099908 |
| generation_model:claude-opus-4-8 | 0.102053 |
| generation_model:claude-sonnet-5 | 0.099202 |
| generation_model:gemini-3.6-flash | 0.075793 |
| generation_model:gpt-5.5 | 0.110123 |
| generation_model:gpt-5.6-sol | 0.117809 |

## R_actual against the two frozen evaluator consensuses

| Consensus | Scope | rho | pairwise_continuous_alpha_z |
|---|---|---:|---:|
| consensus_midrank_percentile | macro_within_level | 0.782211 | 0.791943 |
| consensus_midrank_percentile | item_centered | 0.957499 | 0.934238 |
| consensus_global_z | macro_within_level | 0.781516 | 0.801775 |
| consensus_global_z | item_centered | 0.966872 | 0.963639 |
