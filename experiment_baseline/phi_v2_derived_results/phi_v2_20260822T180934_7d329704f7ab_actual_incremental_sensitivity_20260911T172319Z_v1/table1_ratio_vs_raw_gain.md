# Table 1. Normalized R_actual versus raw gain and frozen simple heuristics

All cells pair Spearman rho with `pairwise_continuous_alpha_z`.

| Candidate | Llama macro rho / alpha_z | Mixtral macro rho / alpha_z | Llama item-centered rho / alpha_z | Mixtral item-centered rho / alpha_z |
|---|---:|---:|---:|---:|
| R_actual | 0.770203 / 0.791854 | 0.760317 / 0.781658 | 0.965367 / 0.959934 | 0.964840 / 0.963579 |
| G_raw_bits | 0.212002 / 0.195338 | 0.183450 / 0.166247 | 0.728197 / 0.705819 | 0.734761 / 0.714154 |
| G_raw_bits_per_output_byte | 0.729121 / 0.731749 | 0.721169 / 0.724071 | 0.953200 / 0.940407 | 0.950604 / 0.939717 |
| C_y_bits | -0.472797 / -0.431606 | -0.492319 / -0.455181 | -0.211718 / -0.254101 | -0.206927 / -0.243725 |
| prompt_to_output_byte_ratio | 0.599186 / 0.634646 | 0.590069 / 0.622059 | 0.921688 / 0.908773 | 0.910760 / 0.889110 |
| rouge_l_recall | 0.800192 / 0.799095 | 0.786613 / 0.796244 | 0.972319 / 0.969107 | 0.970819 / 0.970908 |
| word_token_coverage | 0.750080 / 0.763823 | 0.735093 / 0.757351 | 0.972199 / 0.977236 | 0.968657 / 0.972933 |
| char5_coverage | 0.741589 / 0.751838 | 0.728414 / 0.752110 | 0.962944 / 0.960404 | 0.961021 / 0.961937 |

## Direct paired R-minus-baseline bootstrap contrasts

