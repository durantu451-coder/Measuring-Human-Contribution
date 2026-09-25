# Table 4. Cross-fitted length-residualized robustness

Evaluator comparisons residualize candidate and evaluator independently using the same source-grouped folds. `residual_candidate_vs_raw_treatment_ordinal` instead compares residualized R to the unchanged designed ordinal labels, as frozen; it is not a two-sided partial correlation.

| Length specification | Candidate vs evaluator | Macro rho / alpha_z | Item-centered rho / alpha_z |
|---|---|---:|---:|
| byte_L_full | G_raw_bits_per_output_byte_vs_phi_actual_llama | 0.365583 / 0.417624 | 0.766720 / 0.796922 |
| byte_L_full | G_raw_bits_per_output_byte_vs_phi_actual_mixtral | 0.335613 / 0.392403 | 0.769453 / 0.798783 |
| byte_L_full | G_raw_bits_vs_phi_actual_llama | 0.284133 / 0.330106 | 0.693087 / 0.722634 |
| byte_L_full | G_raw_bits_vs_phi_actual_mixtral | 0.253156 / 0.298236 | 0.691373 / 0.725757 |
| byte_L_full | R_actual_vs_phi_actual_llama | 0.516988 / 0.560275 | 0.809143 / 0.835589 |
| byte_L_full | R_actual_vs_phi_actual_mixtral | 0.507980 / 0.550275 | 0.820204 / 0.845420 |
| byte_L_full | residual_candidate_vs_raw_treatment_ordinal | NA / NA | 0.171703 / 0.167507 |
| byte_L_out | G_raw_bits_per_output_byte_vs_phi_actual_llama | 0.691030 / 0.705966 | 0.952820 / 0.949178 |
| byte_L_out | G_raw_bits_per_output_byte_vs_phi_actual_mixtral | 0.660034 / 0.677672 | 0.951607 / 0.950693 |
| byte_L_out | G_raw_bits_vs_phi_actual_llama | 0.392620 / 0.414730 | 0.909295 / 0.871254 |
| byte_L_out | G_raw_bits_vs_phi_actual_mixtral | 0.369472 / 0.405859 | 0.907137 / 0.872413 |
| byte_L_out | R_actual_vs_phi_actual_llama | 0.763598 / 0.786787 | 0.954666 / 0.957319 |
| byte_L_out | R_actual_vs_phi_actual_mixtral | 0.735424 / 0.770281 | 0.955724 / 0.961679 |
| byte_L_out | residual_candidate_vs_raw_treatment_ordinal | NA / NA | 0.912395 / 0.892026 |

## Direct paired residual R-minus-raw-gain contrasts

| Contrast ID | Point | 95% paired cluster-bootstrap CI |
|---|---:|---:|
| length_delta|byte_L_full|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|item_centered|pairwise_continuous_alpha_z | 0.038666 | [0.035227, 0.042544] |
| length_delta|byte_L_full|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|item_centered|rho | 0.042423 | [0.038905, 0.046161] |
| length_delta|byte_L_full|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|pairwise_continuous_alpha_z | 0.142651 | [0.134074, 0.151752] |
| length_delta|byte_L_full|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|rho | 0.151405 | [0.143116, 0.159696] |
| length_delta|byte_L_full|phi_actual_llama|R_actual-minus-G_raw_bits|item_centered|pairwise_continuous_alpha_z | 0.112955 | [0.107652, 0.118211] |
| length_delta|byte_L_full|phi_actual_llama|R_actual-minus-G_raw_bits|item_centered|rho | 0.116056 | [0.111344, 0.120852] |
| length_delta|byte_L_full|phi_actual_llama|R_actual-minus-G_raw_bits|macro_within_level|pairwise_continuous_alpha_z | 0.230169 | [0.220097, 0.240294] |
| length_delta|byte_L_full|phi_actual_llama|R_actual-minus-G_raw_bits|macro_within_level|rho | 0.232855 | [0.222999, 0.242519] |
| length_delta|byte_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|item_centered|pairwise_continuous_alpha_z | 0.046637 | [0.042722, 0.051004] |
| length_delta|byte_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|item_centered|rho | 0.050751 | [0.046626, 0.054941] |
| length_delta|byte_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|pairwise_continuous_alpha_z | 0.157871 | [0.148586, 0.167766] |
| length_delta|byte_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|rho | 0.172367 | [0.163320, 0.182093] |
| length_delta|byte_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits|item_centered|pairwise_continuous_alpha_z | 0.119663 | [0.113351, 0.125302] |
| length_delta|byte_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits|item_centered|rho | 0.128831 | [0.123017, 0.134319] |
| length_delta|byte_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits|macro_within_level|pairwise_continuous_alpha_z | 0.252038 | [0.241849, 0.262504] |
| length_delta|byte_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits|macro_within_level|rho | 0.254824 | [0.243414, 0.265601] |
| length_delta|byte_L_out|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|item_centered|pairwise_continuous_alpha_z | 0.008141 | [0.007487, 0.008837] |
| length_delta|byte_L_out|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|item_centered|rho | 0.001846 | [0.001283, 0.002415] |
| length_delta|byte_L_out|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|pairwise_continuous_alpha_z | 0.080822 | [0.076099, 0.085381] |
| length_delta|byte_L_out|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|rho | 0.072568 | [0.068108, 0.077056] |
| length_delta|byte_L_out|phi_actual_llama|R_actual-minus-G_raw_bits|item_centered|pairwise_continuous_alpha_z | 0.086065 | [0.083033, 0.089307] |
| length_delta|byte_L_out|phi_actual_llama|R_actual-minus-G_raw_bits|item_centered|rho | 0.045371 | [0.042860, 0.048290] |
| length_delta|byte_L_out|phi_actual_llama|R_actual-minus-G_raw_bits|macro_within_level|pairwise_continuous_alpha_z | 0.372057 | [0.363770, 0.381042] |
| length_delta|byte_L_out|phi_actual_llama|R_actual-minus-G_raw_bits|macro_within_level|rho | 0.370978 | [0.363211, 0.378709] |
| length_delta|byte_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|item_centered|pairwise_continuous_alpha_z | 0.010986 | [0.010218, 0.011753] |
| length_delta|byte_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|item_centered|rho | 0.004118 | [0.003516, 0.004697] |
| length_delta|byte_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|pairwise_continuous_alpha_z | 0.092608 | [0.087467, 0.097711] |
| length_delta|byte_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|rho | 0.075390 | [0.070525, 0.080375] |
| length_delta|byte_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits|item_centered|pairwise_continuous_alpha_z | 0.089266 | [0.086100, 0.092320] |
| length_delta|byte_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits|item_centered|rho | 0.048588 | [0.046238, 0.051273] |
| length_delta|byte_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits|macro_within_level|pairwise_continuous_alpha_z | 0.364422 | [0.356065, 0.373165] |
| length_delta|byte_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits|macro_within_level|rho | 0.365951 | [0.357500, 0.374614] |

## Persistence after length control

| Length specification | Baseline | Classification | Relative to unadjusted |
|---|---|---|---|
| byte_L_full | G_raw_bits | stable_positive | persists |
| byte_L_full | G_raw_bits_per_output_byte | stable_positive | persists |
| byte_L_out | G_raw_bits | stable_positive | persists |
| byte_L_out | G_raw_bits_per_output_byte | stable_positive | persists |