| Contrast | Reference | Scope | Metric | Point | 95% paired cluster-bootstrap CI |
|---|---|---|---|---:|---:|
| R_actual-minus-G_raw_bits_per_output_byte | consensus_rank | item_centered | pairwise_continuous_alpha_z | 0.022154 | [0.019919, 0.024655] |
| R_actual-minus-G_raw_bits_per_output_byte | consensus_rank | item_centered | rho | 0.014781 | [0.013776, 0.015764] |
| R_actual-minus-G_raw_bits_per_output_byte | consensus_rank | macro_within_level | pairwise_continuous_alpha_z | 0.062920 | [0.057893, 0.068420] |
| R_actual-minus-G_raw_bits_per_output_byte | consensus_rank | macro_within_level | rho | 0.040861 | [0.037173, 0.044794] |
| R_actual-minus-G_raw_bits_per_output_byte | consensus_z | item_centered | pairwise_continuous_alpha_z | 0.021735 | [0.019403, 0.024419] |
| R_actual-minus-G_raw_bits_per_output_byte | consensus_z | item_centered | rho | 0.013265 | [0.012235, 0.014346] |
| R_actual-minus-G_raw_bits_per_output_byte | consensus_z | macro_within_level | pairwise_continuous_alpha_z | 0.059765 | [0.054647, 0.065385] |
| R_actual-minus-G_raw_bits_per_output_byte | consensus_z | macro_within_level | rho | 0.040843 | [0.037141, 0.044774] |
| R_actual-minus-G_raw_bits_per_output_byte | llama | item_centered | pairwise_continuous_alpha_z | 0.019527 | [0.017318, 0.022011] |
| R_actual-minus-G_raw_bits_per_output_byte | llama | item_centered | rho | 0.012167 | [0.011187, 0.013223] |
| R_actual-minus-G_raw_bits_per_output_byte | llama | macro_within_level | pairwise_continuous_alpha_z | 0.060105 | [0.055125, 0.065389] |
| R_actual-minus-G_raw_bits_per_output_byte | llama | macro_within_level | rho | 0.041082 | [0.037537, 0.044703] |
| R_actual-minus-G_raw_bits_per_output_byte | mixtral | item_centered | pairwise_continuous_alpha_z | 0.023863 | [0.021337, 0.026775] |
| R_actual-minus-G_raw_bits_per_output_byte | mixtral | item_centered | rho | 0.014236 | [0.013162, 0.015371] |
| R_actual-minus-G_raw_bits_per_output_byte | mixtral | macro_within_level | pairwise_continuous_alpha_z | 0.057587 | [0.052189, 0.063358] |
| R_actual-minus-G_raw_bits_per_output_byte | mixtral | macro_within_level | rho | 0.039148 | [0.035202, 0.043247] |
| R_actual-minus-G_raw_bits_per_output_byte | treatment | item_centered | pairwise_continuous_alpha_z | 0.043883 | [0.041351, 0.046680] |
| R_actual-minus-G_raw_bits_per_output_byte | treatment | item_centered | rho | 0.036981 | [0.035569, 0.038307] |
| R_actual-minus-G_raw_bits_per_output_byte | treatment | pooled | pairwise_continuous_alpha_z | 0.048980 | [0.045860, 0.052427] |
| R_actual-minus-G_raw_bits_per_output_byte | treatment | pooled | rho | 0.033440 | [0.032203, 0.034570] |
| R_actual-minus-G_raw_bits | consensus_rank | item_centered | pairwise_continuous_alpha_z | 0.240299 | [0.233986, 0.246500] |
| R_actual-minus-G_raw_bits | consensus_rank | item_centered | rho | 0.225913 | [0.218653, 0.233252] |
| R_actual-minus-G_raw_bits | consensus_rank | macro_within_level | pairwise_continuous_alpha_z | 0.607642 | [0.595574, 0.619560] |
| R_actual-minus-G_raw_bits | consensus_rank | macro_within_level | rho | 0.581760 | [0.568783, 0.594330] |
| R_actual-minus-G_raw_bits | consensus_z | item_centered | pairwise_continuous_alpha_z | 0.252266 | [0.245296, 0.258999] |
| R_actual-minus-G_raw_bits | consensus_z | item_centered | rho | 0.234034 | [0.226681, 0.241419] |
| R_actual-minus-G_raw_bits | consensus_z | macro_within_level | pairwise_continuous_alpha_z | 0.618542 | [0.606296, 0.630589] |
| R_actual-minus-G_raw_bits | consensus_z | macro_within_level | rho | 0.580428 | [0.567643, 0.592975] |
| R_actual-minus-G_raw_bits | llama | item_centered | pairwise_continuous_alpha_z | 0.254114 | [0.246982, 0.261064] |
| R_actual-minus-G_raw_bits | llama | item_centered | rho | 0.237170 | [0.229490, 0.244878] |
| R_actual-minus-G_raw_bits | llama | macro_within_level | pairwise_continuous_alpha_z | 0.596516 | [0.584103, 0.608538] |
| R_actual-minus-G_raw_bits | llama | macro_within_level | rho | 0.558202 | [0.545382, 0.570652] |
| R_actual-minus-G_raw_bits | mixtral | item_centered | pairwise_continuous_alpha_z | 0.249426 | [0.242531, 0.255962] |
| R_actual-minus-G_raw_bits | mixtral | item_centered | rho | 0.230080 | [0.223051, 0.237076] |
| R_actual-minus-G_raw_bits | mixtral | macro_within_level | pairwise_continuous_alpha_z | 0.615412 | [0.602918, 0.626979] |
| R_actual-minus-G_raw_bits | mixtral | macro_within_level | rho | 0.576867 | [0.564182, 0.589073] |
| R_actual-minus-G_raw_bits | treatment | item_centered | pairwise_continuous_alpha_z | 0.171364 | [0.165500, 0.176999] |
| R_actual-minus-G_raw_bits | treatment | item_centered | rho | 0.143677 | [0.137573, 0.149607] |
| R_actual-minus-G_raw_bits | treatment | pooled | pairwise_continuous_alpha_z | 0.204558 | [0.198296, 0.210407] |
| R_actual-minus-G_raw_bits | treatment | pooled | rho | 0.145459 | [0.138565, 0.152341] |
| R_actual-minus-char5_coverage | consensus_rank | item_centered | pairwise_continuous_alpha_z | 0.006271 | [0.005296, 0.007175] |
| R_actual-minus-char5_coverage | consensus_rank | item_centered | rho | 0.010613 | [0.009719, 0.011368] |
| R_actual-minus-char5_coverage | consensus_rank | macro_within_level | pairwise_continuous_alpha_z | 0.039555 | [0.035284, 0.043364] |
| R_actual-minus-char5_coverage | consensus_rank | macro_within_level | rho | 0.032424 | [0.028671, 0.036388] |
| R_actual-minus-char5_coverage | consensus_z | item_centered | pairwise_continuous_alpha_z | 0.000585 | [-0.000327, 0.001351] |
| R_actual-minus-char5_coverage | consensus_z | item_centered | rho | 0.003116 | [0.002152, 0.003843] |
| R_actual-minus-char5_coverage | consensus_z | macro_within_level | pairwise_continuous_alpha_z | 0.036075 | [0.031716, 0.040006] |
| R_actual-minus-char5_coverage | consensus_z | macro_within_level | rho | 0.032010 | [0.028264, 0.035968] |
| R_actual-minus-char5_coverage | llama | item_centered | pairwise_continuous_alpha_z | -0.000471 | [-0.001427, 0.000358] |
| R_actual-minus-char5_coverage | llama | item_centered | rho | 0.002423 | [0.001415, 0.003174] |
| R_actual-minus-char5_coverage | llama | macro_within_level | pairwise_continuous_alpha_z | 0.040016 | [0.035456, 0.044130] |
| R_actual-minus-char5_coverage | llama | macro_within_level | rho | 0.028614 | [0.024818, 0.032614] |
| R_actual-minus-char5_coverage | mixtral | item_centered | pairwise_continuous_alpha_z | 0.001642 | [0.000741, 0.002425] |
| R_actual-minus-char5_coverage | mixtral | item_centered | rho | 0.003819 | [0.002862, 0.004563] |
| R_actual-minus-char5_coverage | mixtral | macro_within_level | pairwise_continuous_alpha_z | 0.029549 | [0.025007, 0.033679] |
| R_actual-minus-char5_coverage | mixtral | macro_within_level | rho | 0.031903 | [0.028203, 0.035845] |
| R_actual-minus-char5_coverage | treatment | item_centered | pairwise_continuous_alpha_z | -0.007359 | [-0.008442, -0.006297] |
| R_actual-minus-char5_coverage | treatment | item_centered | rho | -0.004027 | [-0.005006, -0.003103] |
| R_actual-minus-char5_coverage | treatment | pooled | pairwise_continuous_alpha_z | -0.017497 | [-0.018973, -0.016054] |
| R_actual-minus-char5_coverage | treatment | pooled | rho | -0.029126 | [-0.030575, -0.027836] |
| R_actual-minus-prompt_to_output_byte_ratio | consensus_rank | item_centered | pairwise_continuous_alpha_z | 0.033793 | [0.029535, 0.038250] |
| R_actual-minus-prompt_to_output_byte_ratio | consensus_rank | item_centered | rho | 0.045525 | [0.043642, 0.047281] |
| R_actual-minus-prompt_to_output_byte_ratio | consensus_rank | macro_within_level | pairwise_continuous_alpha_z | 0.158653 | [0.149045, 0.168228] |
| R_actual-minus-prompt_to_output_byte_ratio | consensus_rank | macro_within_level | rho | 0.173314 | [0.167546, 0.179435] |
| R_actual-minus-prompt_to_output_byte_ratio | consensus_z | item_centered | pairwise_continuous_alpha_z | 0.062925 | [0.058671, 0.067429] |
| R_actual-minus-prompt_to_output_byte_ratio | consensus_z | item_centered | rho | 0.048955 | [0.046989, 0.050751] |
| R_actual-minus-prompt_to_output_byte_ratio | consensus_z | macro_within_level | pairwise_continuous_alpha_z | 0.161042 | [0.151447, 0.170419] |
| R_actual-minus-prompt_to_output_byte_ratio | consensus_z | macro_within_level | rho | 0.173240 | [0.167476, 0.179402] |
| R_actual-minus-prompt_to_output_byte_ratio | llama | item_centered | pairwise_continuous_alpha_z | 0.051160 | [0.047004, 0.055530] |
| R_actual-minus-prompt_to_output_byte_ratio | llama | item_centered | rho | 0.043679 | [0.041844, 0.045358] |
| R_actual-minus-prompt_to_output_byte_ratio | llama | macro_within_level | pairwise_continuous_alpha_z | 0.157208 | [0.147009, 0.167552] |
| R_actual-minus-prompt_to_output_byte_ratio | llama | macro_within_level | rho | 0.171018 | [0.165252, 0.176990] |
| R_actual-minus-prompt_to_output_byte_ratio | mixtral | item_centered | pairwise_continuous_alpha_z | 0.074470 | [0.070028, 0.079053] |
| R_actual-minus-prompt_to_output_byte_ratio | mixtral | item_centered | rho | 0.054081 | [0.051997, 0.056019] |
| R_actual-minus-prompt_to_output_byte_ratio | mixtral | macro_within_level | pairwise_continuous_alpha_z | 0.159599 | [0.150817, 0.168348] |
| R_actual-minus-prompt_to_output_byte_ratio | mixtral | macro_within_level | rho | 0.170248 | [0.164381, 0.176668] |
| R_actual-minus-prompt_to_output_byte_ratio | treatment | item_centered | pairwise_continuous_alpha_z | 0.028021 | [0.024404, 0.031756] |
| R_actual-minus-prompt_to_output_byte_ratio | treatment | item_centered | rho | 0.040619 | [0.038586, 0.042515] |
| R_actual-minus-prompt_to_output_byte_ratio | treatment | pooled | pairwise_continuous_alpha_z | -0.001196 | [-0.005493, 0.003242] |
| R_actual-minus-prompt_to_output_byte_ratio | treatment | pooled | rho | -0.000549 | [-0.002745, 0.001450] |
| R_actual-minus-rouge_l_recall | consensus_rank | item_centered | pairwise_continuous_alpha_z | 0.002477 | [0.001363, 0.003614] |
| R_actual-minus-rouge_l_recall | consensus_rank | item_centered | rho | 0.005581 | [0.004494, 0.006568] |
| R_actual-minus-rouge_l_recall | consensus_rank | macro_within_level | pairwise_continuous_alpha_z | -0.007350 | [-0.012379, -0.002647] |
| R_actual-minus-rouge_l_recall | consensus_rank | macro_within_level | rho | -0.028410 | [-0.031966, -0.024992] |
| R_actual-minus-rouge_l_recall | consensus_z | item_centered | pairwise_continuous_alpha_z | -0.008268 | [-0.009307, -0.007288] |
| R_actual-minus-rouge_l_recall | consensus_z | item_centered | rho | -0.006556 | [-0.007667, -0.005624] |
| R_actual-minus-rouge_l_recall | consensus_z | macro_within_level | pairwise_continuous_alpha_z | -0.010703 | [-0.015641, -0.006065] |
| R_actual-minus-rouge_l_recall | consensus_z | macro_within_level | rho | -0.028509 | [-0.032061, -0.025079] |
| R_actual-minus-rouge_l_recall | llama | item_centered | pairwise_continuous_alpha_z | -0.009173 | [-0.010227, -0.008177] |
| R_actual-minus-rouge_l_recall | llama | item_centered | rho | -0.006952 | [-0.008023, -0.006010] |
| R_actual-minus-rouge_l_recall | llama | macro_within_level | pairwise_continuous_alpha_z | -0.007240 | [-0.012801, -0.002303] |
| R_actual-minus-rouge_l_recall | llama | macro_within_level | rho | -0.029988 | [-0.033373, -0.026685] |
| R_actual-minus-rouge_l_recall | mixtral | item_centered | pairwise_continuous_alpha_z | -0.007328 | [-0.008393, -0.006336] |
| R_actual-minus-rouge_l_recall | mixtral | item_centered | rho | -0.005978 | [-0.007128, -0.004989] |
| R_actual-minus-rouge_l_recall | mixtral | macro_within_level | pairwise_continuous_alpha_z | -0.014585 | [-0.019275, -0.010252] |
| R_actual-minus-rouge_l_recall | mixtral | macro_within_level | rho | -0.026296 | [-0.029986, -0.022770] |
| R_actual-minus-rouge_l_recall | treatment | item_centered | pairwise_continuous_alpha_z | -0.003687 | [-0.004874, -0.002456] |
| R_actual-minus-rouge_l_recall | treatment | item_centered | rho | 0.002498 | [0.001325, 0.003630] |
| R_actual-minus-rouge_l_recall | treatment | pooled | pairwise_continuous_alpha_z | -0.018374 | [-0.020066, -0.016645] |
| R_actual-minus-rouge_l_recall | treatment | pooled | rho | -0.034022 | [-0.035617, -0.032572] |
| R_actual-minus-word_token_coverage | consensus_rank | item_centered | pairwise_continuous_alpha_z | -0.021708 | [-0.023013, -0.020365] |
| R_actual-minus-word_token_coverage | consensus_rank | item_centered | rho | -0.001604 | [-0.002677, -0.000604] |
| R_actual-minus-word_token_coverage | consensus_rank | macro_within_level | pairwise_continuous_alpha_z | 0.027322 | [0.022762, 0.031492] |
| R_actual-minus-word_token_coverage | consensus_rank | macro_within_level | rho | 0.023011 | [0.019402, 0.026723] |
| R_actual-minus-word_token_coverage | consensus_z | item_centered | pairwise_continuous_alpha_z | -0.013359 | [-0.014570, -0.012192] |
| R_actual-minus-word_token_coverage | consensus_z | item_centered | rho | -0.005400 | [-0.006519, -0.004440] |
| R_actual-minus-word_token_coverage | consensus_z | macro_within_level | pairwise_continuous_alpha_z | 0.026631 | [0.022035, 0.030943] |
| R_actual-minus-word_token_coverage | consensus_z | macro_within_level | rho | 0.022864 | [0.019245, 0.026579] |
| R_actual-minus-word_token_coverage | llama | item_centered | pairwise_continuous_alpha_z | -0.017302 | [-0.018480, -0.016160] |
| R_actual-minus-word_token_coverage | llama | item_centered | rho | -0.006832 | [-0.007924, -0.005878] |
| R_actual-minus-word_token_coverage | llama | macro_within_level | pairwise_continuous_alpha_z | 0.028031 | [0.023316, 0.032583] |
| R_actual-minus-word_token_coverage | llama | macro_within_level | rho | 0.020124 | [0.016556, 0.023807] |
| R_actual-minus-word_token_coverage | mixtral | item_centered | pairwise_continuous_alpha_z | -0.009354 | [-0.010628, -0.008109] |
| R_actual-minus-word_token_coverage | mixtral | item_centered | rho | -0.003816 | [-0.005011, -0.002790] |
| R_actual-minus-word_token_coverage | mixtral | macro_within_level | pairwise_continuous_alpha_z | 0.024308 | [0.019918, 0.028624] |
| R_actual-minus-word_token_coverage | mixtral | macro_within_level | rho | 0.025224 | [0.021492, 0.029086] |
| R_actual-minus-word_token_coverage | treatment | item_centered | pairwise_continuous_alpha_z | -0.033990 | [-0.035484, -0.032509] |
| R_actual-minus-word_token_coverage | treatment | item_centered | rho | -0.014600 | [-0.015925, -0.013403] |
| R_actual-minus-word_token_coverage | treatment | pooled | pairwise_continuous_alpha_z | -0.052112 | [-0.054183, -0.050073] |
| R_actual-minus-word_token_coverage | treatment | pooled | rho | -0.040680 | [-0.042434, -0.039070] |
