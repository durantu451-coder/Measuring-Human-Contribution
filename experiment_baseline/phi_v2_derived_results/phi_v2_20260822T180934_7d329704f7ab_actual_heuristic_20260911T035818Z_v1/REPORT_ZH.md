# Experiment A：paper-final actual-only heuristic benchmark

## 分析合同

- 完整冻结 cohort：**11,222 model-items / 56,110 actual prompt-output pairs / 2,551 underlying source clusters**。
- 黑盒主分数：aggregate `actual_ratio`；白盒分别为 Llama 与 Mixtral 的 `levels.<L>.phi`。
- 每项主比较同时报告 Spearman ρ 与明确命名的 `pairwise_continuous_alpha_z`；后者先对每个 scorer 独立按 sample SD（ddof=1）做 z 标准化，再用 interval Krippendorff α 的 O(m) 精确代数式。
- 推断：2,000 次 paired source-cluster bootstrap，seed=20260823；同一 draw 同时用于全部候选、两个 evaluator、ρ、α 和直接差值。
- pooled 只作 secondary 描述；主解释使用 macro within-level 与 item-centered。

## 科学解释边界

BB_actual 与某个 H_actual 高度一致，只说明压缩分数与相应 lexical/length/output observable 共变。某个 heuristic 对白盒 operational estimator 的 convergence 更强，也不等于它更接近真实人类贡献；白盒不是 criterion truth。L1–L5 是联合改变 coverage、prompt length、representation form 与 generation stages 的 investigator-designed treatments，不是人工标签或纯信息量单因素干预。

# Table 1 — Direct BB_actual ↔ H_actual

| Heuristic | Macro within-level ρ | Macro pairwise_continuous_alpha_z | Item-centered ρ | Item-centered pairwise_continuous_alpha_z | Pooled ρ (secondary) | Pooled pairwise_continuous_alpha_z (secondary) |
|---|---:|---:|---:|---:|---:|---:|
| `prompt_bytes` | -0.0308 [-0.0426, -0.0184] | -0.0006 [-0.0111, 0.0105] | 0.7557 [0.7515, 0.7598] | 0.6443 [0.6391, 0.6499] | 0.7640 [0.7574, 0.7701] | 0.5699 [0.5629, 0.5770] |
| `output_bytes` | -0.6373 [-0.6466, -0.6274] | -0.5052 [-0.5136, -0.4965] | -0.1985 [-0.2168, -0.1789] | -0.2360 [-0.2498, -0.2207] | -0.2968 [-0.3134, -0.2785] | -0.2940 [-0.3064, -0.2802] |
| `prompt_words` | -0.0272 [-0.0390, -0.0147] | 0.0161 [0.0051, 0.0273] | 0.7502 [0.7463, 0.7541] | 0.6421 [0.6367, 0.6475] | 0.7698 [0.7633, 0.7758] | 0.5655 [0.5584, 0.5726] |
| `output_words` | -0.6459 [-0.6550, -0.6358] | -0.5139 [-0.5221, -0.5055] | -0.1670 [-0.1858, -0.1464] | -0.2036 [-0.2192, -0.1866] | -0.2791 [-0.2962, -0.2600] | -0.2684 [-0.2825, -0.2530] |
| `prompt_to_output_byte_ratio` | 0.8123 [0.8075, 0.8167] | 0.8135 [0.8052, 0.8220] | 0.9152 [0.9136, 0.9169] | 0.8523 [0.8481, 0.8563] | 0.9304 [0.9287, 0.9319] | 0.8467 [0.8423, 0.8509] |
| `word_type_coverage` | 0.9249 [0.9227, 0.9271] | 0.9324 [0.9296, 0.9347] | 0.9858 [0.9851, 0.9864] | 0.9843 [0.9836, 0.9848] | 0.9848 [0.9838, 0.9856] | 0.9806 [0.9796, 0.9814] |
| `word_token_coverage` | 0.9260 [0.9230, 0.9287] | 0.9244 [0.9210, 0.9277] | 0.9771 [0.9763, 0.9778] | 0.9696 [0.9688, 0.9703] | 0.9783 [0.9773, 0.9791] | 0.9644 [0.9633, 0.9652] |
| `word_bigram_coverage` | 0.7773 [0.7723, 0.7826] | 0.8303 [0.8235, 0.8372] | 0.9700 [0.9689, 0.9710] | 0.9676 [0.9664, 0.9687] | 0.9656 [0.9641, 0.9669] | 0.9644 [0.9630, 0.9658] |
| `char3_coverage` | 0.9151 [0.9118, 0.9182] | 0.9138 [0.9103, 0.9172] | 0.9717 [0.9708, 0.9724] | 0.9545 [0.9535, 0.9554] | 0.9710 [0.9698, 0.9720] | 0.9492 [0.9480, 0.9501] |
| `char5_coverage` | 0.9170 [0.9141, 0.9196] | 0.9253 [0.9219, 0.9284] | 0.9858 [0.9851, 0.9864] | 0.9878 [0.9871, 0.9883] | 0.9833 [0.9823, 0.9841] | 0.9844 [0.9834, 0.9851] |
| `char8_coverage` | 0.8283 [0.8238, 0.8325] | 0.8670 [0.8614, 0.8721] | 0.9776 [0.9767, 0.9784] | 0.9770 [0.9761, 0.9778] | 0.9702 [0.9689, 0.9714] | 0.9745 [0.9734, 0.9755] |
| `rouge_l_recall` | 0.9279 [0.9254, 0.9303] | 0.9220 [0.9187, 0.9254] | 0.9793 [0.9784, 0.9800] | 0.9818 [0.9809, 0.9824] | 0.9826 [0.9815, 0.9834] | 0.9772 [0.9761, 0.9782] |
| `output_type_token_ratio` | 0.3026 [0.2896, 0.3149] | 0.3277 [0.3143, 0.3413] | -0.0095 [-0.0288, 0.0096] | -0.0249 [-0.0459, -0.0040] | 0.0157 [-0.0012, 0.0330] | 0.0071 [-0.0110, 0.0249] |
| `output_bigram_repeat_fraction` | -0.1735 [-0.1869, -0.1602] | -0.1606 [-0.1735, -0.1475] | 0.1584 [0.1395, 0.1769] | 0.2354 [0.2163, 0.2540] | 0.0961 [0.0797, 0.1116] | 0.1621 [0.1460, 0.1773] |
| `output_self_bits_per_byte` | 0.3589 [0.3461, 0.3714] | 0.4225 [0.4078, 0.4369] | 0.1000 [0.0819, 0.1175] | 0.0837 [0.0627, 0.1048] | 0.0987 [0.0816, 0.1151] | 0.1135 [0.0950, 0.1320] |

# Table 2 — Llama white-box convergence

| Candidate | Macro within-level ρ | Macro pairwise_continuous_alpha_z | Item-centered ρ | Item-centered pairwise_continuous_alpha_z | Pooled ρ (secondary) | Pooled pairwise_continuous_alpha_z (secondary) |
|---|---:|---:|---:|---:|---:|---:|
| `blackbox_actual_ratio` | 0.7702 [0.7653, 0.7749] | 0.7919 [0.7863, 0.7973] | 0.9654 [0.9641, 0.9665] | 0.9599 [0.9585, 0.9612] | 0.9570 [0.9554, 0.9583] | 0.9482 [0.9464, 0.9499] |
| `prompt_bytes` | 0.0866 [0.0759, 0.0976] | 0.1003 [0.0905, 0.1106] | 0.8010 [0.7973, 0.8048] | 0.7043 [0.6994, 0.7097] | 0.8055 [0.7997, 0.8111] | 0.6255 [0.6200, 0.6316] |
| `output_bytes` | -0.4625 [-0.4708, -0.4536] | -0.4182 [-0.4257, -0.4102] | -0.1945 [-0.2133, -0.1742] | -0.2564 [-0.2711, -0.2400] | -0.2823 [-0.2989, -0.2639] | -0.2976 [-0.3107, -0.2830] |
| `prompt_words` | 0.1277 [0.1168, 0.1384] | 0.1312 [0.1213, 0.1416] | 0.8007 [0.7972, 0.8044] | 0.7071 [0.7023, 0.7123] | 0.8153 [0.8097, 0.8209] | 0.6278 [0.6222, 0.6337] |
| `output_words` | -0.4566 [-0.4649, -0.4476] | -0.4152 [-0.4228, -0.4072] | -0.1635 [-0.1832, -0.1424] | -0.2247 [-0.2414, -0.2064] | -0.2584 [-0.2756, -0.2396] | -0.2663 [-0.2813, -0.2498] |
| `prompt_to_output_byte_ratio` | 0.5992 [0.5919, 0.6059] | 0.6346 [0.6229, 0.6465] | 0.9217 [0.9202, 0.9232] | 0.9088 [0.9045, 0.9126] | 0.9254 [0.9240, 0.9268] | 0.8942 [0.8891, 0.8986] |
| `word_type_coverage` | 0.7712 [0.7660, 0.7761] | 0.7807 [0.7753, 0.7861] | 0.9663 [0.9654, 0.9671] | 0.9659 [0.9649, 0.9669] | 0.9572 [0.9561, 0.9581] | 0.9560 [0.9548, 0.9571] |
| `word_token_coverage` | 0.7501 [0.7450, 0.7553] | 0.7638 [0.7579, 0.7703] | 0.9722 [0.9714, 0.9729] | 0.9772 [0.9765, 0.9779] | 0.9659 [0.9651, 0.9666] | 0.9670 [0.9661, 0.9679] |
| `word_bigram_coverage` | 0.6598 [0.6526, 0.6671] | 0.6939 [0.6870, 0.7012] | 0.9335 [0.9314, 0.9355] | 0.9132 [0.9107, 0.9154] | 0.9295 [0.9275, 0.9314] | 0.9063 [0.9038, 0.9085] |
| `char3_coverage` | 0.7181 [0.7129, 0.7234] | 0.7454 [0.7394, 0.7512] | 0.9698 [0.9691, 0.9705] | 0.9733 [0.9727, 0.9738] | 0.9613 [0.9605, 0.9621] | 0.9642 [0.9634, 0.9649] |
| `char5_coverage` | 0.7416 [0.7361, 0.7471] | 0.7518 [0.7463, 0.7581] | 0.9629 [0.9618, 0.9640] | 0.9604 [0.9591, 0.9617] | 0.9565 [0.9555, 0.9576] | 0.9506 [0.9491, 0.9521] |
| `char8_coverage` | 0.6941 [0.6874, 0.7009] | 0.7202 [0.7136, 0.7265] | 0.9329 [0.9305, 0.9352] | 0.9167 [0.9142, 0.9191] | 0.9258 [0.9234, 0.9282] | 0.9078 [0.9052, 0.9103] |
| `rouge_l_recall` | 0.8002 [0.7960, 0.8044] | 0.7991 [0.7930, 0.8056] | 0.9723 [0.9716, 0.9730] | 0.9691 [0.9682, 0.9700] | 0.9707 [0.9700, 0.9714] | 0.9627 [0.9617, 0.9637] |
| `output_type_token_ratio` | 0.2488 [0.2367, 0.2606] | 0.2810 [0.2691, 0.2934] | 0.0249 [0.0055, 0.0446] | 0.0326 [0.0118, 0.0543] | 0.0416 [0.0242, 0.0598] | 0.0527 [0.0358, 0.0708] |
| `output_bigram_repeat_fraction` | -0.1721 [-0.1852, -0.1598] | -0.1713 [-0.1845, -0.1591] | 0.1170 [0.0973, 0.1355] | 0.1784 [0.1590, 0.1972] | 0.0562 [0.0383, 0.0726] | 0.1032 [0.0873, 0.1179] |
| `output_self_bits_per_byte` | 0.2815 [0.2690, 0.2940] | 0.3258 [0.3132, 0.3388] | 0.1217 [0.1037, 0.1394] | 0.1143 [0.0943, 0.1353] | 0.1212 [0.1034, 0.1383] | 0.1337 [0.1166, 0.1507] |

# Table 3 — Mixtral white-box convergence

| Candidate | Macro within-level ρ | Macro pairwise_continuous_alpha_z | Item-centered ρ | Item-centered pairwise_continuous_alpha_z | Pooled ρ (secondary) | Pooled pairwise_continuous_alpha_z (secondary) |
|---|---:|---:|---:|---:|---:|---:|
| `blackbox_actual_ratio` | 0.7603 [0.7544, 0.7662] | 0.7817 [0.7756, 0.7879] | 0.9648 [0.9633, 0.9663] | 0.9636 [0.9618, 0.9652] | 0.9563 [0.9545, 0.9580] | 0.9497 [0.9476, 0.9518] |
| `prompt_bytes` | 0.0440 [0.0333, 0.0540] | 0.0403 [0.0308, 0.0500] | 0.7975 [0.7940, 0.8011] | 0.6952 [0.6904, 0.7002] | 0.7994 [0.7937, 0.8047] | 0.6070 [0.6017, 0.6128] |
| `output_bytes` | -0.4828 [-0.4904, -0.4747] | -0.4399 [-0.4471, -0.4322] | -0.1893 [-0.2080, -0.1692] | -0.2449 [-0.2595, -0.2287] | -0.2876 [-0.3039, -0.2701] | -0.2970 [-0.3098, -0.2828] |
| `prompt_words` | 0.0830 [0.0725, 0.0928] | 0.0671 [0.0571, 0.0771] | 0.7977 [0.7942, 0.8013] | 0.6982 [0.6934, 0.7031] | 0.8097 [0.8042, 0.8150] | 0.6101 [0.6047, 0.6157] |
| `output_words` | -0.4703 [-0.4779, -0.4622] | -0.4324 [-0.4397, -0.4248] | -0.1575 [-0.1772, -0.1366] | -0.2131 [-0.2296, -0.1950] | -0.2623 [-0.2792, -0.2438] | -0.2646 [-0.2796, -0.2481] |
| `prompt_to_output_byte_ratio` | 0.5901 [0.5829, 0.5967] | 0.6221 [0.6121, 0.6319] | 0.9108 [0.9091, 0.9124] | 0.8891 [0.8846, 0.8933] | 0.9197 [0.9182, 0.9212] | 0.8747 [0.8695, 0.8793] |
| `word_type_coverage` | 0.7603 [0.7547, 0.7662] | 0.7790 [0.7734, 0.7848] | 0.9662 [0.9650, 0.9672] | 0.9678 [0.9664, 0.9691] | 0.9562 [0.9549, 0.9575] | 0.9551 [0.9534, 0.9566] |
| `word_token_coverage` | 0.7351 [0.7295, 0.7412] | 0.7574 [0.7514, 0.7638] | 0.9687 [0.9676, 0.9696] | 0.9729 [0.9718, 0.9739] | 0.9633 [0.9622, 0.9642] | 0.9600 [0.9586, 0.9613] |
| `word_bigram_coverage` | 0.6495 [0.6415, 0.6571] | 0.6980 [0.6899, 0.7054] | 0.9355 [0.9330, 0.9379] | 0.9230 [0.9199, 0.9258] | 0.9292 [0.9269, 0.9313] | 0.9125 [0.9093, 0.9154] |
| `char3_coverage` | 0.7079 [0.7021, 0.7142] | 0.7392 [0.7330, 0.7456] | 0.9650 [0.9641, 0.9659] | 0.9657 [0.9647, 0.9666] | 0.9583 [0.9572, 0.9592] | 0.9542 [0.9530, 0.9554] |
| `char5_coverage` | 0.7284 [0.7223, 0.7349] | 0.7521 [0.7461, 0.7583] | 0.9610 [0.9596, 0.9624] | 0.9619 [0.9601, 0.9637] | 0.9544 [0.9530, 0.9557] | 0.9486 [0.9466, 0.9506] |
| `char8_coverage` | 0.6745 [0.6667, 0.6826] | 0.7131 [0.7057, 0.7205] | 0.9338 [0.9309, 0.9365] | 0.9254 [0.9222, 0.9282] | 0.9236 [0.9208, 0.9263] | 0.9121 [0.9088, 0.9153] |
| `rouge_l_recall` | 0.7866 [0.7816, 0.7917] | 0.7962 [0.7910, 0.8017] | 0.9708 [0.9698, 0.9718] | 0.9709 [0.9695, 0.9722] | 0.9693 [0.9683, 0.9702] | 0.9623 [0.9607, 0.9637] |
| `output_type_token_ratio` | 0.2601 [0.2485, 0.2719] | 0.2838 [0.2723, 0.2954] | 0.0127 [-0.0068, 0.0323] | 0.0132 [-0.0073, 0.0345] | 0.0393 [0.0221, 0.0573] | 0.0436 [0.0267, 0.0612] |
| `output_bigram_repeat_fraction` | -0.1881 [-0.2011, -0.1761] | -0.1708 [-0.1835, -0.1585] | 0.1299 [0.1100, 0.1484] | 0.1963 [0.1771, 0.2149] | 0.0577 [0.0401, 0.0740] | 0.1123 [0.0966, 0.1271] |
| `output_self_bits_per_byte` | 0.3060 [0.2941, 0.3176] | 0.3389 [0.3274, 0.3503] | 0.1111 [0.0936, 0.1282] | 0.0995 [0.0799, 0.1194] | 0.1223 [0.1047, 0.1392] | 0.1294 [0.1124, 0.1461] |

# Table 4 — Paired BB-minus-heuristic differences

| Heuristic | Evaluator | Scope | Δρ (BB−H) 95% CI | ρ winner | Δpairwise_continuous_alpha_z (BB−H) 95% CI | α winner | Classification |
|---|---|---|---:|---|---:|---|---|
| `prompt_bytes` | Llama | macro_within_level | 0.6836 [0.6712, 0.6952] | BB_actual | 0.6915 [0.6799, 0.7032] | BB_actual | robust_BB_convergence_winner |
| `prompt_bytes` | Llama | item_centered | 0.1643 [0.1603, 0.1683] | BB_actual | 0.2556 [0.2502, 0.2608] | BB_actual | robust_BB_convergence_winner |
| `prompt_bytes` | Llama | pooled | 0.1515 [0.1455, 0.1577] | BB_actual | 0.3227 [0.3165, 0.3284] | BB_actual | secondary |
| `prompt_bytes` | Mixtral | macro_within_level | 0.7163 [0.7045, 0.7280] | BB_actual | 0.7414 [0.7301, 0.7526] | BB_actual | robust_BB_convergence_winner |
| `prompt_bytes` | Mixtral | item_centered | 0.1673 [0.1631, 0.1713] | BB_actual | 0.2684 [0.2632, 0.2734] | BB_actual | robust_BB_convergence_winner |
| `prompt_bytes` | Mixtral | pooled | 0.1570 [0.1511, 0.1631] | BB_actual | 0.3427 [0.3367, 0.3481] | BB_actual | secondary |
| `output_bytes` | Llama | macro_within_level | 1.2327 [1.2211, 1.2431] | BB_actual | 1.2100 [1.1996, 1.2201] | BB_actual | robust_BB_convergence_winner |
| `output_bytes` | Llama | item_centered | 1.1599 [1.1394, 1.1785] | BB_actual | 1.2164 [1.2001, 1.2312] | BB_actual | robust_BB_convergence_winner |
| `output_bytes` | Llama | pooled | 1.2393 [1.2206, 1.2565] | BB_actual | 1.2458 [1.2309, 1.2589] | BB_actual | secondary |
| `output_bytes` | Mixtral | macro_within_level | 1.2431 [1.2326, 1.2538] | BB_actual | 1.2215 [1.2116, 1.2310] | BB_actual | robust_BB_convergence_winner |
| `output_bytes` | Mixtral | item_centered | 1.1541 [1.1341, 1.1726] | BB_actual | 1.2085 [1.1923, 1.2233] | BB_actual | robust_BB_convergence_winner |
| `output_bytes` | Mixtral | pooled | 1.2440 [1.2260, 1.2607] | BB_actual | 1.2467 [1.2320, 1.2598] | BB_actual | secondary |
| `prompt_words` | Llama | macro_within_level | 0.6425 [0.6303, 0.6545] | BB_actual | 0.6607 [0.6493, 0.6724] | BB_actual | robust_BB_convergence_winner |
| `prompt_words` | Llama | item_centered | 0.1646 [0.1606, 0.1684] | BB_actual | 0.2528 [0.2474, 0.2579] | BB_actual | robust_BB_convergence_winner |
| `prompt_words` | Llama | pooled | 0.1417 [0.1359, 0.1477] | BB_actual | 0.3204 [0.3143, 0.3263] | BB_actual | secondary |
| `prompt_words` | Mixtral | macro_within_level | 0.6774 [0.6658, 0.6893] | BB_actual | 0.7146 [0.7033, 0.7260] | BB_actual | robust_BB_convergence_winner |
| `prompt_words` | Mixtral | item_centered | 0.1671 [0.1630, 0.1712] | BB_actual | 0.2654 [0.2601, 0.2704] | BB_actual | robust_BB_convergence_winner |
| `prompt_words` | Mixtral | pooled | 0.1466 [0.1409, 0.1528] | BB_actual | 0.3396 [0.3336, 0.3455] | BB_actual | secondary |
| `output_words` | Llama | macro_within_level | 1.2269 [1.2149, 1.2376] | BB_actual | 1.2071 [1.1967, 1.2170] | BB_actual | robust_BB_convergence_winner |
| `output_words` | Llama | item_centered | 1.1288 [1.1075, 1.1485] | BB_actual | 1.1846 [1.1664, 1.2012] | BB_actual | robust_BB_convergence_winner |
| `output_words` | Llama | pooled | 1.2153 [1.1961, 1.2327] | BB_actual | 1.2145 [1.1976, 1.2296] | BB_actual | secondary |
| `output_words` | Mixtral | macro_within_level | 1.2307 [1.2197, 1.2413] | BB_actual | 1.2140 [1.2042, 1.2234] | BB_actual | robust_BB_convergence_winner |
| `output_words` | Mixtral | item_centered | 1.1224 [1.1016, 1.1417] | BB_actual | 1.1767 [1.1587, 1.1929] | BB_actual | robust_BB_convergence_winner |
| `output_words` | Mixtral | pooled | 1.2187 [1.1999, 1.2356] | BB_actual | 1.2143 [1.1976, 1.2292] | BB_actual | secondary |
| `prompt_to_output_byte_ratio` | Llama | macro_within_level | 0.1710 [0.1653, 0.1770] | BB_actual | 0.1572 [0.1470, 0.1676] | BB_actual | robust_BB_convergence_winner |
| `prompt_to_output_byte_ratio` | Llama | item_centered | 0.0437 [0.0418, 0.0454] | BB_actual | 0.0512 [0.0470, 0.0555] | BB_actual | robust_BB_convergence_winner |
| `prompt_to_output_byte_ratio` | Llama | pooled | 0.0315 [0.0295, 0.0334] | BB_actual | 0.0541 [0.0494, 0.0592] | BB_actual | secondary |
| `prompt_to_output_byte_ratio` | Mixtral | macro_within_level | 0.1702 [0.1644, 0.1767] | BB_actual | 0.1596 [0.1508, 0.1683] | BB_actual | robust_BB_convergence_winner |
| `prompt_to_output_byte_ratio` | Mixtral | item_centered | 0.0541 [0.0520, 0.0560] | BB_actual | 0.0745 [0.0700, 0.0791] | BB_actual | robust_BB_convergence_winner |
| `prompt_to_output_byte_ratio` | Mixtral | pooled | 0.0367 [0.0345, 0.0387] | BB_actual | 0.0750 [0.0701, 0.0804] | BB_actual | secondary |
| `word_type_coverage` | Llama | macro_within_level | -0.0010 [-0.0048, 0.0026] | inconclusive | 0.0112 [0.0070, 0.0152] | BB_actual | inconclusive |
| `word_type_coverage` | Llama | item_centered | -0.0009 [-0.0020, -0.0000] | heuristic | -0.0060 [-0.0071, -0.0051] | heuristic | robust_heuristic_convergence_winner |
| `word_type_coverage` | Llama | pooled | -0.0002 [-0.0017, 0.0009] | inconclusive | -0.0077 [-0.0092, -0.0064] | heuristic | secondary |
| `word_type_coverage` | Mixtral | macro_within_level | 0.0000 [-0.0039, 0.0040] | inconclusive | 0.0026 [-0.0016, 0.0066] | inconclusive | inconclusive |
| `word_type_coverage` | Mixtral | item_centered | -0.0013 [-0.0024, -0.0004] | heuristic | -0.0042 [-0.0053, -0.0033] | heuristic | robust_heuristic_convergence_winner |
| `word_type_coverage` | Mixtral | pooled | 0.0001 [-0.0014, 0.0012] | inconclusive | -0.0053 [-0.0070, -0.0040] | heuristic | secondary |
| `word_token_coverage` | Llama | macro_within_level | 0.0201 [0.0166, 0.0238] | BB_actual | 0.0280 [0.0233, 0.0326] | BB_actual | robust_BB_convergence_winner |
| `word_token_coverage` | Llama | item_centered | -0.0068 [-0.0079, -0.0059] | heuristic | -0.0173 [-0.0185, -0.0162] | heuristic | robust_heuristic_convergence_winner |
| `word_token_coverage` | Llama | pooled | -0.0089 [-0.0105, -0.0078] | heuristic | -0.0188 [-0.0204, -0.0173] | heuristic | secondary |
| `word_token_coverage` | Mixtral | macro_within_level | 0.0252 [0.0215, 0.0291] | BB_actual | 0.0243 [0.0199, 0.0286] | BB_actual | robust_BB_convergence_winner |
| `word_token_coverage` | Mixtral | item_centered | -0.0038 [-0.0050, -0.0028] | heuristic | -0.0094 [-0.0106, -0.0081] | heuristic | robust_heuristic_convergence_winner |
| `word_token_coverage` | Mixtral | pooled | -0.0070 [-0.0086, -0.0057] | heuristic | -0.0103 [-0.0120, -0.0087] | heuristic | secondary |
| `word_bigram_coverage` | Llama | macro_within_level | 0.1104 [0.1039, 0.1173] | BB_actual | 0.0980 [0.0914, 0.1047] | BB_actual | robust_BB_convergence_winner |
| `word_bigram_coverage` | Llama | item_centered | 0.0318 [0.0304, 0.0335] | BB_actual | 0.0467 [0.0452, 0.0484] | BB_actual | robust_BB_convergence_winner |
| `word_bigram_coverage` | Llama | pooled | 0.0275 [0.0257, 0.0292] | BB_actual | 0.0420 [0.0403, 0.0437] | BB_actual | secondary |
| `word_bigram_coverage` | Mixtral | macro_within_level | 0.1108 [0.1046, 0.1169] | BB_actual | 0.0837 [0.0776, 0.0899] | BB_actual | robust_BB_convergence_winner |
| `word_bigram_coverage` | Mixtral | item_centered | 0.0293 [0.0278, 0.0310] | BB_actual | 0.0405 [0.0389, 0.0424] | BB_actual | robust_BB_convergence_winner |
| `word_bigram_coverage` | Mixtral | pooled | 0.0272 [0.0254, 0.0289] | BB_actual | 0.0372 [0.0354, 0.0392] | BB_actual | secondary |
| `char3_coverage` | Llama | macro_within_level | 0.0521 [0.0484, 0.0560] | BB_actual | 0.0464 [0.0417, 0.0509] | BB_actual | robust_BB_convergence_winner |
| `char3_coverage` | Llama | item_centered | -0.0044 [-0.0056, -0.0035] | heuristic | -0.0133 [-0.0147, -0.0121] | heuristic | inconclusive |
| `char3_coverage` | Llama | pooled | -0.0043 [-0.0058, -0.0031] | heuristic | -0.0159 [-0.0177, -0.0143] | heuristic | secondary |
| `char3_coverage` | Mixtral | macro_within_level | 0.0524 [0.0484, 0.0565] | BB_actual | 0.0424 [0.0377, 0.0470] | BB_actual | robust_BB_convergence_winner |
| `char3_coverage` | Mixtral | item_centered | -0.0002 [-0.0014, 0.0008] | inconclusive | -0.0021 [-0.0036, -0.0007] | heuristic | inconclusive |
| `char3_coverage` | Mixtral | pooled | -0.0019 [-0.0035, -0.0006] | heuristic | -0.0045 [-0.0066, -0.0027] | heuristic | secondary |
| `char5_coverage` | Llama | macro_within_level | 0.0286 [0.0248, 0.0326] | BB_actual | 0.0400 [0.0355, 0.0441] | BB_actual | robust_BB_convergence_winner |
| `char5_coverage` | Llama | item_centered | 0.0024 [0.0014, 0.0032] | BB_actual | -0.0005 [-0.0014, 0.0004] | inconclusive | inconclusive |
| `char5_coverage` | Llama | pooled | 0.0004 [-0.0010, 0.0014] | inconclusive | -0.0024 [-0.0037, -0.0014] | heuristic | secondary |
| `char5_coverage` | Mixtral | macro_within_level | 0.0319 [0.0282, 0.0358] | BB_actual | 0.0295 [0.0250, 0.0337] | BB_actual | robust_BB_convergence_winner |
| `char5_coverage` | Mixtral | item_centered | 0.0038 [0.0029, 0.0046] | BB_actual | 0.0016 [0.0007, 0.0024] | BB_actual | inconclusive |
| `char5_coverage` | Mixtral | pooled | 0.0020 [0.0005, 0.0030] | BB_actual | 0.0011 [-0.0003, 0.0022] | inconclusive | secondary |
| `char8_coverage` | Llama | macro_within_level | 0.0761 [0.0702, 0.0823] | BB_actual | 0.0717 [0.0660, 0.0775] | BB_actual | robust_BB_convergence_winner |
| `char8_coverage` | Llama | item_centered | 0.0325 [0.0308, 0.0343] | BB_actual | 0.0432 [0.0417, 0.0448] | BB_actual | robust_BB_convergence_winner |
| `char8_coverage` | Llama | pooled | 0.0312 [0.0292, 0.0331] | BB_actual | 0.0405 [0.0388, 0.0421] | BB_actual | secondary |
| `char8_coverage` | Mixtral | macro_within_level | 0.0858 [0.0801, 0.0916] | BB_actual | 0.0686 [0.0631, 0.0739] | BB_actual | robust_BB_convergence_winner |
| `char8_coverage` | Mixtral | item_centered | 0.0311 [0.0293, 0.0329] | BB_actual | 0.0382 [0.0365, 0.0400] | BB_actual | robust_BB_convergence_winner |
| `char8_coverage` | Mixtral | pooled | 0.0327 [0.0307, 0.0346] | BB_actual | 0.0376 [0.0357, 0.0394] | BB_actual | secondary |
| `rouge_l_recall` | Llama | macro_within_level | -0.0300 [-0.0334, -0.0267] | heuristic | -0.0072 [-0.0128, -0.0023] | heuristic | robust_heuristic_convergence_winner |
| `rouge_l_recall` | Llama | item_centered | -0.0070 [-0.0080, -0.0060] | heuristic | -0.0092 [-0.0102, -0.0082] | heuristic | robust_heuristic_convergence_winner |
| `rouge_l_recall` | Llama | pooled | -0.0138 [-0.0153, -0.0126] | heuristic | -0.0144 [-0.0159, -0.0132] | heuristic | secondary |
| `rouge_l_recall` | Mixtral | macro_within_level | -0.0263 [-0.0300, -0.0228] | heuristic | -0.0146 [-0.0193, -0.0103] | heuristic | robust_heuristic_convergence_winner |
| `rouge_l_recall` | Mixtral | item_centered | -0.0060 [-0.0071, -0.0050] | heuristic | -0.0073 [-0.0084, -0.0063] | heuristic | robust_heuristic_convergence_winner |
| `rouge_l_recall` | Mixtral | pooled | -0.0129 [-0.0146, -0.0117] | heuristic | -0.0126 [-0.0142, -0.0112] | heuristic | secondary |
| `output_type_token_ratio` | Llama | macro_within_level | 0.5214 [0.5087, 0.5341] | BB_actual | 0.5108 [0.4984, 0.5232] | BB_actual | robust_BB_convergence_winner |
| `output_type_token_ratio` | Llama | item_centered | 0.9405 [0.9203, 0.9604] | BB_actual | 0.9273 [0.9053, 0.9484] | BB_actual | robust_BB_convergence_winner |
| `output_type_token_ratio` | Llama | pooled | 0.9154 [0.8970, 0.9332] | BB_actual | 0.8956 [0.8773, 0.9129] | BB_actual | secondary |
| `output_type_token_ratio` | Mixtral | macro_within_level | 0.5002 [0.4867, 0.5138] | BB_actual | 0.4979 [0.4852, 0.5105] | BB_actual | robust_BB_convergence_winner |
| `output_type_token_ratio` | Mixtral | item_centered | 0.9521 [0.9322, 0.9722] | BB_actual | 0.9504 [0.9289, 0.9709] | BB_actual | robust_BB_convergence_winner |
| `output_type_token_ratio` | Mixtral | pooled | 0.9171 [0.8986, 0.9345] | BB_actual | 0.9061 [0.8878, 0.9234] | BB_actual | secondary |
| `output_bigram_repeat_fraction` | Llama | macro_within_level | 0.9423 [0.9285, 0.9564] | BB_actual | 0.9631 [0.9488, 0.9784] | BB_actual | robust_BB_convergence_winner |
| `output_bigram_repeat_fraction` | Llama | item_centered | 0.8484 [0.8299, 0.8681] | BB_actual | 0.7815 [0.7628, 0.8011] | BB_actual | robust_BB_convergence_winner |
| `output_bigram_repeat_fraction` | Llama | pooled | 0.9008 [0.8843, 0.9186] | BB_actual | 0.8450 [0.8303, 0.8614] | BB_actual | secondary |
| `output_bigram_repeat_fraction` | Mixtral | macro_within_level | 0.9484 [0.9356, 0.9618] | BB_actual | 0.9524 [0.9386, 0.9663] | BB_actual | robust_BB_convergence_winner |
| `output_bigram_repeat_fraction` | Mixtral | item_centered | 0.8349 [0.8164, 0.8545] | BB_actual | 0.7673 [0.7490, 0.7860] | BB_actual | robust_BB_convergence_winner |
| `output_bigram_repeat_fraction` | Mixtral | pooled | 0.8986 [0.8820, 0.9161] | BB_actual | 0.8374 [0.8226, 0.8532] | BB_actual | secondary |
| `output_self_bits_per_byte` | Llama | macro_within_level | 0.4887 [0.4755, 0.5016] | BB_actual | 0.4661 [0.4535, 0.4784] | BB_actual | robust_BB_convergence_winner |
| `output_self_bits_per_byte` | Llama | item_centered | 0.8437 [0.8258, 0.8615] | BB_actual | 0.8456 [0.8245, 0.8658] | BB_actual | robust_BB_convergence_winner |
| `output_self_bits_per_byte` | Llama | pooled | 0.8358 [0.8187, 0.8539] | BB_actual | 0.8146 [0.7973, 0.8320] | BB_actual | secondary |
| `output_self_bits_per_byte` | Mixtral | macro_within_level | 0.4543 [0.4411, 0.4676] | BB_actual | 0.4428 [0.4307, 0.4551] | BB_actual | robust_BB_convergence_winner |
| `output_self_bits_per_byte` | Mixtral | item_centered | 0.8538 [0.8367, 0.8713] | BB_actual | 0.8641 [0.8444, 0.8841] | BB_actual | robust_BB_convergence_winner |
| `output_self_bits_per_byte` | Mixtral | pooled | 0.8341 [0.8169, 0.8519] | BB_actual | 0.8203 [0.8036, 0.8376] | BB_actual | secondary |

# Table 5 — Joint two-white-box agreement

| Candidate | Scope | Mean reference Spearman ρ | joint_reference_continuous_alpha_z | Δmean ρ (BB−H) 95% CI | Δjoint α_z (BB−H) 95% CI |
|---|---|---:|---:|---:|---:|
| `blackbox_actual_ratio` | macro_within_level | 0.7653 [0.7602, 0.7703] | 0.8317 [0.8277, 0.8358] | reference | reference |
| `blackbox_actual_ratio` | item_centered | 0.9651 [0.9638, 0.9664] | 0.9719 [0.9708, 0.9729] | reference | reference |
| `blackbox_actual_ratio` | pooled | 0.9567 [0.9550, 0.9581] | 0.9627 [0.9614, 0.9640] | reference | reference |
| `prompt_bytes` | macro_within_level | 0.0653 [0.0547, 0.0756] | 0.3541 [0.3477, 0.3606] | 0.6999 [0.6881, 0.7112] | 0.4776 [0.4702, 0.4849] |
| `prompt_bytes` | item_centered | 0.7993 [0.7957, 0.8030] | 0.7972 [0.7941, 0.8007] | 0.1658 [0.1618, 0.1699] | 0.1747 [0.1712, 0.1780] |
| `prompt_bytes` | pooled | 0.8024 [0.7967, 0.8079] | 0.7409 [0.7374, 0.7449] | 0.1542 [0.1485, 0.1604] | 0.2218 [0.2178, 0.2255] |
| `output_bytes` | macro_within_level | -0.4727 [-0.4803, -0.4646] | 0.0212 [0.0163, 0.0263] | 1.2379 [1.2273, 1.2479] | 0.8105 [0.8042, 0.8165] |
| `output_bytes` | item_centered | -0.1919 [-0.2106, -0.1716] | 0.1636 [0.1538, 0.1744] | 1.1570 [1.1368, 1.1756] | 0.8083 [0.7975, 0.8182] |
| `output_bytes` | pooled | -0.2850 [-0.3017, -0.2670] | 0.1319 [0.1233, 0.1414] | 1.2416 [1.2233, 1.2585] | 0.8308 [0.8209, 0.8396] |
| `prompt_words` | macro_within_level | 0.1053 [0.0948, 0.1155] | 0.3733 [0.3668, 0.3799] | 0.6599 [0.6483, 0.6713] | 0.4584 [0.4511, 0.4656] |
| `prompt_words` | item_centered | 0.7992 [0.7958, 0.8028] | 0.7992 [0.7960, 0.8025] | 0.1659 [0.1619, 0.1698] | 0.1727 [0.1692, 0.1760] |
| `prompt_words` | pooled | 0.8125 [0.8069, 0.8179] | 0.7427 [0.7391, 0.7465] | 0.1441 [0.1384, 0.1503] | 0.2200 [0.2160, 0.2239] |
| `output_words` | macro_within_level | -0.4635 [-0.4711, -0.4552] | 0.0247 [0.0197, 0.0298] | 1.2288 [1.2180, 1.2386] | 0.8070 [0.8007, 0.8131] |
| `output_words` | item_centered | -0.1605 [-0.1802, -0.1395] | 0.1848 [0.1736, 0.1970] | 1.1256 [1.1047, 1.1450] | 0.7871 [0.7750, 0.7981] |
| `output_words` | pooled | -0.2603 [-0.2770, -0.2416] | 0.1531 [0.1432, 0.1642] | 1.2170 [1.1977, 1.2340] | 0.8096 [0.7983, 0.8195] |
| `prompt_to_output_byte_ratio` | macro_within_level | 0.5946 [0.5878, 0.6011] | 0.7261 [0.7190, 0.7334] | 0.1706 [0.1649, 0.1766] | 0.1056 [0.0993, 0.1118] |
| `prompt_to_output_byte_ratio` | item_centered | 0.9162 [0.9147, 0.9178] | 0.9300 [0.9271, 0.9327] | 0.0489 [0.0469, 0.0507] | 0.0419 [0.0390, 0.0449] |
| `prompt_to_output_byte_ratio` | pooled | 0.9226 [0.9211, 0.9239] | 0.9197 [0.9163, 0.9227] | 0.0341 [0.0320, 0.0360] | 0.0430 [0.0398, 0.0464] |
| `word_type_coverage` | macro_within_level | 0.7658 [0.7607, 0.7707] | 0.8271 [0.8233, 0.8308] | -0.0005 [-0.0042, 0.0031] | 0.0046 [0.0019, 0.0071] |
| `word_type_coverage` | item_centered | 0.9662 [0.9652, 0.9671] | 0.9753 [0.9745, 0.9761] | -0.0011 [-0.0022, -0.0002] | -0.0034 [-0.0041, -0.0028] |
| `word_type_coverage` | pooled | 0.9567 [0.9556, 0.9578] | 0.9671 [0.9661, 0.9680] | -0.0000 [-0.0015, 0.0010] | -0.0044 [-0.0054, -0.0035] |
| `word_token_coverage` | macro_within_level | 0.7426 [0.7375, 0.7480] | 0.8143 [0.8103, 0.8183] | 0.0227 [0.0191, 0.0263] | 0.0174 [0.0144, 0.0203] |
| `word_token_coverage` | item_centered | 0.9704 [0.9696, 0.9712] | 0.9808 [0.9801, 0.9814] | -0.0053 [-0.0064, -0.0044] | -0.0089 [-0.0097, -0.0081] |
| `word_token_coverage` | pooled | 0.9646 [0.9637, 0.9654] | 0.9724 [0.9716, 0.9732] | -0.0079 [-0.0095, -0.0067] | -0.0097 [-0.0108, -0.0087] |
| `word_bigram_coverage` | macro_within_level | 0.6547 [0.6473, 0.6618] | 0.7711 [0.7661, 0.7758] | 0.1106 [0.1045, 0.1167] | 0.0606 [0.0565, 0.0647] |
| `word_bigram_coverage` | item_centered | 0.9345 [0.9322, 0.9366] | 0.9428 [0.9409, 0.9445] | 0.0306 [0.0291, 0.0322] | 0.0291 [0.0280, 0.0303] |
| `word_bigram_coverage` | pooled | 0.9293 [0.9272, 0.9314] | 0.9364 [0.9344, 0.9381] | 0.0273 [0.0256, 0.0290] | 0.0264 [0.0252, 0.0276] |
| `char3_coverage` | macro_within_level | 0.7130 [0.7076, 0.7187] | 0.8021 [0.7980, 0.8062] | 0.0523 [0.0485, 0.0561] | 0.0296 [0.0265, 0.0325] |
| `char3_coverage` | item_centered | 0.9674 [0.9666, 0.9681] | 0.9770 [0.9764, 0.9776] | -0.0023 [-0.0034, -0.0014] | -0.0051 [-0.0060, -0.0043] |
| `char3_coverage` | pooled | 0.9598 [0.9589, 0.9606] | 0.9696 [0.9688, 0.9702] | -0.0031 [-0.0047, -0.0019] | -0.0068 [-0.0081, -0.0057] |
| `char5_coverage` | macro_within_level | 0.7350 [0.7294, 0.7406] | 0.8085 [0.8047, 0.8126] | 0.0303 [0.0267, 0.0340] | 0.0232 [0.0204, 0.0257] |
| `char5_coverage` | item_centered | 0.9620 [0.9608, 0.9632] | 0.9715 [0.9704, 0.9726] | 0.0031 [0.0022, 0.0038] | 0.0004 [-0.0002, 0.0009] |
| `char5_coverage` | pooled | 0.9555 [0.9543, 0.9566] | 0.9632 [0.9620, 0.9644] | 0.0012 [-0.0002, 0.0022] | -0.0004 [-0.0013, 0.0002] |
| `char8_coverage` | macro_within_level | 0.6843 [0.6772, 0.6918] | 0.7849 [0.7802, 0.7896] | 0.0810 [0.0755, 0.0867] | 0.0468 [0.0433, 0.0502] |
| `char8_coverage` | item_centered | 0.9333 [0.9307, 0.9358] | 0.9448 [0.9428, 0.9465] | 0.0318 [0.0300, 0.0336] | 0.0271 [0.0261, 0.0283] |
| `char8_coverage` | pooled | 0.9247 [0.9221, 0.9272] | 0.9367 [0.9348, 0.9386] | 0.0319 [0.0300, 0.0338] | 0.0260 [0.0248, 0.0272] |
| `rouge_l_recall` | macro_within_level | 0.7934 [0.7892, 0.7976] | 0.8390 [0.8353, 0.8428] | -0.0281 [-0.0316, -0.0248] | -0.0073 [-0.0105, -0.0043] |
| `rouge_l_recall` | item_centered | 0.9716 [0.9707, 0.9724] | 0.9774 [0.9766, 0.9782] | -0.0065 [-0.0076, -0.0055] | -0.0055 [-0.0062, -0.0048] |
| `rouge_l_recall` | pooled | 0.9700 [0.9692, 0.9708] | 0.9718 [0.9708, 0.9726] | -0.0134 [-0.0149, -0.0122] | -0.0090 [-0.0100, -0.0081] |
| `output_type_token_ratio` | macro_within_level | 0.2545 [0.2428, 0.2660] | 0.4955 [0.4876, 0.5035] | 0.5108 [0.4981, 0.5230] | 0.3362 [0.3282, 0.3444] |
| `output_type_token_ratio` | item_centered | 0.0188 [-0.0007, 0.0388] | 0.3460 [0.3323, 0.3604] | 0.9463 [0.9264, 0.9663] | 0.6259 [0.6114, 0.6398] |
| `output_type_token_ratio` | pooled | 0.0404 [0.0232, 0.0584] | 0.3622 [0.3508, 0.3741] | 0.9162 [0.8978, 0.9339] | 0.6006 [0.5884, 0.6120] |
| `output_bigram_repeat_fraction` | macro_within_level | -0.1801 [-0.1926, -0.1681] | 0.1932 [0.1846, 0.2013] | 0.9454 [0.9323, 0.9588] | 0.6385 [0.6295, 0.6480] |
| `output_bigram_repeat_fraction` | item_centered | 0.1234 [0.1038, 0.1419] | 0.4556 [0.4428, 0.4681] | 0.8417 [0.8233, 0.8612] | 0.5163 [0.5040, 0.5290] |
| `output_bigram_repeat_fraction` | pooled | 0.0570 [0.0393, 0.0733] | 0.4019 [0.3914, 0.4118] | 0.8997 [0.8832, 0.9172] | 0.5608 [0.5508, 0.5716] |
| `output_self_bits_per_byte` | macro_within_level | 0.2938 [0.2819, 0.3058] | 0.5287 [0.5207, 0.5368] | 0.4715 [0.4586, 0.4842] | 0.3030 [0.2950, 0.3110] |
| `output_self_bits_per_byte` | item_centered | 0.1164 [0.0985, 0.1339] | 0.4020 [0.3888, 0.4157] | 0.8487 [0.8312, 0.8664] | 0.5699 [0.5561, 0.5832] |
| `output_self_bits_per_byte` | pooled | 0.1217 [0.1040, 0.1389] | 0.4178 [0.4064, 0.4290] | 0.8349 [0.8179, 0.8529] | 0.5450 [0.5337, 0.5565] |

# Table 6 — Observed-cohort generation-model/domain robustness

| Dimension | Subgroup | Comparison | Evaluator | Candidate/heuristic | Macro within-level ρ | Macro pairwise_continuous_alpha_z |
|---|---|---|---|---|---:|---:|
| generation_model | claude-opus-4-8 | BB↔H | — | `prompt_bytes` | 0.1981 [0.1768, 0.2200] | 0.2006 [0.1804, 0.2203] |
| generation_model | claude-opus-4-8 | BB↔H | — | `output_bytes` | -0.4376 [-0.4531, -0.4202] | -0.3156 [-0.3321, -0.3001] |
| generation_model | claude-opus-4-8 | BB↔H | — | `prompt_words` | 0.1947 [0.1729, 0.2166] | 0.2177 [0.1968, 0.2375] |
| generation_model | claude-opus-4-8 | BB↔H | — | `output_words` | -0.4872 [-0.5014, -0.4714] | -0.3626 [-0.3772, -0.3488] |
| generation_model | claude-opus-4-8 | BB↔H | — | `prompt_to_output_byte_ratio` | 0.7156 [0.7037, 0.7268] | 0.7335 [0.7164, 0.7490] |
| generation_model | claude-opus-4-8 | BB↔H | — | `word_type_coverage` | 0.9091 [0.9039, 0.9138] | 0.9259 [0.9198, 0.9328] |
| generation_model | claude-opus-4-8 | BB↔H | — | `word_token_coverage` | 0.8955 [0.8887, 0.9015] | 0.9062 [0.9000, 0.9123] |
| generation_model | claude-opus-4-8 | BB↔H | — | `word_bigram_coverage` | 0.8229 [0.8125, 0.8326] | 0.8413 [0.8226, 0.8617] |
| generation_model | claude-opus-4-8 | BB↔H | — | `char3_coverage` | 0.8731 [0.8662, 0.8794] | 0.8904 [0.8814, 0.8980] |
| generation_model | claude-opus-4-8 | BB↔H | — | `char5_coverage` | 0.9132 [0.9070, 0.9189] | 0.9310 [0.9195, 0.9408] |
| generation_model | claude-opus-4-8 | BB↔H | — | `char8_coverage` | 0.8660 [0.8572, 0.8737] | 0.8822 [0.8669, 0.8978] |
| generation_model | claude-opus-4-8 | BB↔H | — | `rouge_l_recall` | 0.9016 [0.8954, 0.9071] | 0.9123 [0.9043, 0.9194] |
| generation_model | claude-opus-4-8 | BB↔H | — | `output_type_token_ratio` | 0.1809 [0.1600, 0.2024] | 0.2183 [0.1936, 0.2408] |
| generation_model | claude-opus-4-8 | BB↔H | — | `output_bigram_repeat_fraction` | -0.0997 [-0.1245, -0.0754] | -0.0988 [-0.1209, -0.0772] |
| generation_model | claude-opus-4-8 | BB↔H | — | `output_self_bits_per_byte` | 0.2474 [0.2251, 0.2693] | 0.3046 [0.2806, 0.3270] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `blackbox_actual_ratio` | 0.7378 [0.7259, 0.7491] | 0.7172 [0.6910, 0.7413] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `prompt_bytes` | 0.2297 [0.2101, 0.2499] | 0.2323 [0.2136, 0.2521] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `output_bytes` | -0.3071 [-0.3244, -0.2889] | -0.2591 [-0.2757, -0.2418] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `prompt_words` | 0.2516 [0.2315, 0.2723] | 0.2582 [0.2399, 0.2782] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `output_words` | -0.3512 [-0.3677, -0.3344] | -0.3006 [-0.3167, -0.2839] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `prompt_to_output_byte_ratio` | 0.5507 [0.5351, 0.5664] | 0.5164 [0.4744, 0.5580] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `word_type_coverage` | 0.7095 [0.6971, 0.7219] | 0.7111 [0.6934, 0.7277] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `word_token_coverage` | 0.6843 [0.6719, 0.6970] | 0.6757 [0.6555, 0.6959] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `word_bigram_coverage` | 0.6230 [0.6096, 0.6358] | 0.6527 [0.6397, 0.6660] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `char3_coverage` | 0.6460 [0.6327, 0.6595] | 0.6526 [0.6319, 0.6725] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `char5_coverage` | 0.6756 [0.6621, 0.6885] | 0.6910 [0.6745, 0.7077] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `char8_coverage` | 0.6499 [0.6365, 0.6624] | 0.6716 [0.6561, 0.6864] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `rouge_l_recall` | 0.7303 [0.7190, 0.7416] | 0.7178 [0.6980, 0.7374] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `output_type_token_ratio` | 0.2016 [0.1804, 0.2239] | 0.2089 [0.1849, 0.2327] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `output_bigram_repeat_fraction` | -0.1426 [-0.1675, -0.1192] | -0.1395 [-0.1630, -0.1170] |
| generation_model | claude-opus-4-8 | candidate↔φ | Llama | `output_self_bits_per_byte` | 0.2008 [0.1792, 0.2238] | 0.1985 [0.1656, 0.2293] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `blackbox_actual_ratio` | 0.6994 [0.6867, 0.7117] | 0.7146 [0.7012, 0.7296] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `prompt_bytes` | 0.2001 [0.1798, 0.2201] | 0.1653 [0.1444, 0.1856] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `output_bytes` | -0.3059 [-0.3228, -0.2891] | -0.2722 [-0.2862, -0.2578] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `prompt_words` | 0.2119 [0.1902, 0.2336] | 0.1778 [0.1565, 0.1996] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `output_words` | -0.3279 [-0.3435, -0.3112] | -0.3084 [-0.3221, -0.2942] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | 0.5079 [0.4917, 0.5231] | 0.5059 [0.4824, 0.5348] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `word_type_coverage` | 0.6960 [0.6831, 0.7080] | 0.7367 [0.7254, 0.7480] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `word_token_coverage` | 0.6582 [0.6447, 0.6712] | 0.6969 [0.6853, 0.7093] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `word_bigram_coverage` | 0.6049 [0.5902, 0.6199] | 0.6443 [0.6303, 0.6589] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `char3_coverage` | 0.6216 [0.6075, 0.6356] | 0.6629 [0.6499, 0.6764] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `char5_coverage` | 0.6557 [0.6419, 0.6697] | 0.6965 [0.6847, 0.7083] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `char8_coverage` | 0.6223 [0.6078, 0.6364] | 0.6493 [0.6356, 0.6632] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `rouge_l_recall` | 0.7040 [0.6912, 0.7155] | 0.7342 [0.7226, 0.7466] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `output_type_token_ratio` | 0.2010 [0.1801, 0.2231] | 0.2152 [0.1934, 0.2369] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | -0.1630 [-0.1869, -0.1406] | -0.1423 [-0.1641, -0.1213] |
| generation_model | claude-opus-4-8 | candidate↔φ | Mixtral | `output_self_bits_per_byte` | 0.2448 [0.2242, 0.2667] | 0.2463 [0.2247, 0.2703] |
| generation_model | claude-sonnet-5 | BB↔H | — | `prompt_bytes` | 0.1363 [0.1165, 0.1574] | 0.1181 [0.0986, 0.1404] |
| generation_model | claude-sonnet-5 | BB↔H | — | `output_bytes` | -0.4775 [-0.4937, -0.4606] | -0.3723 [-0.3891, -0.3565] |
| generation_model | claude-sonnet-5 | BB↔H | — | `prompt_words` | 0.1396 [0.1200, 0.1607] | 0.1324 [0.1115, 0.1556] |
| generation_model | claude-sonnet-5 | BB↔H | — | `output_words` | -0.5245 [-0.5395, -0.5087] | -0.4138 [-0.4287, -0.3993] |
| generation_model | claude-sonnet-5 | BB↔H | — | `prompt_to_output_byte_ratio` | 0.7033 [0.6928, 0.7135] | 0.7080 [0.6955, 0.7203] |
| generation_model | claude-sonnet-5 | BB↔H | — | `word_type_coverage` | 0.8799 [0.8739, 0.8851] | 0.9162 [0.9111, 0.9205] |
| generation_model | claude-sonnet-5 | BB↔H | — | `word_token_coverage` | 0.8745 [0.8684, 0.8800] | 0.8960 [0.8895, 0.9020] |
| generation_model | claude-sonnet-5 | BB↔H | — | `word_bigram_coverage` | 0.7383 [0.7278, 0.7476] | 0.8264 [0.8119, 0.8387] |
| generation_model | claude-sonnet-5 | BB↔H | — | `char3_coverage` | 0.8343 [0.8274, 0.8408] | 0.8568 [0.8498, 0.8631] |
| generation_model | claude-sonnet-5 | BB↔H | — | `char5_coverage` | 0.8877 [0.8816, 0.8932] | 0.9301 [0.9246, 0.9347] |
| generation_model | claude-sonnet-5 | BB↔H | — | `char8_coverage` | 0.7991 [0.7898, 0.8073] | 0.8644 [0.8513, 0.8757] |
| generation_model | claude-sonnet-5 | BB↔H | — | `rouge_l_recall` | 0.8720 [0.8657, 0.8776] | 0.8999 [0.8941, 0.9057] |
| generation_model | claude-sonnet-5 | BB↔H | — | `output_type_token_ratio` | 0.2200 [0.1980, 0.2405] | 0.2588 [0.2367, 0.2798] |
| generation_model | claude-sonnet-5 | BB↔H | — | `output_bigram_repeat_fraction` | -0.1025 [-0.1257, -0.0786] | -0.1113 [-0.1324, -0.0875] |
| generation_model | claude-sonnet-5 | BB↔H | — | `output_self_bits_per_byte` | 0.2417 [0.2196, 0.2640] | 0.3358 [0.3109, 0.3598] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `blackbox_actual_ratio` | 0.7067 [0.6959, 0.7171] | 0.7216 [0.7092, 0.7333] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `prompt_bytes` | 0.1671 [0.1476, 0.1878] | 0.1862 [0.1666, 0.2074] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `output_bytes` | -0.3263 [-0.3450, -0.3076] | -0.2840 [-0.3005, -0.2674] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `prompt_words` | 0.1927 [0.1734, 0.2132] | 0.2117 [0.1915, 0.2332] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `output_words` | -0.3654 [-0.3825, -0.3474] | -0.3223 [-0.3377, -0.3060] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `prompt_to_output_byte_ratio` | 0.5097 [0.4948, 0.5246] | 0.5105 [0.4903, 0.5299] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `word_type_coverage` | 0.6847 [0.6734, 0.6955] | 0.7077 [0.6948, 0.7203] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `word_token_coverage` | 0.6570 [0.6453, 0.6681] | 0.6766 [0.6623, 0.6905] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `word_bigram_coverage` | 0.5749 [0.5620, 0.5877] | 0.6325 [0.6159, 0.6484] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `char3_coverage` | 0.5805 [0.5669, 0.5933] | 0.6219 [0.6063, 0.6365] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `char5_coverage` | 0.6424 [0.6302, 0.6533] | 0.6808 [0.6666, 0.6938] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `char8_coverage` | 0.6052 [0.5921, 0.6175] | 0.6483 [0.6325, 0.6632] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `rouge_l_recall` | 0.7143 [0.7039, 0.7241] | 0.7307 [0.7184, 0.7428] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `output_type_token_ratio` | 0.2262 [0.2043, 0.2460] | 0.2411 [0.2190, 0.2619] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `output_bigram_repeat_fraction` | -0.1231 [-0.1450, -0.1006] | -0.1301 [-0.1531, -0.1069] |
| generation_model | claude-sonnet-5 | candidate↔φ | Llama | `output_self_bits_per_byte` | 0.1909 [0.1682, 0.2119] | 0.2289 [0.2054, 0.2514] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `blackbox_actual_ratio` | 0.6317 [0.6185, 0.6444] | 0.7021 [0.6891, 0.7146] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `prompt_bytes` | 0.1260 [0.1062, 0.1458] | 0.1020 [0.0821, 0.1243] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `output_bytes` | -0.3187 [-0.3362, -0.3015] | -0.3035 [-0.3200, -0.2869] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `prompt_words` | 0.1576 [0.1379, 0.1776] | 0.1226 [0.1018, 0.1460] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `output_words` | -0.3302 [-0.3476, -0.3124] | -0.3285 [-0.3446, -0.3116] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | 0.4496 [0.4330, 0.4661] | 0.4992 [0.4770, 0.5200] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `word_type_coverage` | 0.6154 [0.6023, 0.6281] | 0.7025 [0.6892, 0.7143] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `word_token_coverage` | 0.5726 [0.5586, 0.5863] | 0.6665 [0.6523, 0.6798] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `word_bigram_coverage` | 0.5253 [0.5110, 0.5395] | 0.6242 [0.6067, 0.6398] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `char3_coverage` | 0.5102 [0.4949, 0.5252] | 0.6075 [0.5916, 0.6220] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `char5_coverage` | 0.5777 [0.5640, 0.5909] | 0.6647 [0.6505, 0.6774] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `char8_coverage` | 0.5364 [0.5220, 0.5505] | 0.6140 [0.5967, 0.6298] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `rouge_l_recall` | 0.6436 [0.6308, 0.6557] | 0.7244 [0.7119, 0.7360] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `output_type_token_ratio` | 0.2159 [0.1946, 0.2364] | 0.2359 [0.2140, 0.2566] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | -0.1443 [-0.1664, -0.1231] | -0.1330 [-0.1555, -0.1117] |
| generation_model | claude-sonnet-5 | candidate↔φ | Mixtral | `output_self_bits_per_byte` | 0.2155 [0.1947, 0.2359] | 0.2627 [0.2398, 0.2849] |
| generation_model | gemini-3.6-flash | BB↔H | — | `prompt_bytes` | 0.2958 [0.2771, 0.3147] | 0.3276 [0.3107, 0.3459] |
| generation_model | gemini-3.6-flash | BB↔H | — | `output_bytes` | -0.4069 [-0.4200, -0.3927] | -0.3138 [-0.3315, -0.2976] |
| generation_model | gemini-3.6-flash | BB↔H | — | `prompt_words` | 0.3139 [0.2950, 0.3339] | 0.3444 [0.3254, 0.3643] |
| generation_model | gemini-3.6-flash | BB↔H | — | `output_words` | -0.4387 [-0.4516, -0.4253] | -0.3390 [-0.3571, -0.3226] |
| generation_model | gemini-3.6-flash | BB↔H | — | `prompt_to_output_byte_ratio` | 0.7386 [0.7281, 0.7487] | 0.7656 [0.7560, 0.7776] |
| generation_model | gemini-3.6-flash | BB↔H | — | `word_type_coverage` | 0.8989 [0.8938, 0.9034] | 0.9209 [0.9143, 0.9268] |
| generation_model | gemini-3.6-flash | BB↔H | — | `word_token_coverage` | 0.8739 [0.8670, 0.8803] | 0.8977 [0.8925, 0.9033] |
| generation_model | gemini-3.6-flash | BB↔H | — | `word_bigram_coverage` | 0.6524 [0.6411, 0.6633] | 0.7724 [0.7090, 0.8114] |
| generation_model | gemini-3.6-flash | BB↔H | — | `char3_coverage` | 0.8438 [0.8358, 0.8512] | 0.8655 [0.8582, 0.8730] |
| generation_model | gemini-3.6-flash | BB↔H | — | `char5_coverage` | 0.8508 [0.8434, 0.8578] | 0.8911 [0.8739, 0.9038] |
| generation_model | gemini-3.6-flash | BB↔H | — | `char8_coverage` | 0.7453 [0.7350, 0.7546] | 0.8221 [0.7889, 0.8451] |
| generation_model | gemini-3.6-flash | BB↔H | — | `rouge_l_recall` | 0.8670 [0.8604, 0.8725] | 0.8789 [0.8735, 0.8875] |
| generation_model | gemini-3.6-flash | BB↔H | — | `output_type_token_ratio` | 0.3986 [0.3811, 0.4150] | 0.4013 [0.3828, 0.4201] |
| generation_model | gemini-3.6-flash | BB↔H | — | `output_bigram_repeat_fraction` | -0.3086 [-0.3277, -0.2883] | -0.3060 [-0.3269, -0.2874] |
| generation_model | gemini-3.6-flash | BB↔H | — | `output_self_bits_per_byte` | 0.4213 [0.4039, 0.4380] | 0.4709 [0.4531, 0.4890] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `blackbox_actual_ratio` | 0.6914 [0.6793, 0.7026] | 0.7122 [0.6947, 0.7283] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `prompt_bytes` | 0.2738 [0.2553, 0.2922] | 0.2937 [0.2777, 0.3103] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `output_bytes` | -0.3035 [-0.3182, -0.2873] | -0.2818 [-0.2970, -0.2672] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `prompt_words` | 0.3345 [0.3159, 0.3525] | 0.3295 [0.3128, 0.3467] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `output_words` | -0.3150 [-0.3286, -0.3006] | -0.2906 [-0.3053, -0.2765] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `prompt_to_output_byte_ratio` | 0.5257 [0.5112, 0.5399] | 0.5728 [0.5546, 0.5914] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `word_type_coverage` | 0.6904 [0.6782, 0.7017] | 0.7008 [0.6815, 0.7200] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `word_token_coverage` | 0.6684 [0.6563, 0.6799] | 0.6820 [0.6624, 0.7016] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `word_bigram_coverage` | 0.4585 [0.4426, 0.4746] | 0.5489 [0.5088, 0.5900] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `char3_coverage` | 0.6253 [0.6126, 0.6369] | 0.6530 [0.6337, 0.6726] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `char5_coverage` | 0.6077 [0.5935, 0.6207] | 0.6326 [0.6091, 0.6584] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `char8_coverage` | 0.5209 [0.5044, 0.5365] | 0.5782 [0.5562, 0.6033] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `rouge_l_recall` | 0.7259 [0.7149, 0.7364] | 0.7353 [0.7192, 0.7526] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `output_type_token_ratio` | 0.4646 [0.4488, 0.4795] | 0.4587 [0.4428, 0.4746] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `output_bigram_repeat_fraction` | -0.4077 [-0.4249, -0.3903] | -0.3846 [-0.4018, -0.3671] |
| generation_model | gemini-3.6-flash | candidate↔φ | Llama | `output_self_bits_per_byte` | 0.4626 [0.4465, 0.4779] | 0.4664 [0.4488, 0.4846] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `blackbox_actual_ratio` | 0.6621 [0.6492, 0.6738] | 0.6944 [0.6801, 0.7083] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `prompt_bytes` | 0.2293 [0.2113, 0.2469] | 0.2284 [0.2111, 0.2452] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `output_bytes` | -0.3269 [-0.3417, -0.3115] | -0.3177 [-0.3318, -0.3034] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `prompt_words` | 0.2926 [0.2747, 0.3097] | 0.2635 [0.2461, 0.2810] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `output_words` | -0.3317 [-0.3450, -0.3177] | -0.3191 [-0.3329, -0.3053] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | 0.4999 [0.4854, 0.5140] | 0.5525 [0.5367, 0.5698] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `word_type_coverage` | 0.6527 [0.6401, 0.6647] | 0.6774 [0.6626, 0.6922] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `word_token_coverage` | 0.6344 [0.6216, 0.6467] | 0.6599 [0.6462, 0.6745] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `word_bigram_coverage` | 0.4333 [0.4172, 0.4491] | 0.5329 [0.4904, 0.5670] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `char3_coverage` | 0.5988 [0.5858, 0.6110] | 0.6354 [0.6207, 0.6501] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `char5_coverage` | 0.5790 [0.5643, 0.5919] | 0.6169 [0.5982, 0.6350] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `char8_coverage` | 0.4848 [0.4686, 0.5002] | 0.5573 [0.5325, 0.5797] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `rouge_l_recall` | 0.6967 [0.6849, 0.7076] | 0.7137 [0.7011, 0.7304] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `output_type_token_ratio` | 0.4665 [0.4504, 0.4825] | 0.4573 [0.4416, 0.4731] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | -0.4088 [-0.4253, -0.3908] | -0.3756 [-0.3926, -0.3585] |
| generation_model | gemini-3.6-flash | candidate↔φ | Mixtral | `output_self_bits_per_byte` | 0.4724 [0.4563, 0.4878] | 0.4774 [0.4587, 0.4948] |
| generation_model | gpt-5.5 | BB↔H | — | `prompt_bytes` | 0.1301 [0.1118, 0.1488] | 0.1413 [0.1241, 0.1597] |
| generation_model | gpt-5.5 | BB↔H | — | `output_bytes` | -0.5353 [-0.5471, -0.5219] | -0.4555 [-0.4687, -0.4424] |
| generation_model | gpt-5.5 | BB↔H | — | `prompt_words` | 0.1469 [0.1298, 0.1655] | 0.1622 [0.1443, 0.1810] |
| generation_model | gpt-5.5 | BB↔H | — | `output_words` | -0.5643 [-0.5755, -0.5520] | -0.4762 [-0.4893, -0.4634] |
| generation_model | gpt-5.5 | BB↔H | — | `prompt_to_output_byte_ratio` | 0.7289 [0.7178, 0.7388] | 0.6979 [0.6813, 0.7145] |
| generation_model | gpt-5.5 | BB↔H | — | `word_type_coverage` | 0.8186 [0.8105, 0.8263] | 0.8456 [0.8342, 0.8560] |
| generation_model | gpt-5.5 | BB↔H | — | `word_token_coverage` | 0.8479 [0.8404, 0.8549] | 0.8666 [0.8554, 0.8763] |
| generation_model | gpt-5.5 | BB↔H | — | `word_bigram_coverage` | 0.6839 [0.6736, 0.6948] | 0.7136 [0.6983, 0.7298] |
| generation_model | gpt-5.5 | BB↔H | — | `char3_coverage` | 0.8758 [0.8691, 0.8818] | 0.8869 [0.8775, 0.8959] |
| generation_model | gpt-5.5 | BB↔H | — | `char5_coverage` | 0.8603 [0.8527, 0.8667] | 0.8862 [0.8723, 0.8978] |
| generation_model | gpt-5.5 | BB↔H | — | `char8_coverage` | 0.7768 [0.7676, 0.7854] | 0.8129 [0.7945, 0.8296] |
| generation_model | gpt-5.5 | BB↔H | — | `rouge_l_recall` | 0.8396 [0.8320, 0.8471] | 0.8516 [0.8397, 0.8623] |
| generation_model | gpt-5.5 | BB↔H | — | `output_type_token_ratio` | 0.1749 [0.1564, 0.1923] | 0.1985 [0.1793, 0.2176] |
| generation_model | gpt-5.5 | BB↔H | — | `output_bigram_repeat_fraction` | -0.0331 [-0.0519, -0.0133] | -0.0087 [-0.0282, 0.0096] |
| generation_model | gpt-5.5 | BB↔H | — | `output_self_bits_per_byte` | 0.2056 [0.1874, 0.2232] | 0.2631 [0.2418, 0.2828] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `blackbox_actual_ratio` | 0.6502 [0.6385, 0.6614] | 0.6733 [0.6603, 0.6856] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `prompt_bytes` | 0.2234 [0.2048, 0.2429] | 0.2319 [0.2139, 0.2507] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `output_bytes` | -0.2980 [-0.3125, -0.2830] | -0.2962 [-0.3095, -0.2823] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `prompt_words` | 0.2759 [0.2580, 0.2946] | 0.2684 [0.2503, 0.2867] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `output_words` | -0.3098 [-0.3240, -0.2948] | -0.3093 [-0.3226, -0.2955] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `prompt_to_output_byte_ratio` | 0.4094 [0.3952, 0.4223] | 0.4042 [0.3830, 0.4259] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `word_type_coverage` | 0.6766 [0.6646, 0.6874] | 0.6896 [0.6760, 0.7031] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `word_token_coverage` | 0.6595 [0.6476, 0.6705] | 0.6639 [0.6496, 0.6777] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `word_bigram_coverage` | 0.5448 [0.5312, 0.5585] | 0.5724 [0.5575, 0.5876] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `char3_coverage` | 0.6228 [0.6106, 0.6343] | 0.6484 [0.6365, 0.6618] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `char5_coverage` | 0.6285 [0.6167, 0.6397] | 0.6536 [0.6428, 0.6661] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `char8_coverage` | 0.5796 [0.5664, 0.5921] | 0.6125 [0.5990, 0.6261] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `rouge_l_recall` | 0.6824 [0.6710, 0.6933] | 0.6954 [0.6819, 0.7078] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `output_type_token_ratio` | 0.1740 [0.1567, 0.1917] | 0.1797 [0.1613, 0.1976] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `output_bigram_repeat_fraction` | -0.0998 [-0.1184, -0.0812] | -0.0798 [-0.0978, -0.0618] |
| generation_model | gpt-5.5 | candidate↔φ | Llama | `output_self_bits_per_byte` | 0.1564 [0.1383, 0.1746] | 0.1732 [0.1544, 0.1931] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `blackbox_actual_ratio` | 0.5872 [0.5743, 0.5998] | 0.6019 [0.5866, 0.6170] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `prompt_bytes` | 0.2165 [0.1978, 0.2366] | 0.2197 [0.2015, 0.2382] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `output_bytes` | -0.2540 [-0.2690, -0.2387] | -0.2723 [-0.2868, -0.2577] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `prompt_words` | 0.2700 [0.2512, 0.2889] | 0.2532 [0.2352, 0.2719] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `output_words` | -0.2558 [-0.2711, -0.2404] | -0.2797 [-0.2945, -0.2653] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | 0.3413 [0.3263, 0.3559] | 0.3490 [0.3308, 0.3682] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `word_type_coverage` | 0.6061 [0.5927, 0.6195] | 0.6116 [0.5937, 0.6304] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `word_token_coverage` | 0.5905 [0.5767, 0.6045] | 0.5852 [0.5674, 0.6040] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `word_bigram_coverage` | 0.5219 [0.5078, 0.5366] | 0.5365 [0.5167, 0.5561] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `char3_coverage` | 0.5678 [0.5546, 0.5806] | 0.5787 [0.5618, 0.5972] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `char5_coverage` | 0.5842 [0.5710, 0.5969] | 0.5896 [0.5732, 0.6085] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `char8_coverage` | 0.5428 [0.5287, 0.5567] | 0.5574 [0.5392, 0.5768] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `rouge_l_recall` | 0.6133 [0.6004, 0.6265] | 0.6141 [0.5969, 0.6327] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `output_type_token_ratio` | 0.1530 [0.1343, 0.1722] | 0.1523 [0.1331, 0.1712] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | -0.1024 [-0.1221, -0.0830] | -0.0688 [-0.0877, -0.0507] |
| generation_model | gpt-5.5 | candidate↔φ | Mixtral | `output_self_bits_per_byte` | 0.1398 [0.1210, 0.1591] | 0.1439 [0.1243, 0.1631] |
| generation_model | gpt-5.6-sol | BB↔H | — | `prompt_bytes` | 0.0051 [-0.0155, 0.0257] | 0.0161 [-0.0040, 0.0366] |
| generation_model | gpt-5.6-sol | BB↔H | — | `output_bytes` | -0.6106 [-0.6220, -0.5981] | -0.5077 [-0.5200, -0.4965] |
| generation_model | gpt-5.6-sol | BB↔H | — | `prompt_words` | 0.0377 [0.0180, 0.0574] | 0.0524 [0.0324, 0.0727] |
| generation_model | gpt-5.6-sol | BB↔H | — | `output_words` | -0.6178 [-0.6289, -0.6059] | -0.5174 [-0.5292, -0.5065] |
| generation_model | gpt-5.6-sol | BB↔H | — | `prompt_to_output_byte_ratio` | 0.7448 [0.7350, 0.7547] | 0.6939 [0.6745, 0.7176] |
| generation_model | gpt-5.6-sol | BB↔H | — | `word_type_coverage` | 0.8412 [0.8336, 0.8484] | 0.8522 [0.8425, 0.8608] |
| generation_model | gpt-5.6-sol | BB↔H | — | `word_token_coverage` | 0.8488 [0.8405, 0.8563] | 0.8523 [0.8417, 0.8620] |
| generation_model | gpt-5.6-sol | BB↔H | — | `word_bigram_coverage` | 0.6994 [0.6885, 0.7104] | 0.7573 [0.7422, 0.7709] |
| generation_model | gpt-5.6-sol | BB↔H | — | `char3_coverage` | 0.8677 [0.8598, 0.8745] | 0.8700 [0.8602, 0.8783] |
| generation_model | gpt-5.6-sol | BB↔H | — | `char5_coverage` | 0.8695 [0.8620, 0.8759] | 0.8830 [0.8735, 0.8906] |
| generation_model | gpt-5.6-sol | BB↔H | — | `char8_coverage` | 0.7825 [0.7735, 0.7908] | 0.8213 [0.8083, 0.8320] |
| generation_model | gpt-5.6-sol | BB↔H | — | `rouge_l_recall` | 0.8548 [0.8475, 0.8618] | 0.8472 [0.8365, 0.8569] |
| generation_model | gpt-5.6-sol | BB↔H | — | `output_type_token_ratio` | 0.1937 [0.1719, 0.2132] | 0.1935 [0.1702, 0.2150] |
| generation_model | gpt-5.6-sol | BB↔H | — | `output_bigram_repeat_fraction` | -0.0218 [-0.0435, 0.0003] | 0.0282 [0.0074, 0.0499] |
| generation_model | gpt-5.6-sol | BB↔H | — | `output_self_bits_per_byte` | 0.2884 [0.2674, 0.3080] | 0.3264 [0.3024, 0.3501] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `blackbox_actual_ratio` | 0.7108 [0.7009, 0.7206] | 0.7022 [0.6890, 0.7145] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `prompt_bytes` | 0.0593 [0.0397, 0.0788] | 0.0618 [0.0432, 0.0807] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `output_bytes` | -0.4376 [-0.4507, -0.4242] | -0.4063 [-0.4189, -0.3948] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `prompt_words` | 0.1261 [0.1065, 0.1444] | 0.1108 [0.0920, 0.1288] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `output_words` | -0.4294 [-0.4423, -0.4157] | -0.4027 [-0.4158, -0.3910] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `prompt_to_output_byte_ratio` | 0.4716 [0.4604, 0.4826] | 0.4354 [0.4063, 0.4676] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `word_type_coverage` | 0.7103 [0.6999, 0.7204] | 0.6801 [0.6662, 0.6936] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `word_token_coverage` | 0.6956 [0.6852, 0.7058] | 0.6567 [0.6416, 0.6715] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `word_bigram_coverage` | 0.5785 [0.5645, 0.5912] | 0.5940 [0.5800, 0.6070] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `char3_coverage` | 0.6600 [0.6496, 0.6705] | 0.6391 [0.6267, 0.6523] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `char5_coverage` | 0.6713 [0.6604, 0.6824] | 0.6498 [0.6383, 0.6627] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `char8_coverage` | 0.6067 [0.5944, 0.6187] | 0.6213 [0.6093, 0.6336] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `rouge_l_recall` | 0.7381 [0.7287, 0.7474] | 0.6915 [0.6780, 0.7052] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `output_type_token_ratio` | 0.2227 [0.2042, 0.2425] | 0.1996 [0.1797, 0.2197] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `output_bigram_repeat_fraction` | -0.1019 [-0.1236, -0.0826] | -0.0473 [-0.0672, -0.0284] |
| generation_model | gpt-5.6-sol | candidate↔φ | Llama | `output_self_bits_per_byte` | 0.2766 [0.2577, 0.2964] | 0.2506 [0.2296, 0.2723] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `blackbox_actual_ratio` | 0.6518 [0.6403, 0.6638] | 0.6453 [0.6308, 0.6596] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `prompt_bytes` | 0.0503 [0.0307, 0.0699] | 0.0381 [0.0193, 0.0578] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `output_bytes` | -0.4100 [-0.4238, -0.3958] | -0.4021 [-0.4146, -0.3902] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `prompt_words` | 0.1172 [0.0971, 0.1367] | 0.0851 [0.0655, 0.1051] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `output_words` | -0.4005 [-0.4145, -0.3860] | -0.3984 [-0.4112, -0.3865] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | 0.4235 [0.4113, 0.4357] | 0.4182 [0.3951, 0.4431] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `word_type_coverage` | 0.6444 [0.6318, 0.6563] | 0.6244 [0.6079, 0.6404] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `word_token_coverage` | 0.6278 [0.6157, 0.6398] | 0.6023 [0.5858, 0.6190] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `word_bigram_coverage` | 0.5267 [0.5116, 0.5414] | 0.5459 [0.5265, 0.5645] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `char3_coverage` | 0.6021 [0.5896, 0.6146] | 0.5914 [0.5761, 0.6063] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `char5_coverage` | 0.6165 [0.6039, 0.6292] | 0.6051 [0.5886, 0.6207] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `char8_coverage` | 0.5600 [0.5459, 0.5741] | 0.5667 [0.5491, 0.5841] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `rouge_l_recall` | 0.6674 [0.6564, 0.6785] | 0.6406 [0.6242, 0.6564] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `output_type_token_ratio` | 0.2302 [0.2103, 0.2488] | 0.2050 [0.1849, 0.2235] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | -0.1236 [-0.1440, -0.1036] | -0.0547 [-0.0749, -0.0345] |
| generation_model | gpt-5.6-sol | candidate↔φ | Mixtral | `output_self_bits_per_byte` | 0.2783 [0.2588, 0.2973] | 0.2561 [0.2342, 0.2758] |
| domain | arxiv | BB↔H | — | `prompt_bytes` | -0.0995 [-0.1218, -0.0764] | -0.1070 [-0.1279, -0.0849] |
| domain | arxiv | BB↔H | — | `output_bytes` | -0.7841 [-0.7969, -0.7708] | -0.7215 [-0.7334, -0.7090] |
| domain | arxiv | BB↔H | — | `prompt_words` | -0.0754 [-0.0967, -0.0531] | -0.0801 [-0.1009, -0.0585] |
| domain | arxiv | BB↔H | — | `output_words` | -0.7740 [-0.7871, -0.7602] | -0.7104 [-0.7228, -0.6974] |
| domain | arxiv | BB↔H | — | `prompt_to_output_byte_ratio` | 0.8932 [0.8861, 0.8997] | 0.9059 [0.9000, 0.9124] |
| domain | arxiv | BB↔H | — | `word_type_coverage` | 0.9088 [0.9025, 0.9147] | 0.9178 [0.9114, 0.9239] |
| domain | arxiv | BB↔H | — | `word_token_coverage` | 0.9023 [0.8949, 0.9089] | 0.9076 [0.9004, 0.9143] |
| domain | arxiv | BB↔H | — | `word_bigram_coverage` | 0.7434 [0.7318, 0.7550] | 0.8013 [0.7840, 0.8180] |
| domain | arxiv | BB↔H | — | `char3_coverage` | 0.9107 [0.9030, 0.9173] | 0.9123 [0.9053, 0.9185] |
| domain | arxiv | BB↔H | — | `char5_coverage` | 0.8939 [0.8864, 0.9008] | 0.9082 [0.8992, 0.9165] |
| domain | arxiv | BB↔H | — | `char8_coverage` | 0.8017 [0.7907, 0.8123] | 0.8562 [0.8423, 0.8686] |
| domain | arxiv | BB↔H | — | `rouge_l_recall` | 0.9064 [0.8993, 0.9128] | 0.9098 [0.9029, 0.9170] |
| domain | arxiv | BB↔H | — | `output_type_token_ratio` | 0.6020 [0.5837, 0.6205] | 0.6228 [0.6049, 0.6409] |
| domain | arxiv | BB↔H | — | `output_bigram_repeat_fraction` | -0.4664 [-0.4875, -0.4451] | -0.4663 [-0.4881, -0.4454] |
| domain | arxiv | BB↔H | — | `output_self_bits_per_byte` | 0.6780 [0.6612, 0.6941] | 0.7193 [0.7040, 0.7338] |
| domain | arxiv | candidate↔φ | Llama | `blackbox_actual_ratio` | 0.7951 [0.7856, 0.8040] | 0.8197 [0.8076, 0.8310] |
| domain | arxiv | candidate↔φ | Llama | `prompt_bytes` | 0.0381 [0.0115, 0.0639] | 0.0450 [0.0190, 0.0704] |
| domain | arxiv | candidate↔φ | Llama | `output_bytes` | -0.5959 [-0.6123, -0.5787] | -0.6042 [-0.6189, -0.5892] |
| domain | arxiv | candidate↔φ | Llama | `prompt_words` | 0.0807 [0.0546, 0.1063] | 0.0816 [0.0574, 0.1060] |
| domain | arxiv | candidate↔φ | Llama | `output_words` | -0.5895 [-0.6064, -0.5723] | -0.5945 [-0.6097, -0.5790] |
| domain | arxiv | candidate↔φ | Llama | `prompt_to_output_byte_ratio` | 0.7100 [0.6988, 0.7213] | 0.7403 [0.7205, 0.7594] |
| domain | arxiv | candidate↔φ | Llama | `word_type_coverage` | 0.7582 [0.7478, 0.7678] | 0.7877 [0.7761, 0.7989] |
| domain | arxiv | candidate↔φ | Llama | `word_token_coverage` | 0.7590 [0.7490, 0.7683] | 0.7895 [0.7772, 0.8019] |
| domain | arxiv | candidate↔φ | Llama | `word_bigram_coverage` | 0.6404 [0.6267, 0.6535] | 0.6939 [0.6818, 0.7072] |
| domain | arxiv | candidate↔φ | Llama | `char3_coverage` | 0.7601 [0.7503, 0.7697] | 0.7972 [0.7851, 0.8090] |
| domain | arxiv | candidate↔φ | Llama | `char5_coverage` | 0.7509 [0.7403, 0.7610] | 0.7791 [0.7669, 0.7923] |
| domain | arxiv | candidate↔φ | Llama | `char8_coverage` | 0.6934 [0.6798, 0.7068] | 0.7456 [0.7330, 0.7578] |
| domain | arxiv | candidate↔φ | Llama | `rouge_l_recall` | 0.7874 [0.7779, 0.7958] | 0.8055 [0.7932, 0.8195] |
| domain | arxiv | candidate↔φ | Llama | `output_type_token_ratio` | 0.4801 [0.4619, 0.4997] | 0.5184 [0.4995, 0.5387] |
| domain | arxiv | candidate↔φ | Llama | `output_bigram_repeat_fraction` | -0.3941 [-0.4143, -0.3749] | -0.4402 [-0.4600, -0.4209] |
| domain | arxiv | candidate↔φ | Llama | `output_self_bits_per_byte` | 0.5095 [0.4908, 0.5284] | 0.5490 [0.5270, 0.5701] |
| domain | arxiv | candidate↔φ | Mixtral | `blackbox_actual_ratio` | 0.8104 [0.8008, 0.8191] | 0.8343 [0.8247, 0.8429] |
| domain | arxiv | candidate↔φ | Mixtral | `prompt_bytes` | 0.0307 [0.0068, 0.0541] | 0.0238 [-0.0003, 0.0477] |
| domain | arxiv | candidate↔φ | Mixtral | `output_bytes` | -0.6077 [-0.6240, -0.5914] | -0.6137 [-0.6286, -0.5978] |
| domain | arxiv | candidate↔φ | Mixtral | `prompt_words` | 0.0592 [0.0349, 0.0824] | 0.0516 [0.0283, 0.0751] |
| domain | arxiv | candidate↔φ | Mixtral | `output_words` | -0.5993 [-0.6155, -0.5827] | -0.6021 [-0.6174, -0.5861] |
| domain | arxiv | candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | 0.7187 [0.7073, 0.7295] | 0.7468 [0.7297, 0.7624] |
| domain | arxiv | candidate↔φ | Mixtral | `word_type_coverage` | 0.7780 [0.7680, 0.7879] | 0.8068 [0.7976, 0.8158] |
| domain | arxiv | candidate↔φ | Mixtral | `word_token_coverage` | 0.7696 [0.7602, 0.7789] | 0.8041 [0.7944, 0.8129] |
| domain | arxiv | candidate↔φ | Mixtral | `word_bigram_coverage` | 0.6592 [0.6465, 0.6720] | 0.7117 [0.6972, 0.7253] |
| domain | arxiv | candidate↔φ | Mixtral | `char3_coverage` | 0.7810 [0.7715, 0.7896] | 0.8172 [0.8089, 0.8254] |
| domain | arxiv | candidate↔φ | Mixtral | `char5_coverage` | 0.7732 [0.7628, 0.7827] | 0.8071 [0.7978, 0.8153] |
| domain | arxiv | candidate↔φ | Mixtral | `char8_coverage` | 0.7132 [0.6999, 0.7255] | 0.7668 [0.7541, 0.7784] |
| domain | arxiv | candidate↔φ | Mixtral | `rouge_l_recall` | 0.7938 [0.7845, 0.8023] | 0.8173 [0.8081, 0.8264] |
| domain | arxiv | candidate↔φ | Mixtral | `output_type_token_ratio` | 0.4737 [0.4555, 0.4933] | 0.5119 [0.4932, 0.5312] |
| domain | arxiv | candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | -0.3887 [-0.4087, -0.3684] | -0.4308 [-0.4506, -0.4114] |
| domain | arxiv | candidate↔φ | Mixtral | `output_self_bits_per_byte` | 0.5084 [0.4904, 0.5264] | 0.5494 [0.5291, 0.5690] |
| domain | news | BB↔H | — | `prompt_bytes` | -0.0516 [-0.0707, -0.0329] | -0.0530 [-0.0723, -0.0328] |
| domain | news | BB↔H | — | `output_bytes` | -0.5709 [-0.5870, -0.5554] | -0.5298 [-0.5460, -0.5140] |
| domain | news | BB↔H | — | `prompt_words` | NA [NA, NA] | NA [NA, NA] |
| domain | news | BB↔H | — | `output_words` | -0.5392 [-0.5552, -0.5234] | -0.4956 [-0.5119, -0.4801] |
| domain | news | BB↔H | — | `prompt_to_output_byte_ratio` | 0.6894 [0.6772, 0.7009] | 0.6093 [0.5965, 0.6305] |
| domain | news | BB↔H | — | `word_type_coverage` | 0.9449 [0.9426, 0.9470] | 0.9454 [0.9430, 0.9478] |
| domain | news | BB↔H | — | `word_token_coverage` | 0.9484 [0.9460, 0.9505] | 0.9519 [0.9499, 0.9541] |
| domain | news | BB↔H | — | `word_bigram_coverage` | 0.8322 [0.8230, 0.8407] | 0.8491 [0.8393, 0.8589] |
| domain | news | BB↔H | — | `char3_coverage` | 0.9439 [0.9408, 0.9467] | 0.9445 [0.9417, 0.9472] |
| domain | news | BB↔H | — | `char5_coverage` | 0.9446 [0.9410, 0.9480] | 0.9401 [0.9363, 0.9439] |
| domain | news | BB↔H | — | `char8_coverage` | 0.8773 [0.8697, 0.8846] | 0.8824 [0.8747, 0.8904] |
| domain | news | BB↔H | — | `rouge_l_recall` | 0.9314 [0.9283, 0.9341] | 0.9296 [0.9266, 0.9328] |
| domain | news | BB↔H | — | `output_type_token_ratio` | 0.1412 [0.1253, 0.1571] | 0.1665 [0.1511, 0.1829] |
| domain | news | BB↔H | — | `output_bigram_repeat_fraction` | -0.0292 [-0.0489, -0.0122] | -0.0328 [-0.0530, -0.0143] |
| domain | news | BB↔H | — | `output_self_bits_per_byte` | 0.3083 [0.2919, 0.3246] | 0.3376 [0.3216, 0.3547] |
| domain | news | candidate↔φ | Llama | `blackbox_actual_ratio` | 0.7958 [0.7881, 0.8037] | 0.8218 [0.8138, 0.8298] |
| domain | news | candidate↔φ | Llama | `prompt_bytes` | 0.0675 [0.0489, 0.0849] | 0.0583 [0.0404, 0.0764] |
| domain | news | candidate↔φ | Llama | `output_bytes` | -0.3553 [-0.3699, -0.3412] | -0.3424 [-0.3561, -0.3288] |
| domain | news | candidate↔φ | Llama | `prompt_words` | NA [NA, NA] | NA [NA, NA] |
| domain | news | candidate↔φ | Llama | `output_words` | -0.3117 [-0.3260, -0.2978] | -0.2977 [-0.3110, -0.2847] |
| domain | news | candidate↔φ | Llama | `prompt_to_output_byte_ratio` | 0.4927 [0.4796, 0.5047] | 0.4323 [0.4131, 0.4575] |
| domain | news | candidate↔φ | Llama | `word_type_coverage` | 0.7840 [0.7764, 0.7918] | 0.8016 [0.7937, 0.8097] |
| domain | news | candidate↔φ | Llama | `word_token_coverage` | 0.7874 [0.7798, 0.7948] | 0.8096 [0.8016, 0.8175] |
| domain | news | candidate↔φ | Llama | `word_bigram_coverage` | 0.6930 [0.6824, 0.7035] | 0.7154 [0.7039, 0.7275] |
| domain | news | candidate↔φ | Llama | `char3_coverage` | 0.7593 [0.7510, 0.7676] | 0.7809 [0.7723, 0.7894] |
| domain | news | candidate↔φ | Llama | `char5_coverage` | 0.7726 [0.7642, 0.7807] | 0.7883 [0.7792, 0.7973] |
| domain | news | candidate↔φ | Llama | `char8_coverage` | 0.7302 [0.7198, 0.7405] | 0.7477 [0.7363, 0.7606] |
| domain | news | candidate↔φ | Llama | `rouge_l_recall` | 0.8266 [0.8198, 0.8334] | 0.8396 [0.8323, 0.8468] |
| domain | news | candidate↔φ | Llama | `output_type_token_ratio` | 0.0446 [0.0287, 0.0603] | 0.0745 [0.0587, 0.0897] |
| domain | news | candidate↔φ | Llama | `output_bigram_repeat_fraction` | -0.0075 [-0.0255, 0.0088] | -0.0173 [-0.0355, 0.0007] |
| domain | news | candidate↔φ | Llama | `output_self_bits_per_byte` | 0.1862 [0.1699, 0.2019] | 0.2242 [0.2087, 0.2390] |
| domain | news | candidate↔φ | Mixtral | `blackbox_actual_ratio` | 0.8284 [0.8206, 0.8361] | 0.8414 [0.8336, 0.8491] |
| domain | news | candidate↔φ | Mixtral | `prompt_bytes` | 0.0388 [0.0227, 0.0556] | 0.0332 [0.0168, 0.0498] |
| domain | news | candidate↔φ | Mixtral | `output_bytes` | -0.4001 [-0.4137, -0.3875] | -0.3801 [-0.3933, -0.3673] |
| domain | news | candidate↔φ | Mixtral | `prompt_words` | NA [NA, NA] | NA [NA, NA] |
| domain | news | candidate↔φ | Mixtral | `output_words` | -0.3544 [-0.3677, -0.3417] | -0.3330 [-0.3460, -0.3209] |
| domain | news | candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | 0.5337 [0.5212, 0.5458] | 0.4574 [0.4392, 0.4814] |
| domain | news | candidate↔φ | Mixtral | `word_type_coverage` | 0.8162 [0.8088, 0.8236] | 0.8256 [0.8183, 0.8329] |
| domain | news | candidate↔φ | Mixtral | `word_token_coverage` | 0.8213 [0.8137, 0.8285] | 0.8289 [0.8210, 0.8362] |
| domain | news | candidate↔φ | Mixtral | `word_bigram_coverage` | 0.7183 [0.7064, 0.7295] | 0.7386 [0.7278, 0.7491] |
| domain | news | candidate↔φ | Mixtral | `char3_coverage` | 0.7984 [0.7903, 0.8065] | 0.8073 [0.7997, 0.8152] |
| domain | news | candidate↔φ | Mixtral | `char5_coverage` | 0.8046 [0.7961, 0.8126] | 0.8131 [0.8053, 0.8212] |
| domain | news | candidate↔φ | Mixtral | `char8_coverage` | 0.7453 [0.7345, 0.7558] | 0.7656 [0.7549, 0.7767] |
| domain | news | candidate↔φ | Mixtral | `rouge_l_recall` | 0.8572 [0.8502, 0.8637] | 0.8584 [0.8510, 0.8654] |
| domain | news | candidate↔φ | Mixtral | `output_type_token_ratio` | 0.0745 [0.0594, 0.0892] | 0.0986 [0.0836, 0.1136] |
| domain | news | candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | -0.0328 [-0.0500, -0.0164] | -0.0381 [-0.0563, -0.0214] |
| domain | news | candidate↔φ | Mixtral | `output_self_bits_per_byte` | 0.2264 [0.2108, 0.2411] | 0.2498 [0.2347, 0.2641] |
| domain | patent | BB↔H | — | `prompt_bytes` | -0.1512 [-0.1676, -0.1338] | -0.1478 [-0.1639, -0.1301] |
| domain | patent | BB↔H | — | `output_bytes` | -0.7637 [-0.7748, -0.7531] | -0.7122 [-0.7227, -0.7013] |
| domain | patent | BB↔H | — | `prompt_words` | -0.1509 [-0.1673, -0.1341] | -0.1457 [-0.1631, -0.1284] |
| domain | patent | BB↔H | — | `output_words` | -0.7379 [-0.7489, -0.7271] | -0.6897 [-0.7002, -0.6789] |
| domain | patent | BB↔H | — | `prompt_to_output_byte_ratio` | 0.8150 [0.8074, 0.8227] | 0.8381 [0.8312, 0.8450] |
| domain | patent | BB↔H | — | `word_type_coverage` | 0.9428 [0.9399, 0.9453] | 0.9470 [0.9436, 0.9503] |
| domain | patent | BB↔H | — | `word_token_coverage` | 0.9461 [0.9437, 0.9481] | 0.9453 [0.9431, 0.9477] |
| domain | patent | BB↔H | — | `word_bigram_coverage` | 0.7872 [0.7786, 0.7950] | 0.8603 [0.8479, 0.8716] |
| domain | patent | BB↔H | — | `char3_coverage` | 0.9587 [0.9566, 0.9605] | 0.9539 [0.9517, 0.9562] |
| domain | patent | BB↔H | — | `char5_coverage` | 0.9179 [0.9131, 0.9224] | 0.9441 [0.9394, 0.9483] |
| domain | patent | BB↔H | — | `char8_coverage` | 0.8336 [0.8255, 0.8410] | 0.8973 [0.8894, 0.9047] |
| domain | patent | BB↔H | — | `rouge_l_recall` | 0.9447 [0.9421, 0.9471] | 0.9382 [0.9352, 0.9417] |
| domain | patent | BB↔H | — | `output_type_token_ratio` | 0.1553 [0.1381, 0.1719] | 0.1905 [0.1736, 0.2070] |
| domain | patent | BB↔H | — | `output_bigram_repeat_fraction` | -0.0064 [-0.0234, 0.0110] | -0.0154 [-0.0349, 0.0038] |
| domain | patent | BB↔H | — | `output_self_bits_per_byte` | 0.2793 [0.2638, 0.2950] | 0.3315 [0.3158, 0.3478] |
| domain | patent | candidate↔φ | Llama | `blackbox_actual_ratio` | 0.8033 [0.7960, 0.8099] | 0.8350 [0.8276, 0.8419] |
| domain | patent | candidate↔φ | Llama | `prompt_bytes` | 0.0516 [0.0342, 0.0687] | 0.0336 [0.0172, 0.0503] |
| domain | patent | candidate↔φ | Llama | `output_bytes` | -0.5468 [-0.5608, -0.5324] | -0.5928 [-0.6056, -0.5800] |
| domain | patent | candidate↔φ | Llama | `prompt_words` | 0.0600 [0.0422, 0.0778] | 0.0472 [0.0303, 0.0632] |
| domain | patent | candidate↔φ | Llama | `output_words` | -0.5246 [-0.5382, -0.5102] | -0.5709 [-0.5837, -0.5583] |
| domain | patent | candidate↔φ | Llama | `prompt_to_output_byte_ratio` | 0.6211 [0.6098, 0.6315] | 0.6912 [0.6785, 0.7035] |
| domain | patent | candidate↔φ | Llama | `word_type_coverage` | 0.8116 [0.8048, 0.8180] | 0.8190 [0.8118, 0.8267] |
| domain | patent | candidate↔φ | Llama | `word_token_coverage` | 0.7932 [0.7858, 0.8000] | 0.8184 [0.8101, 0.8269] |
| domain | patent | candidate↔φ | Llama | `word_bigram_coverage` | 0.7522 [0.7412, 0.7637] | 0.7649 [0.7532, 0.7774] |
| domain | patent | candidate↔φ | Llama | `char3_coverage` | 0.7799 [0.7715, 0.7879] | 0.8132 [0.8045, 0.8218] |
| domain | patent | candidate↔φ | Llama | `char5_coverage` | 0.7964 [0.7867, 0.8056] | 0.8103 [0.8009, 0.8195] |
| domain | patent | candidate↔φ | Llama | `char8_coverage` | 0.7913 [0.7807, 0.8019] | 0.7951 [0.7850, 0.8064] |
| domain | patent | candidate↔φ | Llama | `rouge_l_recall` | 0.8153 [0.8079, 0.8224] | 0.8251 [0.8164, 0.8345] |
| domain | patent | candidate↔φ | Llama | `output_type_token_ratio` | 0.0888 [0.0700, 0.1065] | 0.1396 [0.1223, 0.1571] |
| domain | patent | candidate↔φ | Llama | `output_bigram_repeat_fraction` | 0.0255 [0.0065, 0.0464] | -0.0114 [-0.0292, 0.0070] |
| domain | patent | candidate↔φ | Llama | `output_self_bits_per_byte` | 0.1456 [0.1269, 0.1634] | 0.2271 [0.2096, 0.2443] |
| domain | patent | candidate↔φ | Mixtral | `blackbox_actual_ratio` | 0.8215 [0.8141, 0.8285] | 0.8605 [0.8539, 0.8667] |
| domain | patent | candidate↔φ | Mixtral | `prompt_bytes` | 0.0099 [-0.0078, 0.0277] | -0.0149 [-0.0324, 0.0031] |
| domain | patent | candidate↔φ | Mixtral | `output_bytes` | -0.5590 [-0.5730, -0.5442] | -0.5954 [-0.6080, -0.5828] |
| domain | patent | candidate↔φ | Mixtral | `prompt_words` | 0.0203 [0.0019, 0.0379] | 0.0013 [-0.0171, 0.0182] |
| domain | patent | candidate↔φ | Mixtral | `output_words` | -0.5280 [-0.5416, -0.5130] | -0.5659 [-0.5786, -0.5529] |
| domain | patent | candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | 0.6269 [0.6144, 0.6381] | 0.6956 [0.6834, 0.7069] |
| domain | patent | candidate↔φ | Mixtral | `word_type_coverage` | 0.8337 [0.8268, 0.8402] | 0.8645 [0.8589, 0.8701] |
| domain | patent | candidate↔φ | Mixtral | `word_token_coverage` | 0.8079 [0.8000, 0.8152] | 0.8532 [0.8474, 0.8591] |
| domain | patent | candidate↔φ | Mixtral | `word_bigram_coverage` | 0.7669 [0.7566, 0.7774] | 0.8070 [0.7967, 0.8176] |
| domain | patent | candidate↔φ | Mixtral | `char3_coverage` | 0.7948 [0.7860, 0.8031] | 0.8415 [0.8342, 0.8490] |
| domain | patent | candidate↔φ | Mixtral | `char5_coverage` | 0.8142 [0.8054, 0.8225] | 0.8516 [0.8440, 0.8596] |
| domain | patent | candidate↔φ | Mixtral | `char8_coverage` | 0.8022 [0.7915, 0.8124] | 0.8257 [0.8168, 0.8354] |
| domain | patent | candidate↔φ | Mixtral | `rouge_l_recall` | 0.8268 [0.8188, 0.8345] | 0.8578 [0.8513, 0.8644] |
| domain | patent | candidate↔φ | Mixtral | `output_type_token_ratio` | 0.0766 [0.0585, 0.0939] | 0.1351 [0.1176, 0.1525] |
| domain | patent | candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | 0.0354 [0.0171, 0.0543] | -0.0007 [-0.0191, 0.0177] |
| domain | patent | candidate↔φ | Mixtral | `output_self_bits_per_byte` | 0.1582 [0.1399, 0.1757] | 0.2505 [0.2333, 0.2675] |
| domain | poetry | BB↔H | — | `prompt_bytes` | -0.1182 [-0.1374, -0.0984] | -0.1040 [-0.1245, -0.0835] |
| domain | poetry | BB↔H | — | `output_bytes` | -0.7192 [-0.7322, -0.7060] | -0.6710 [-0.6836, -0.6583] |
| domain | poetry | BB↔H | — | `prompt_words` | -0.1002 [-0.1202, -0.0790] | -0.0829 [-0.1044, -0.0606] |
| domain | poetry | BB↔H | — | `output_words` | -0.7079 [-0.7207, -0.6947] | -0.6613 [-0.6741, -0.6485] |
| domain | poetry | BB↔H | — | `prompt_to_output_byte_ratio` | 0.7768 [0.7658, 0.7872] | 0.7383 [0.7259, 0.7581] |
| domain | poetry | BB↔H | — | `word_type_coverage` | 0.9253 [0.9187, 0.9301] | 0.9331 [0.9213, 0.9408] |
| domain | poetry | BB↔H | — | `word_token_coverage` | 0.9239 [0.9172, 0.9289] | 0.9290 [0.9187, 0.9363] |
| domain | poetry | BB↔H | — | `word_bigram_coverage` | 0.7559 [0.7452, 0.7657] | 0.7988 [0.7831, 0.8119] |
| domain | poetry | BB↔H | — | `char3_coverage` | 0.9062 [0.8988, 0.9119] | 0.9170 [0.9060, 0.9242] |
| domain | poetry | BB↔H | — | `char5_coverage` | 0.9137 [0.9061, 0.9197] | 0.9213 [0.9085, 0.9303] |
| domain | poetry | BB↔H | — | `char8_coverage` | 0.7940 [0.7836, 0.8036] | 0.8269 [0.8103, 0.8398] |
| domain | poetry | BB↔H | — | `rouge_l_recall` | 0.9237 [0.9168, 0.9291] | 0.9239 [0.9127, 0.9318] |
| domain | poetry | BB↔H | — | `output_type_token_ratio` | 0.4251 [0.4099, 0.4398] | 0.4605 [0.4461, 0.4751] |
| domain | poetry | BB↔H | — | `output_bigram_repeat_fraction` | -0.2929 [-0.3089, -0.2761] | -0.3015 [-0.3205, -0.2838] |
| domain | poetry | BB↔H | — | `output_self_bits_per_byte` | 0.5422 [0.5268, 0.5589] | 0.5887 [0.5732, 0.6037] |
| domain | poetry | candidate↔φ | Llama | `blackbox_actual_ratio` | 0.8031 [0.7934, 0.8122] | 0.8094 [0.7955, 0.8218] |
| domain | poetry | candidate↔φ | Llama | `prompt_bytes` | -0.0124 [-0.0324, 0.0066] | -0.0029 [-0.0245, 0.0176] |
| domain | poetry | candidate↔φ | Llama | `output_bytes` | -0.5660 [-0.5812, -0.5511] | -0.5430 [-0.5591, -0.5276] |
| domain | poetry | candidate↔φ | Llama | `prompt_words` | 0.0016 [-0.0196, 0.0224] | 0.0075 [-0.0150, 0.0296] |
| domain | poetry | candidate↔φ | Llama | `output_words` | -0.5571 [-0.5724, -0.5426] | -0.5331 [-0.5494, -0.5175] |
| domain | poetry | candidate↔φ | Llama | `prompt_to_output_byte_ratio` | 0.6468 [0.6339, 0.6596] | 0.5803 [0.5539, 0.6203] |
| domain | poetry | candidate↔φ | Llama | `word_type_coverage` | 0.7960 [0.7859, 0.8052] | 0.8076 [0.7969, 0.8175] |
| domain | poetry | candidate↔φ | Llama | `word_token_coverage` | 0.7910 [0.7804, 0.8003] | 0.8004 [0.7893, 0.8101] |
| domain | poetry | candidate↔φ | Llama | `word_bigram_coverage` | 0.6526 [0.6406, 0.6643] | 0.6892 [0.6757, 0.7033] |
| domain | poetry | candidate↔φ | Llama | `char3_coverage` | 0.7707 [0.7605, 0.7804] | 0.7892 [0.7796, 0.7986] |
| domain | poetry | candidate↔φ | Llama | `char5_coverage` | 0.7787 [0.7690, 0.7879] | 0.7968 [0.7865, 0.8062] |
| domain | poetry | candidate↔φ | Llama | `char8_coverage` | 0.6835 [0.6717, 0.6951] | 0.7160 [0.7023, 0.7294] |
| domain | poetry | candidate↔φ | Llama | `rouge_l_recall` | 0.8215 [0.8130, 0.8299] | 0.8290 [0.8194, 0.8378] |
| domain | poetry | candidate↔φ | Llama | `output_type_token_ratio` | 0.3506 [0.3343, 0.3666] | 0.3808 [0.3646, 0.3978] |
| domain | poetry | candidate↔φ | Llama | `output_bigram_repeat_fraction` | -0.2769 [-0.2940, -0.2582] | -0.2837 [-0.3000, -0.2665] |
| domain | poetry | candidate↔φ | Llama | `output_self_bits_per_byte` | 0.4254 [0.4078, 0.4427] | 0.4488 [0.4271, 0.4707] |
| domain | poetry | candidate↔φ | Mixtral | `blackbox_actual_ratio` | 0.8118 [0.8013, 0.8213] | 0.8066 [0.7918, 0.8201] |
| domain | poetry | candidate↔φ | Mixtral | `prompt_bytes` | -0.0560 [-0.0765, -0.0361] | -0.0443 [-0.0664, -0.0229] |
| domain | poetry | candidate↔φ | Mixtral | `output_bytes` | -0.5681 [-0.5837, -0.5521] | -0.5448 [-0.5606, -0.5296] |
| domain | poetry | candidate↔φ | Mixtral | `prompt_words` | -0.0452 [-0.0665, -0.0238] | -0.0360 [-0.0591, -0.0134] |
| domain | poetry | candidate↔φ | Mixtral | `output_words` | -0.5595 [-0.5749, -0.5437] | -0.5347 [-0.5505, -0.5191] |
| domain | poetry | candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | 0.6299 [0.6159, 0.6433] | 0.5595 [0.5347, 0.5981] |
| domain | poetry | candidate↔φ | Mixtral | `word_type_coverage` | 0.7911 [0.7802, 0.8014] | 0.7982 [0.7862, 0.8092] |
| domain | poetry | candidate↔φ | Mixtral | `word_token_coverage` | 0.7772 [0.7656, 0.7879] | 0.7842 [0.7719, 0.7954] |
| domain | poetry | candidate↔φ | Mixtral | `word_bigram_coverage` | 0.6825 [0.6698, 0.6954] | 0.7187 [0.7038, 0.7325] |
| domain | poetry | candidate↔φ | Mixtral | `char3_coverage` | 0.7518 [0.7406, 0.7623] | 0.7698 [0.7590, 0.7800] |
| domain | poetry | candidate↔φ | Mixtral | `char5_coverage` | 0.7824 [0.7715, 0.7930] | 0.7998 [0.7893, 0.8102] |
| domain | poetry | candidate↔φ | Mixtral | `char8_coverage` | 0.7060 [0.6933, 0.7183] | 0.7386 [0.7255, 0.7512] |
| domain | poetry | candidate↔φ | Mixtral | `rouge_l_recall` | 0.8111 [0.8008, 0.8206] | 0.8136 [0.8026, 0.8237] |
| domain | poetry | candidate↔φ | Mixtral | `output_type_token_ratio` | 0.3414 [0.3246, 0.3575] | 0.3717 [0.3553, 0.3884] |
| domain | poetry | candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | -0.2643 [-0.2811, -0.2461] | -0.2703 [-0.2865, -0.2530] |
| domain | poetry | candidate↔φ | Mixtral | `output_self_bits_per_byte` | 0.4218 [0.4044, 0.4394] | 0.4429 [0.4223, 0.4637] |

## Robust convergence winner

满足两个 evaluator 的 paired Δρ CI 同方向且不跨 0，并且相应 continuous alpha_z 的 paired Δ CI 也同方向且不跨 0 的结果如下：
- `char3_coverage` / macro_within_level: **robust_BB_convergence_winner**
- `char5_coverage` / macro_within_level: **robust_BB_convergence_winner**
- `char8_coverage` / item_centered: **robust_BB_convergence_winner**
- `char8_coverage` / macro_within_level: **robust_BB_convergence_winner**
- `output_bigram_repeat_fraction` / item_centered: **robust_BB_convergence_winner**
- `output_bigram_repeat_fraction` / macro_within_level: **robust_BB_convergence_winner**
- `output_bytes` / item_centered: **robust_BB_convergence_winner**
- `output_bytes` / macro_within_level: **robust_BB_convergence_winner**
- `output_self_bits_per_byte` / item_centered: **robust_BB_convergence_winner**
- `output_self_bits_per_byte` / macro_within_level: **robust_BB_convergence_winner**
- `output_type_token_ratio` / item_centered: **robust_BB_convergence_winner**
- `output_type_token_ratio` / macro_within_level: **robust_BB_convergence_winner**
- `output_words` / item_centered: **robust_BB_convergence_winner**
- `output_words` / macro_within_level: **robust_BB_convergence_winner**
- `prompt_bytes` / item_centered: **robust_BB_convergence_winner**
- `prompt_bytes` / macro_within_level: **robust_BB_convergence_winner**
- `prompt_to_output_byte_ratio` / item_centered: **robust_BB_convergence_winner**
- `prompt_to_output_byte_ratio` / macro_within_level: **robust_BB_convergence_winner**
- `prompt_words` / item_centered: **robust_BB_convergence_winner**
- `prompt_words` / macro_within_level: **robust_BB_convergence_winner**
- `rouge_l_recall` / item_centered: **robust_heuristic_convergence_winner**
- `rouge_l_recall` / macro_within_level: **robust_heuristic_convergence_winner**
- `word_bigram_coverage` / item_centered: **robust_BB_convergence_winner**
- `word_bigram_coverage` / macro_within_level: **robust_BB_convergence_winner**
- `word_token_coverage` / item_centered: **robust_heuristic_convergence_winner**
- `word_token_coverage` / macro_within_level: **robust_BB_convergence_winner**
- `word_type_coverage` / item_centered: **robust_heuristic_convergence_winner**

## 附录

以下附录全部由 `metrics.json` 自动生成；alpha_rank 与 alpha_raw 不用于跨 feature 主排名。

# Appendix A — Per-level agreement

| Comparison | Evaluator | Candidate/heuristic | Level | Spearman ρ | pairwise_continuous_alpha_z |
|---|---|---|---|---:|---:|
| BB↔H | — | `prompt_bytes` | L1 | 0.1124 [0.0950, 0.1289] | 0.1640 [0.1509, 0.1782] |
| BB↔H | — | `prompt_bytes` | L2 | -0.0254 [-0.0557, 0.0065] | 0.0965 [0.0710, 0.1223] |
| BB↔H | — | `prompt_bytes` | L3 | -0.1051 [-0.1229, -0.0867] | -0.1186 [-0.1354, -0.1018] |
| BB↔H | — | `prompt_bytes` | L4 | -0.1647 [-0.1823, -0.1446] | -0.1504 [-0.1682, -0.1311] |
| BB↔H | — | `prompt_bytes` | L5 | 0.0288 [0.0084, 0.0492] | 0.0057 [-0.0129, 0.0256] |
| BB↔H | — | `output_bytes` | L1 | -0.3771 [-0.3994, -0.3544] | -0.3290 [-0.3506, -0.3070] |
| BB↔H | — | `output_bytes` | L2 | -0.1948 [-0.2255, -0.1618] | 0.0108 [-0.0160, 0.0380] |
| BB↔H | — | `output_bytes` | L3 | -0.8533 [-0.8600, -0.8460] | -0.7582 [-0.7641, -0.7523] |
| BB↔H | — | `output_bytes` | L4 | -0.8097 [-0.8186, -0.8003] | -0.7052 [-0.7140, -0.6965] |
| BB↔H | — | `output_bytes` | L5 | -0.9518 [-0.9536, -0.9498] | -0.7442 [-0.7530, -0.7362] |
| BB↔H | — | `prompt_words` | L1 | 0.0855 [0.0682, 0.1022] | 0.1526 [0.1390, 0.1670] |
| BB↔H | — | `prompt_words` | L2 | -0.1108 [-0.1400, -0.0797] | 0.0623 [0.0371, 0.0879] |
| BB↔H | — | `prompt_words` | L3 | -0.0854 [-0.1042, -0.0669] | -0.0949 [-0.1127, -0.0778] |
| BB↔H | — | `prompt_words` | L4 | -0.1108 [-0.1289, -0.0909] | -0.0918 [-0.1100, -0.0717] |
| BB↔H | — | `prompt_words` | L5 | 0.0857 [0.0671, 0.1045] | 0.0522 [0.0331, 0.0729] |
| BB↔H | — | `output_words` | L1 | -0.3339 [-0.3561, -0.3103] | -0.2740 [-0.2963, -0.2527] |
| BB↔H | — | `output_words` | L2 | -0.2028 [-0.2327, -0.1703] | 0.0036 [-0.0232, 0.0305] |
| BB↔H | — | `output_words` | L3 | -0.8793 [-0.8840, -0.8740] | -0.7878 [-0.7927, -0.7832] |
| BB↔H | — | `output_words` | L4 | -0.8583 [-0.8641, -0.8519] | -0.7454 [-0.7520, -0.7388] |
| BB↔H | — | `output_words` | L5 | -0.9550 [-0.9568, -0.9531] | -0.7658 [-0.7741, -0.7579] |
| BB↔H | — | `prompt_to_output_byte_ratio` | L1 | 0.7752 [0.7644, 0.7847] | 0.8246 [0.8097, 0.8384] |
| BB↔H | — | `prompt_to_output_byte_ratio` | L2 | 0.5488 [0.5278, 0.5698] | 0.4716 [0.4334, 0.5095] |
| BB↔H | — | `prompt_to_output_byte_ratio` | L3 | 0.9143 [0.9090, 0.9193] | 0.9457 [0.9430, 0.9483] |
| BB↔H | — | `prompt_to_output_byte_ratio` | L4 | 0.8550 [0.8464, 0.8638] | 0.8645 [0.8552, 0.8735] |
| BB↔H | — | `prompt_to_output_byte_ratio` | L5 | 0.9682 [0.9666, 0.9694] | 0.9613 [0.9571, 0.9652] |
| BB↔H | — | `word_type_coverage` | L1 | 0.9195 [0.9149, 0.9240] | 0.9534 [0.9484, 0.9569] |
| BB↔H | — | `word_type_coverage` | L2 | 0.8734 [0.8658, 0.8807] | 0.8675 [0.8593, 0.8753] |
| BB↔H | — | `word_type_coverage` | L3 | 0.9692 [0.9675, 0.9707] | 0.9764 [0.9752, 0.9776] |
| BB↔H | — | `word_type_coverage` | L4 | 0.9548 [0.9528, 0.9567] | 0.9546 [0.9527, 0.9565] |
| BB↔H | — | `word_type_coverage` | L5 | 0.9078 [0.9038, 0.9116] | 0.9099 [0.9046, 0.9155] |
| BB↔H | — | `word_token_coverage` | L1 | 0.9242 [0.9197, 0.9285] | 0.9358 [0.9307, 0.9396] |
| BB↔H | — | `word_token_coverage` | L2 | 0.8373 [0.8257, 0.8486] | 0.8267 [0.8136, 0.8391] |
| BB↔H | — | `word_token_coverage` | L3 | 0.9568 [0.9546, 0.9588] | 0.9730 [0.9717, 0.9741] |
| BB↔H | — | `word_token_coverage` | L4 | 0.9578 [0.9559, 0.9596] | 0.9562 [0.9544, 0.9582] |
| BB↔H | — | `word_token_coverage` | L5 | 0.9537 [0.9517, 0.9556] | 0.9302 [0.9251, 0.9360] |
| BB↔H | — | `word_bigram_coverage` | L1 | 0.9298 [0.9253, 0.9342] | 0.9480 [0.9422, 0.9525] |
| BB↔H | — | `word_bigram_coverage` | L2 | 0.8814 [0.8723, 0.8908] | 0.8688 [0.8583, 0.8795] |
| BB↔H | — | `word_bigram_coverage` | L3 | 0.9415 [0.9385, 0.9444] | 0.9585 [0.9564, 0.9605] |
| BB↔H | — | `word_bigram_coverage` | L4 | 0.8820 [0.8767, 0.8873] | 0.8887 [0.8836, 0.8935] |
| BB↔H | — | `word_bigram_coverage` | L5 | 0.2516 [0.2296, 0.2742] | 0.4877 [0.4555, 0.5186] |
| BB↔H | — | `char3_coverage` | L1 | 0.9492 [0.9453, 0.9525] | 0.9367 [0.9319, 0.9402] |
| BB↔H | — | `char3_coverage` | L2 | 0.8015 [0.7866, 0.8152] | 0.7875 [0.7717, 0.8021] |
| BB↔H | — | `char3_coverage` | L3 | 0.9458 [0.9427, 0.9487] | 0.9693 [0.9679, 0.9707] |
| BB↔H | — | `char3_coverage` | L4 | 0.9201 [0.9161, 0.9240] | 0.9331 [0.9298, 0.9365] |
| BB↔H | — | `char3_coverage` | L5 | 0.9589 [0.9572, 0.9606] | 0.9425 [0.9367, 0.9483] |
| BB↔H | — | `char5_coverage` | L1 | 0.9640 [0.9608, 0.9667] | 0.9716 [0.9671, 0.9745] |
| BB↔H | — | `char5_coverage` | L2 | 0.8994 [0.8902, 0.9076] | 0.8946 [0.8848, 0.9034] |
| BB↔H | — | `char5_coverage` | L3 | 0.9791 [0.9779, 0.9803] | 0.9864 [0.9857, 0.9871] |
| BB↔H | — | `char5_coverage` | L4 | 0.9767 [0.9756, 0.9777] | 0.9755 [0.9744, 0.9766] |
| BB↔H | — | `char5_coverage` | L5 | 0.7657 [0.7558, 0.7750] | 0.7984 [0.7862, 0.8096] |
| BB↔H | — | `char8_coverage` | L1 | 0.9643 [0.9612, 0.9669] | 0.9727 [0.9680, 0.9757] |
| BB↔H | — | `char8_coverage` | L2 | 0.9251 [0.9187, 0.9312] | 0.9157 [0.9082, 0.9227] |
| BB↔H | — | `char8_coverage` | L3 | 0.9665 [0.9647, 0.9681] | 0.9761 [0.9750, 0.9772] |
| BB↔H | — | `char8_coverage` | L4 | 0.9344 [0.9312, 0.9376] | 0.9349 [0.9318, 0.9378] |
| BB↔H | — | `char8_coverage` | L5 | 0.3510 [0.3306, 0.3702] | 0.5356 [0.5098, 0.5595] |
| BB↔H | — | `rouge_l_recall` | L1 | 0.9310 [0.9262, 0.9353] | 0.9513 [0.9459, 0.9551] |
| BB↔H | — | `rouge_l_recall` | L2 | 0.8562 [0.8471, 0.8656] | 0.8521 [0.8417, 0.8626] |
| BB↔H | — | `rouge_l_recall` | L3 | 0.9556 [0.9532, 0.9577] | 0.9674 [0.9657, 0.9690] |
| BB↔H | — | `rouge_l_recall` | L4 | 0.9532 [0.9511, 0.9552] | 0.9437 [0.9415, 0.9460] |
| BB↔H | — | `rouge_l_recall` | L5 | 0.9434 [0.9410, 0.9456] | 0.8955 [0.8859, 0.9064] |
| BB↔H | — | `output_type_token_ratio` | L1 | 0.0839 [0.0618, 0.1066] | 0.1428 [0.1222, 0.1636] |
| BB↔H | — | `output_type_token_ratio` | L2 | -0.2702 [-0.3031, -0.2390] | -0.2073 [-0.2449, -0.1689] |
| BB↔H | — | `output_type_token_ratio` | L3 | 0.4476 [0.4289, 0.4669] | 0.4339 [0.4143, 0.4537] |
| BB↔H | — | `output_type_token_ratio` | L4 | 0.4930 [0.4779, 0.5084] | 0.5062 [0.4917, 0.5210] |
| BB↔H | — | `output_type_token_ratio` | L5 | 0.7585 [0.7503, 0.7670] | 0.7631 [0.7550, 0.7715] |
| BB↔H | — | `output_bigram_repeat_fraction` | L1 | -0.1289 [-0.1509, -0.1080] | -0.1898 [-0.2129, -0.1686] |
| BB↔H | — | `output_bigram_repeat_fraction` | L2 | 0.3546 [0.3256, 0.3839] | 0.3130 [0.2866, 0.3382] |
| BB↔H | — | `output_bigram_repeat_fraction` | L3 | -0.2187 [-0.2407, -0.1977] | -0.1423 [-0.1640, -0.1209] |
| BB↔H | — | `output_bigram_repeat_fraction` | L4 | -0.3183 [-0.3375, -0.3007] | -0.3061 [-0.3244, -0.2881] |
| BB↔H | — | `output_bigram_repeat_fraction` | L5 | -0.5563 [-0.5699, -0.5421] | -0.4779 [-0.4934, -0.4620] |
| BB↔H | — | `output_self_bits_per_byte` | L1 | 0.1612 [0.1386, 0.1839] | 0.2240 [0.2042, 0.2446] |
| BB↔H | — | `output_self_bits_per_byte` | L2 | -0.1758 [-0.2110, -0.1424] | -0.0086 [-0.0558, 0.0391] |
| BB↔H | — | `output_self_bits_per_byte` | L3 | 0.5075 [0.4897, 0.5269] | 0.5284 [0.5105, 0.5468] |
| BB↔H | — | `output_self_bits_per_byte` | L4 | 0.4263 [0.4086, 0.4436] | 0.4545 [0.4375, 0.4721] |
| BB↔H | — | `output_self_bits_per_byte` | L5 | 0.8752 [0.8701, 0.8801] | 0.9143 [0.9098, 0.9185] |
| candidate↔φ | Llama | `blackbox_actual_ratio` | L1 | 0.8771 [0.8705, 0.8836] | 0.9165 [0.9100, 0.9213] |
| candidate↔φ | Llama | `blackbox_actual_ratio` | L2 | 0.6201 [0.6022, 0.6378] | 0.6178 [0.6010, 0.6347] |
| candidate↔φ | Llama | `blackbox_actual_ratio` | L3 | 0.8504 [0.8445, 0.8555] | 0.8878 [0.8830, 0.8921] |
| candidate↔φ | Llama | `blackbox_actual_ratio` | L4 | 0.8437 [0.8371, 0.8503] | 0.8352 [0.8284, 0.8422] |
| candidate↔φ | Llama | `blackbox_actual_ratio` | L5 | 0.6598 [0.6484, 0.6710] | 0.7021 [0.6862, 0.7176] |
| candidate↔φ | Llama | `prompt_bytes` | L1 | 0.2374 [0.2205, 0.2547] | 0.2460 [0.2334, 0.2584] |
| candidate↔φ | Llama | `prompt_bytes` | L2 | -0.1042 [-0.1248, -0.0833] | -0.0570 [-0.0751, -0.0380] |
| candidate↔φ | Llama | `prompt_bytes` | L3 | 0.0602 [0.0416, 0.0796] | 0.0250 [0.0054, 0.0432] |
| candidate↔φ | Llama | `prompt_bytes` | L4 | 0.0079 [-0.0101, 0.0270] | 0.0237 [0.0052, 0.0427] |
| candidate↔φ | Llama | `prompt_bytes` | L5 | 0.2318 [0.2026, 0.2606] | 0.2640 [0.2372, 0.2903] |
| candidate↔φ | Llama | `output_bytes` | L1 | -0.2361 [-0.2607, -0.2116] | -0.2551 [-0.2792, -0.2312] |
| candidate↔φ | Llama | `output_bytes` | L2 | -0.1825 [-0.2037, -0.1601] | -0.0785 [-0.0976, -0.0582] |
| candidate↔φ | Llama | `output_bytes` | L3 | -0.6924 [-0.7021, -0.6826] | -0.6519 [-0.6594, -0.6441] |
| candidate↔φ | Llama | `output_bytes` | L4 | -0.6051 [-0.6174, -0.5927] | -0.5467 [-0.5571, -0.5359] |
| candidate↔φ | Llama | `output_bytes` | L5 | -0.5967 [-0.6116, -0.5819] | -0.5587 [-0.5702, -0.5473] |
| candidate↔φ | Llama | `prompt_words` | L1 | 0.2473 [0.2308, 0.2641] | 0.2467 [0.2342, 0.2593] |
| candidate↔φ | Llama | `prompt_words` | L2 | -0.1152 [-0.1358, -0.0941] | -0.0616 [-0.0800, -0.0427] |
| candidate↔φ | Llama | `prompt_words` | L3 | 0.1033 [0.0838, 0.1220] | 0.0683 [0.0485, 0.0871] |
| candidate↔φ | Llama | `prompt_words` | L4 | 0.0537 [0.0357, 0.0733] | 0.0737 [0.0550, 0.0931] |
| candidate↔φ | Llama | `prompt_words` | L5 | 0.3492 [0.3220, 0.3745] | 0.3288 [0.3051, 0.3516] |
| candidate↔φ | Llama | `output_words` | L1 | -0.1699 [-0.1941, -0.1455] | -0.1816 [-0.2060, -0.1587] |
| candidate↔φ | Llama | `output_words` | L2 | -0.1457 [-0.1671, -0.1227] | -0.0497 [-0.0692, -0.0300] |
| candidate↔φ | Llama | `output_words` | L3 | -0.6987 [-0.7077, -0.6891] | -0.6711 [-0.6781, -0.6635] |
| candidate↔φ | Llama | `output_words` | L4 | -0.6512 [-0.6623, -0.6399] | -0.5862 [-0.5955, -0.5766] |
| candidate↔φ | Llama | `output_words` | L5 | -0.6178 [-0.6316, -0.6034] | -0.5875 [-0.5985, -0.5767] |
| candidate↔φ | Llama | `prompt_to_output_byte_ratio` | L1 | 0.6289 [0.6160, 0.6414] | 0.7905 [0.7717, 0.8080] |
| candidate↔φ | Llama | `prompt_to_output_byte_ratio` | L2 | 0.2188 [0.1939, 0.2424] | 0.1706 [0.1241, 0.2169] |
| candidate↔φ | Llama | `prompt_to_output_byte_ratio` | L3 | 0.8136 [0.8067, 0.8200] | 0.8564 [0.8503, 0.8617] |
| candidate↔φ | Llama | `prompt_to_output_byte_ratio` | L4 | 0.6865 [0.6743, 0.6982] | 0.6927 [0.6786, 0.7061] |
| candidate↔φ | Llama | `prompt_to_output_byte_ratio` | L5 | 0.6482 [0.6358, 0.6601] | 0.6630 [0.6372, 0.6863] |
| candidate↔φ | Llama | `word_type_coverage` | L1 | 0.9039 [0.8977, 0.9099] | 0.9382 [0.9334, 0.9423] |
| candidate↔φ | Llama | `word_type_coverage` | L2 | 0.5332 [0.5162, 0.5497] | 0.5583 [0.5426, 0.5735] |
| candidate↔φ | Llama | `word_type_coverage` | L3 | 0.8572 [0.8513, 0.8625] | 0.8892 [0.8843, 0.8936] |
| candidate↔φ | Llama | `word_type_coverage` | L4 | 0.8603 [0.8544, 0.8660] | 0.8522 [0.8459, 0.8585] |
| candidate↔φ | Llama | `word_type_coverage` | L5 | 0.7013 [0.6903, 0.7118] | 0.6653 [0.6486, 0.6837] |
| candidate↔φ | Llama | `word_token_coverage` | L1 | 0.8884 [0.8815, 0.8948] | 0.9262 [0.9211, 0.9302] |
| candidate↔φ | Llama | `word_token_coverage` | L2 | 0.5031 [0.4851, 0.5214] | 0.5377 [0.5210, 0.5543] |
| candidate↔φ | Llama | `word_token_coverage` | L3 | 0.8531 [0.8473, 0.8580] | 0.8880 [0.8833, 0.8923] |
| candidate↔φ | Llama | `word_token_coverage` | L4 | 0.8203 [0.8126, 0.8279] | 0.8157 [0.8074, 0.8240] |
| candidate↔φ | Llama | `word_token_coverage` | L5 | 0.6855 [0.6744, 0.6966] | 0.6515 [0.6310, 0.6742] |
| candidate↔φ | Llama | `word_bigram_coverage` | L1 | 0.8990 [0.8925, 0.9051] | 0.9042 [0.8984, 0.9095] |
| candidate↔φ | Llama | `word_bigram_coverage` | L2 | 0.5728 [0.5565, 0.5899] | 0.5818 [0.5668, 0.5973] |
| candidate↔φ | Llama | `word_bigram_coverage` | L3 | 0.8403 [0.8337, 0.8464] | 0.8791 [0.8742, 0.8837] |
| candidate↔φ | Llama | `word_bigram_coverage` | L4 | 0.8083 [0.8006, 0.8160] | 0.8068 [0.7989, 0.8149] |
| candidate↔φ | Llama | `word_bigram_coverage` | L5 | 0.1788 [0.1543, 0.2039] | 0.2974 [0.2711, 0.3260] |
| candidate↔φ | Llama | `char3_coverage` | L1 | 0.8840 [0.8782, 0.8897] | 0.9241 [0.9205, 0.9273] |
| candidate↔φ | Llama | `char3_coverage` | L2 | 0.4495 [0.4301, 0.4683] | 0.4952 [0.4765, 0.5132] |
| candidate↔φ | Llama | `char3_coverage` | L3 | 0.8418 [0.8358, 0.8474] | 0.8811 [0.8760, 0.8857] |
| candidate↔φ | Llama | `char3_coverage` | L4 | 0.7586 [0.7493, 0.7677] | 0.7720 [0.7620, 0.7815] |
| candidate↔φ | Llama | `char3_coverage` | L5 | 0.6567 [0.6450, 0.6684] | 0.6547 [0.6363, 0.6735] |
| candidate↔φ | Llama | `char5_coverage` | L1 | 0.8907 [0.8849, 0.8963] | 0.9268 [0.9231, 0.9302] |
| candidate↔φ | Llama | `char5_coverage` | L2 | 0.5313 [0.5132, 0.5496] | 0.5434 [0.5265, 0.5597] |
| candidate↔φ | Llama | `char5_coverage` | L3 | 0.8628 [0.8573, 0.8678] | 0.8945 [0.8901, 0.8985] |
| candidate↔φ | Llama | `char5_coverage` | L4 | 0.8462 [0.8397, 0.8527] | 0.8422 [0.8352, 0.8491] |
| candidate↔φ | Llama | `char5_coverage` | L5 | 0.5769 [0.5616, 0.5919] | 0.5524 [0.5305, 0.5744] |
| candidate↔φ | Llama | `char8_coverage` | L1 | 0.8824 [0.8762, 0.8883] | 0.9007 [0.8960, 0.9051] |
| candidate↔φ | Llama | `char8_coverage` | L2 | 0.5620 [0.5439, 0.5802] | 0.5661 [0.5492, 0.5821] |
| candidate↔φ | Llama | `char8_coverage` | L3 | 0.8448 [0.8386, 0.8509] | 0.8832 [0.8782, 0.8877] |
| candidate↔φ | Llama | `char8_coverage` | L4 | 0.8385 [0.8321, 0.8448] | 0.8329 [0.8265, 0.8397] |
| candidate↔φ | Llama | `char8_coverage` | L5 | 0.3426 [0.3178, 0.3659] | 0.4179 [0.3916, 0.4428] |
| candidate↔φ | Llama | `rouge_l_recall` | L1 | 0.9119 [0.9060, 0.9177] | 0.9436 [0.9394, 0.9472] |
| candidate↔φ | Llama | `rouge_l_recall` | L2 | 0.6845 [0.6712, 0.6982] | 0.6942 [0.6823, 0.7063] |
| candidate↔φ | Llama | `rouge_l_recall` | L3 | 0.8797 [0.8746, 0.8842] | 0.9036 [0.8996, 0.9071] |
| candidate↔φ | Llama | `rouge_l_recall` | L4 | 0.8580 [0.8518, 0.8642] | 0.8473 [0.8406, 0.8539] |
| candidate↔φ | Llama | `rouge_l_recall` | L5 | 0.6669 [0.6554, 0.6785] | 0.6068 [0.5812, 0.6347] |
| candidate↔φ | Llama | `output_type_token_ratio` | L1 | 0.1709 [0.1506, 0.1915] | 0.2373 [0.2196, 0.2549] |
| candidate↔φ | Llama | `output_type_token_ratio` | L2 | -0.1078 [-0.1350, -0.0829] | -0.0950 [-0.1214, -0.0702] |
| candidate↔φ | Llama | `output_type_token_ratio` | L3 | 0.3244 [0.3037, 0.3456] | 0.3338 [0.3125, 0.3554] |
| candidate↔φ | Llama | `output_type_token_ratio` | L4 | 0.2882 [0.2682, 0.3085] | 0.3090 [0.2891, 0.3287] |
| candidate↔φ | Llama | `output_type_token_ratio` | L5 | 0.5685 [0.5544, 0.5826] | 0.6202 [0.6070, 0.6328] |
| candidate↔φ | Llama | `output_bigram_repeat_fraction` | L1 | -0.2605 [-0.2789, -0.2418] | -0.3449 [-0.3639, -0.3266] |
| candidate↔φ | Llama | `output_bigram_repeat_fraction` | L2 | 0.1520 [0.1272, 0.1769] | 0.1567 [0.1359, 0.1780] |
| candidate↔φ | Llama | `output_bigram_repeat_fraction` | L3 | -0.1597 [-0.1828, -0.1376] | -0.0909 [-0.1147, -0.0677] |
| candidate↔φ | Llama | `output_bigram_repeat_fraction` | L4 | -0.1436 [-0.1663, -0.1226] | -0.1460 [-0.1673, -0.1242] |
| candidate↔φ | Llama | `output_bigram_repeat_fraction` | L5 | -0.4486 [-0.4661, -0.4300] | -0.4312 [-0.4469, -0.4160] |
| candidate↔φ | Llama | `output_self_bits_per_byte` | L1 | 0.2474 [0.2275, 0.2662] | 0.2945 [0.2760, 0.3133] |
| candidate↔φ | Llama | `output_self_bits_per_byte` | L2 | -0.0040 [-0.0316, 0.0218] | 0.0437 [0.0152, 0.0722] |
| candidate↔φ | Llama | `output_self_bits_per_byte` | L3 | 0.3927 [0.3731, 0.4133] | 0.4261 [0.4053, 0.4465] |
| candidate↔φ | Llama | `output_self_bits_per_byte` | L4 | 0.2249 [0.2042, 0.2456] | 0.2491 [0.2284, 0.2692] |
| candidate↔φ | Llama | `output_self_bits_per_byte` | L5 | 0.5468 [0.5295, 0.5638] | 0.6155 [0.5977, 0.6335] |
| candidate↔φ | Mixtral | `blackbox_actual_ratio` | L1 | 0.8692 [0.8613, 0.8767] | 0.9043 [0.8962, 0.9117] |
| candidate↔φ | Mixtral | `blackbox_actual_ratio` | L2 | 0.4961 [0.4745, 0.5190] | 0.5097 [0.4883, 0.5306] |
| candidate↔φ | Mixtral | `blackbox_actual_ratio` | L3 | 0.8711 [0.8656, 0.8762] | 0.8986 [0.8942, 0.9029] |
| candidate↔φ | Mixtral | `blackbox_actual_ratio` | L4 | 0.8495 [0.8428, 0.8561] | 0.8396 [0.8323, 0.8464] |
| candidate↔φ | Mixtral | `blackbox_actual_ratio` | L5 | 0.7156 [0.7055, 0.7261] | 0.7561 [0.7440, 0.7677] |
| candidate↔φ | Mixtral | `prompt_bytes` | L1 | 0.2215 [0.2044, 0.2385] | 0.2173 [0.2044, 0.2304] |
| candidate↔φ | Mixtral | `prompt_bytes` | L2 | -0.0935 [-0.1153, -0.0727] | -0.0824 [-0.1029, -0.0617] |
| candidate↔φ | Mixtral | `prompt_bytes` | L3 | -0.0265 [-0.0445, -0.0081] | -0.0516 [-0.0701, -0.0345] |
| candidate↔φ | Mixtral | `prompt_bytes` | L4 | -0.0454 [-0.0628, -0.0269] | -0.0246 [-0.0419, -0.0059] |
| candidate↔φ | Mixtral | `prompt_bytes` | L5 | 0.1642 [0.1398, 0.1880] | 0.1428 [0.1193, 0.1671] |
| candidate↔φ | Mixtral | `output_bytes` | L1 | -0.2541 [-0.2779, -0.2307] | -0.2664 [-0.2905, -0.2431] |
| candidate↔φ | Mixtral | `output_bytes` | L2 | -0.1409 [-0.1635, -0.1198] | -0.0870 [-0.1079, -0.0655] |
| candidate↔φ | Mixtral | `output_bytes` | L3 | -0.7446 [-0.7533, -0.7360] | -0.6937 [-0.7005, -0.6868] |
| candidate↔φ | Mixtral | `output_bytes` | L4 | -0.6198 [-0.6320, -0.6072] | -0.5613 [-0.5718, -0.5501] |
| candidate↔φ | Mixtral | `output_bytes` | L5 | -0.6547 [-0.6685, -0.6413] | -0.5909 [-0.6014, -0.5805] |
| candidate↔φ | Mixtral | `prompt_words` | L1 | 0.2317 [0.2151, 0.2482] | 0.2187 [0.2061, 0.2319] |
| candidate↔φ | Mixtral | `prompt_words` | L2 | -0.0776 [-0.1003, -0.0568] | -0.0786 [-0.0991, -0.0578] |
| candidate↔φ | Mixtral | `prompt_words` | L3 | 0.0133 [-0.0054, 0.0313] | -0.0115 [-0.0305, 0.0069] |
| candidate↔φ | Mixtral | `prompt_words` | L4 | -0.0066 [-0.0243, 0.0122] | 0.0165 [-0.0013, 0.0352] |
| candidate↔φ | Mixtral | `prompt_words` | L5 | 0.2540 [0.2314, 0.2763] | 0.1901 [0.1678, 0.2127] |
| candidate↔φ | Mixtral | `output_words` | L1 | -0.1862 [-0.2089, -0.1629] | -0.1932 [-0.2166, -0.1705] |
| candidate↔φ | Mixtral | `output_words` | L2 | -0.0898 [-0.1129, -0.0680] | -0.0484 [-0.0696, -0.0269] |
| candidate↔φ | Mixtral | `output_words` | L3 | -0.7491 [-0.7575, -0.7407] | -0.7114 [-0.7177, -0.7049] |
| candidate↔φ | Mixtral | `output_words` | L4 | -0.6649 [-0.6756, -0.6535] | -0.5991 [-0.6083, -0.5890] |
| candidate↔φ | Mixtral | `output_words` | L5 | -0.6617 [-0.6747, -0.6490] | -0.6097 [-0.6200, -0.5996] |
| candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | L1 | 0.6339 [0.6220, 0.6456] | 0.7676 [0.7488, 0.7855] |
| candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | L2 | 0.1127 [0.0887, 0.1367] | 0.0850 [0.0471, 0.1232] |
| candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | L3 | 0.8297 [0.8228, 0.8360] | 0.8713 [0.8659, 0.8764] |
| candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | L4 | 0.6815 [0.6688, 0.6933] | 0.6862 [0.6724, 0.6990] |
| candidate↔φ | Mixtral | `prompt_to_output_byte_ratio` | L5 | 0.6926 [0.6810, 0.7040] | 0.7003 [0.6825, 0.7171] |
| candidate↔φ | Mixtral | `word_type_coverage` | L1 | 0.8941 [0.8858, 0.9019] | 0.9219 [0.9138, 0.9296] |
| candidate↔φ | Mixtral | `word_type_coverage` | L2 | 0.4446 [0.4249, 0.4650] | 0.4783 [0.4589, 0.4974] |
| candidate↔φ | Mixtral | `word_type_coverage` | L3 | 0.8633 [0.8574, 0.8689] | 0.8900 [0.8849, 0.8946] |
| candidate↔φ | Mixtral | `word_type_coverage` | L4 | 0.8526 [0.8460, 0.8586] | 0.8426 [0.8355, 0.8495] |
| candidate↔φ | Mixtral | `word_type_coverage` | L5 | 0.7468 [0.7371, 0.7563] | 0.7623 [0.7516, 0.7732] |
| candidate↔φ | Mixtral | `word_token_coverage` | L1 | 0.8732 [0.8645, 0.8815] | 0.9027 [0.8950, 0.9097] |
| candidate↔φ | Mixtral | `word_token_coverage` | L2 | 0.4066 [0.3854, 0.4275] | 0.4452 [0.4249, 0.4654] |
| candidate↔φ | Mixtral | `word_token_coverage` | L3 | 0.8597 [0.8539, 0.8652] | 0.8935 [0.8889, 0.8978] |
| candidate↔φ | Mixtral | `word_token_coverage` | L4 | 0.8100 [0.8017, 0.8179] | 0.8017 [0.7926, 0.8103] |
| candidate↔φ | Mixtral | `word_token_coverage` | L5 | 0.7259 [0.7159, 0.7355] | 0.7437 [0.7329, 0.7542] |
| candidate↔φ | Mixtral | `word_bigram_coverage` | L1 | 0.8817 [0.8728, 0.8898] | 0.8886 [0.8783, 0.8980] |
| candidate↔φ | Mixtral | `word_bigram_coverage` | L2 | 0.4670 [0.4461, 0.4871] | 0.4986 [0.4795, 0.5174] |
| candidate↔φ | Mixtral | `word_bigram_coverage` | L3 | 0.8459 [0.8392, 0.8524] | 0.8792 [0.8739, 0.8841] |
| candidate↔φ | Mixtral | `word_bigram_coverage` | L4 | 0.8007 [0.7925, 0.8090] | 0.7939 [0.7851, 0.8026] |
| candidate↔φ | Mixtral | `word_bigram_coverage` | L5 | 0.2524 [0.2308, 0.2755] | 0.4294 [0.4030, 0.4551] |
| candidate↔φ | Mixtral | `char3_coverage` | L1 | 0.8679 [0.8596, 0.8757] | 0.8990 [0.8915, 0.9055] |
| candidate↔φ | Mixtral | `char3_coverage` | L2 | 0.3550 [0.3334, 0.3767] | 0.3998 [0.3785, 0.4217] |
| candidate↔φ | Mixtral | `char3_coverage` | L3 | 0.8546 [0.8485, 0.8600] | 0.8918 [0.8872, 0.8963] |
| candidate↔φ | Mixtral | `char3_coverage` | L4 | 0.7534 [0.7436, 0.7626] | 0.7637 [0.7534, 0.7733] |
| candidate↔φ | Mixtral | `char3_coverage` | L5 | 0.7086 [0.6980, 0.7186] | 0.7418 [0.7291, 0.7529] |
| candidate↔φ | Mixtral | `char5_coverage` | L1 | 0.8736 [0.8654, 0.8812] | 0.9058 [0.8980, 0.9130] |
| candidate↔φ | Mixtral | `char5_coverage` | L2 | 0.4164 [0.3943, 0.4395] | 0.4372 [0.4161, 0.4586] |
| candidate↔φ | Mixtral | `char5_coverage` | L3 | 0.8750 [0.8696, 0.8800] | 0.9020 [0.8977, 0.9060] |
| candidate↔φ | Mixtral | `char5_coverage` | L4 | 0.8434 [0.8361, 0.8505] | 0.8348 [0.8275, 0.8424] |
| candidate↔φ | Mixtral | `char5_coverage` | L5 | 0.6336 [0.6202, 0.6473] | 0.6807 [0.6664, 0.6947] |
| candidate↔φ | Mixtral | `char8_coverage` | L1 | 0.8631 [0.8547, 0.8712] | 0.8826 [0.8733, 0.8907] |
| candidate↔φ | Mixtral | `char8_coverage` | L2 | 0.4388 [0.4161, 0.4620] | 0.4633 [0.4425, 0.4842] |
| candidate↔φ | Mixtral | `char8_coverage` | L3 | 0.8565 [0.8502, 0.8626] | 0.8879 [0.8831, 0.8925] |
| candidate↔φ | Mixtral | `char8_coverage` | L4 | 0.8368 [0.8299, 0.8436] | 0.8269 [0.8197, 0.8342] |
| candidate↔φ | Mixtral | `char8_coverage` | L5 | 0.3772 [0.3544, 0.3993] | 0.5047 [0.4817, 0.5262] |
| candidate↔φ | Mixtral | `rouge_l_recall` | L1 | 0.8960 [0.8880, 0.9036] | 0.9243 [0.9162, 0.9316] |
| candidate↔φ | Mixtral | `rouge_l_recall` | L2 | 0.5922 [0.5757, 0.6085] | 0.6168 [0.6015, 0.6322] |
| candidate↔φ | Mixtral | `rouge_l_recall` | L3 | 0.8884 [0.8834, 0.8931] | 0.9089 [0.9048, 0.9128] |
| candidate↔φ | Mixtral | `rouge_l_recall` | L4 | 0.8477 [0.8407, 0.8543] | 0.8315 [0.8235, 0.8391] |
| candidate↔φ | Mixtral | `rouge_l_recall` | L5 | 0.7088 [0.6981, 0.7193] | 0.6998 [0.6846, 0.7149] |
| candidate↔φ | Mixtral | `output_type_token_ratio` | L1 | 0.1629 [0.1420, 0.1839] | 0.2180 [0.1991, 0.2365] |
| candidate↔φ | Mixtral | `output_type_token_ratio` | L2 | -0.0542 [-0.0799, -0.0292] | -0.0604 [-0.0858, -0.0352] |
| candidate↔φ | Mixtral | `output_type_token_ratio` | L3 | 0.3473 [0.3272, 0.3676] | 0.3510 [0.3302, 0.3725] |
| candidate↔φ | Mixtral | `output_type_token_ratio` | L4 | 0.2931 [0.2737, 0.3117] | 0.3135 [0.2942, 0.3319] |
| candidate↔φ | Mixtral | `output_type_token_ratio` | L5 | 0.5515 [0.5386, 0.5648] | 0.5969 [0.5839, 0.6100] |
| candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | L1 | -0.2520 [-0.2716, -0.2326] | -0.3170 [-0.3364, -0.2978] |
| candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | L2 | 0.0665 [0.0412, 0.0910] | 0.1046 [0.0827, 0.1270] |
| candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | L3 | -0.1786 [-0.2001, -0.1573] | -0.0994 [-0.1224, -0.0770] |
| candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | L4 | -0.1525 [-0.1731, -0.1323] | -0.1523 [-0.1727, -0.1316] |
| candidate↔φ | Mixtral | `output_bigram_repeat_fraction` | L5 | -0.4240 [-0.4409, -0.4057] | -0.3897 [-0.4063, -0.3728] |
| candidate↔φ | Mixtral | `output_self_bits_per_byte` | L1 | 0.2409 [0.2212, 0.2604] | 0.2754 [0.2557, 0.2943] |
| candidate↔φ | Mixtral | `output_self_bits_per_byte` | L2 | 0.0483 [0.0229, 0.0731] | 0.0561 [0.0296, 0.0832] |
| candidate↔φ | Mixtral | `output_self_bits_per_byte` | L3 | 0.4155 [0.3960, 0.4358] | 0.4408 [0.4209, 0.4605] |
| candidate↔φ | Mixtral | `output_self_bits_per_byte` | L4 | 0.2302 [0.2102, 0.2499] | 0.2520 [0.2320, 0.2712] |
| candidate↔φ | Mixtral | `output_self_bits_per_byte` | L5 | 0.5951 [0.5801, 0.6105] | 0.6699 [0.6545, 0.6849] |

## Joint-reference per-level auxiliary

| Candidate | Level | Mean reference Spearman ρ | joint_reference_continuous_alpha_z |
|---|---|---:|---:|
| `blackbox_actual_ratio` | L1 | 0.8731 [0.8662, 0.8799] | 0.9319 [0.9267, 0.9365] |
| `blackbox_actual_ratio` | L2 | 0.5581 [0.5387, 0.5779] | 0.6863 [0.6738, 0.6987] |
| `blackbox_actual_ratio` | L3 | 0.8607 [0.8554, 0.8656] | 0.9190 [0.9158, 0.9220] |
| `blackbox_actual_ratio` | L4 | 0.8466 [0.8400, 0.8529] | 0.8744 [0.8696, 0.8792] |
| `blackbox_actual_ratio` | L5 | 0.6877 [0.6782, 0.6973] | 0.7468 [0.7369, 0.7568] |
| `prompt_bytes` | L1 | 0.2294 [0.2125, 0.2463] | 0.4794 [0.4707, 0.4881] |
| `prompt_bytes` | L2 | -0.0989 [-0.1192, -0.0794] | 0.2640 [0.2516, 0.2771] |
| `prompt_bytes` | L3 | 0.0168 [-0.0019, 0.0355] | 0.3147 [0.3020, 0.3264] |
| `prompt_bytes` | L4 | -0.0188 [-0.0362, -0.0003] | 0.3159 [0.3043, 0.3284] |
| `prompt_bytes` | L5 | 0.1980 [0.1723, 0.2239] | 0.3964 [0.3797, 0.4135] |
| `output_bytes` | L1 | -0.2451 [-0.2687, -0.2213] | 0.1511 [0.1351, 0.1666] |
| `output_bytes` | L2 | -0.1617 [-0.1828, -0.1401] | 0.2553 [0.2424, 0.2689] |
| `output_bytes` | L3 | -0.7185 [-0.7275, -0.7093] | -0.1250 [-0.1296, -0.1203] |
| `output_bytes` | L4 | -0.6124 [-0.6246, -0.5998] | -0.0532 [-0.0598, -0.0462] |
| `output_bytes` | L5 | -0.6257 [-0.6391, -0.6127] | -0.1224 [-0.1294, -0.1155] |
| `prompt_words` | L1 | 0.2395 [0.2231, 0.2560] | 0.4801 [0.4713, 0.4888] |
| `prompt_words` | L2 | -0.0964 [-0.1169, -0.0763] | 0.2637 [0.2512, 0.2769] |
| `prompt_words` | L3 | 0.0583 [0.0392, 0.0764] | 0.3425 [0.3294, 0.3548] |
| `prompt_words` | L4 | 0.0236 [0.0064, 0.0422] | 0.3462 [0.3339, 0.3588] |
| `prompt_words` | L5 | 0.3016 [0.2787, 0.3247] | 0.4337 [0.4186, 0.4487] |
| `output_words` | L1 | -0.1780 [-0.2016, -0.1543] | 0.2000 [0.1841, 0.2151] |
| `output_words` | L2 | -0.1178 [-0.1386, -0.0955] | 0.2778 [0.2649, 0.2913] |
| `output_words` | L3 | -0.7239 [-0.7324, -0.7151] | -0.1373 [-0.1415, -0.1328] |
| `output_words` | L4 | -0.6581 [-0.6683, -0.6466] | -0.0790 [-0.0850, -0.0725] |
| `output_words` | L5 | -0.6397 [-0.6524, -0.6275] | -0.1383 [-0.1450, -0.1318] |
| `prompt_to_output_byte_ratio` | L1 | 0.6314 [0.6194, 0.6435] | 0.8444 [0.8315, 0.8564] |
| `prompt_to_output_byte_ratio` | L2 | 0.1658 [0.1412, 0.1887] | 0.3957 [0.3679, 0.4231] |
| `prompt_to_output_byte_ratio` | L3 | 0.8216 [0.8149, 0.8280] | 0.8995 [0.8957, 0.9031] |
| `prompt_to_output_byte_ratio` | L4 | 0.6840 [0.6721, 0.6955] | 0.7758 [0.7662, 0.7846] |
| `prompt_to_output_byte_ratio` | L5 | 0.6704 [0.6598, 0.6813] | 0.7152 [0.7001, 0.7288] |
| `word_type_coverage` | L1 | 0.8990 [0.8923, 0.9053] | 0.9450 [0.9403, 0.9495] |
| `word_type_coverage` | L2 | 0.4889 [0.4708, 0.5065] | 0.6560 [0.6441, 0.6674] |
| `word_type_coverage` | L3 | 0.8602 [0.8546, 0.8656] | 0.9166 [0.9132, 0.9196] |
| `word_type_coverage` | L4 | 0.8565 [0.8504, 0.8620] | 0.8811 [0.8765, 0.8856] |
| `word_type_coverage` | L5 | 0.7241 [0.7152, 0.7331] | 0.7367 [0.7265, 0.7463] |
| `word_token_coverage` | L1 | 0.8808 [0.8736, 0.8876] | 0.9346 [0.9300, 0.9389] |
| `word_token_coverage` | L2 | 0.4548 [0.4357, 0.4742] | 0.6381 [0.6258, 0.6502] |
| `word_token_coverage` | L3 | 0.8564 [0.8507, 0.8614] | 0.9174 [0.9142, 0.9203] |
| `word_token_coverage` | L4 | 0.8152 [0.8075, 0.8227] | 0.8553 [0.8493, 0.8610] |
| `word_token_coverage` | L5 | 0.7057 [0.6971, 0.7150] | 0.7258 [0.7152, 0.7365] |
| `word_bigram_coverage` | L1 | 0.8904 [0.8832, 0.8970] | 0.9226 [0.9167, 0.9281] |
| `word_bigram_coverage` | L2 | 0.5199 [0.5020, 0.5379] | 0.6706 [0.6594, 0.6817] |
| `word_bigram_coverage` | L3 | 0.8431 [0.8366, 0.8492] | 0.9097 [0.9062, 0.9129] |
| `word_bigram_coverage` | L4 | 0.8045 [0.7967, 0.8123] | 0.8498 [0.8439, 0.8555] |
| `word_bigram_coverage` | L5 | 0.2156 [0.1933, 0.2380] | 0.5030 [0.4864, 0.5201] |
| `char3_coverage` | L1 | 0.8759 [0.8695, 0.8821] | 0.9327 [0.9282, 0.9366] |
| `char3_coverage` | L2 | 0.4022 [0.3821, 0.4223] | 0.6088 [0.5956, 0.6220] |
| `char3_coverage` | L3 | 0.8482 [0.8424, 0.8535] | 0.9146 [0.9112, 0.9177] |
| `char3_coverage` | L4 | 0.7560 [0.7467, 0.7647] | 0.8281 [0.8210, 0.8344] |
| `char3_coverage` | L5 | 0.6827 [0.6728, 0.6921] | 0.7262 [0.7157, 0.7364] |
| `char5_coverage` | L1 | 0.8822 [0.8758, 0.8882] | 0.9358 [0.9312, 0.9398] |
| `char5_coverage` | L2 | 0.4739 [0.4545, 0.4940] | 0.6373 [0.6247, 0.6500] |
| `char5_coverage` | L3 | 0.8689 [0.8636, 0.8737] | 0.9224 [0.9194, 0.9252] |
| `char5_coverage` | L4 | 0.8448 [0.8380, 0.8513] | 0.8752 [0.8702, 0.8801] |
| `char5_coverage` | L5 | 0.6052 [0.5918, 0.6184] | 0.6718 [0.6593, 0.6838] |
| `char8_coverage` | L1 | 0.8728 [0.8660, 0.8793] | 0.9194 [0.9142, 0.9240] |
| `char8_coverage` | L2 | 0.5004 [0.4800, 0.5204] | 0.6536 [0.6412, 0.6661] |
| `char8_coverage` | L3 | 0.8506 [0.8447, 0.8565] | 0.9139 [0.9106, 0.9170] |
| `char8_coverage` | L4 | 0.8377 [0.8313, 0.8441] | 0.8694 [0.8646, 0.8744] |
| `char8_coverage` | L5 | 0.3599 [0.3370, 0.3817] | 0.5683 [0.5525, 0.5838] |
| `rouge_l_recall` | L1 | 0.9040 [0.8973, 0.9101] | 0.9476 [0.9429, 0.9519] |
| `rouge_l_recall` | L2 | 0.6383 [0.6237, 0.6531] | 0.7475 [0.7384, 0.7566] |
| `rouge_l_recall` | L3 | 0.8840 [0.8792, 0.8884] | 0.9277 [0.9249, 0.9303] |
| `rouge_l_recall` | L4 | 0.8529 [0.8464, 0.8590] | 0.8758 [0.8708, 0.8808] |
| `rouge_l_recall` | L5 | 0.6879 [0.6788, 0.6974] | 0.6963 [0.6828, 0.7105] |
| `output_type_token_ratio` | L1 | 0.1669 [0.1461, 0.1871] | 0.4768 [0.4644, 0.4886] |
| `output_type_token_ratio` | L2 | -0.0810 [-0.1070, -0.0568] | 0.2587 [0.2419, 0.2748] |
| `output_type_token_ratio` | L3 | 0.3358 [0.3156, 0.3567] | 0.5518 [0.5379, 0.5660] |
| `output_type_token_ratio` | L4 | 0.2907 [0.2710, 0.3098] | 0.5237 [0.5104, 0.5364] |
| `output_type_token_ratio` | L5 | 0.5600 [0.5478, 0.5720] | 0.6665 [0.6568, 0.6759] |
| `output_bigram_repeat_fraction` | L1 | -0.2563 [-0.2748, -0.2370] | 0.1043 [0.0917, 0.1167] |
| `output_bigram_repeat_fraction` | L2 | 0.1093 [0.0847, 0.1339] | 0.3976 [0.3840, 0.4122] |
| `output_bigram_repeat_fraction` | L3 | -0.1691 [-0.1915, -0.1476] | 0.2601 [0.2447, 0.2750] |
| `output_bigram_repeat_fraction` | L4 | -0.1481 [-0.1696, -0.1277] | 0.2167 [0.2030, 0.2306] |
| `output_bigram_repeat_fraction` | L5 | -0.4363 [-0.4522, -0.4196] | -0.0129 [-0.0228, -0.0025] |
| `output_self_bits_per_byte` | L1 | 0.2441 [0.2248, 0.2631] | 0.5150 [0.5019, 0.5274] |
| `output_self_bits_per_byte` | L2 | 0.0221 [-0.0037, 0.0467] | 0.3437 [0.3257, 0.3615] |
| `output_self_bits_per_byte` | L3 | 0.4041 [0.3847, 0.4244] | 0.6126 [0.5994, 0.6260] |
| `output_self_bits_per_byte` | L4 | 0.2275 [0.2074, 0.2472] | 0.4832 [0.4694, 0.4963] |
| `output_self_bits_per_byte` | L5 | 0.5709 [0.5560, 0.5856] | 0.6892 [0.6781, 0.7003] |

# Appendix B — Auxiliary agreement alphas

`pairwise_continuous_alpha_rank` is ordinal and overlaps with Spearman; `pairwise_continuous_alpha_raw` is scale/calibration sensitive. Neither is used for primary cross-feature ranking.

| Family | Evaluator | Candidate/heuristic | Scope | Exact alpha namespace | Point | Effective n |
|---|---|---|---|---|---:|---:|
| direct | — | `prompt_bytes` | pooled | `pairwise_continuous_alpha_raw` | -0.3427 | 56110 |
| direct | — | `prompt_bytes` | pooled | `pairwise_continuous_alpha_rank` | 0.7640 | 56110 |
| direct | — | `output_bytes` | pooled | `pairwise_continuous_alpha_raw` | -0.4980 | 56110 |
| direct | — | `output_bytes` | pooled | `pairwise_continuous_alpha_rank` | -0.2968 | 56110 |
| direct | — | `prompt_words` | pooled | `pairwise_continuous_alpha_raw` | -0.3182 | 56110 |
| direct | — | `prompt_words` | pooled | `pairwise_continuous_alpha_rank` | 0.7698 | 56110 |
| direct | — | `output_words` | pooled | `pairwise_continuous_alpha_raw` | -0.5259 | 56110 |
| direct | — | `output_words` | pooled | `pairwise_continuous_alpha_rank` | -0.2790 | 56110 |
| direct | — | `prompt_to_output_byte_ratio` | pooled | `pairwise_continuous_alpha_raw` | 0.4416 | 56110 |
| direct | — | `prompt_to_output_byte_ratio` | pooled | `pairwise_continuous_alpha_rank` | 0.9304 | 56110 |
| direct | — | `word_type_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.8655 | 56110 |
| direct | — | `word_type_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9848 | 56110 |
| direct | — | `word_token_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.8317 | 56110 |
| direct | — | `word_token_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9783 | 56110 |
| direct | — | `word_bigram_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.9194 | 56110 |
| direct | — | `word_bigram_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9656 | 56110 |
| direct | — | `char3_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.7965 | 56110 |
| direct | — | `char3_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9710 | 56110 |
| direct | — | `char5_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.9483 | 56110 |
| direct | — | `char5_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9833 | 56110 |
| direct | — | `char8_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.9324 | 56110 |
| direct | — | `char8_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9702 | 56110 |
| direct | — | `rouge_l_recall` | pooled | `pairwise_continuous_alpha_raw` | 0.9189 | 56110 |
| direct | — | `rouge_l_recall` | pooled | `pairwise_continuous_alpha_rank` | 0.9826 | 56110 |
| direct | — | `output_type_token_ratio` | pooled | `pairwise_continuous_alpha_raw` | -0.4805 | 56110 |
| direct | — | `output_type_token_ratio` | pooled | `pairwise_continuous_alpha_rank` | 0.0157 | 56110 |
| direct | — | `output_bigram_repeat_fraction` | pooled | `pairwise_continuous_alpha_raw` | -0.1792 | 56110 |
| direct | — | `output_bigram_repeat_fraction` | pooled | `pairwise_continuous_alpha_rank` | 0.0961 | 56110 |
| direct | — | `output_self_bits_per_byte` | pooled | `pairwise_continuous_alpha_raw` | -0.9379 | 56110 |
| direct | — | `output_self_bits_per_byte` | pooled | `pairwise_continuous_alpha_rank` | 0.0987 | 56110 |
| convergence | llama | `blackbox_actual_ratio` | pooled | `pairwise_continuous_alpha_raw` | 0.8603 | 56110 |
| convergence | llama | `blackbox_actual_ratio` | pooled | `pairwise_continuous_alpha_rank` | 0.9570 | 56110 |
| convergence | llama | `prompt_bytes` | pooled | `pairwise_continuous_alpha_raw` | -0.3426 | 56110 |
| convergence | llama | `prompt_bytes` | pooled | `pairwise_continuous_alpha_rank` | 0.8055 | 56110 |
| convergence | llama | `output_bytes` | pooled | `pairwise_continuous_alpha_raw` | -0.4980 | 56110 |
| convergence | llama | `output_bytes` | pooled | `pairwise_continuous_alpha_rank` | -0.2823 | 56110 |
| convergence | llama | `prompt_words` | pooled | `pairwise_continuous_alpha_raw` | -0.3176 | 56110 |
| convergence | llama | `prompt_words` | pooled | `pairwise_continuous_alpha_rank` | 0.8153 | 56110 |
| convergence | llama | `output_words` | pooled | `pairwise_continuous_alpha_raw` | -0.5258 | 56110 |
| convergence | llama | `output_words` | pooled | `pairwise_continuous_alpha_rank` | -0.2584 | 56110 |
| convergence | llama | `prompt_to_output_byte_ratio` | pooled | `pairwise_continuous_alpha_raw` | 0.6870 | 56110 |
| convergence | llama | `prompt_to_output_byte_ratio` | pooled | `pairwise_continuous_alpha_rank` | 0.9254 | 56110 |
| convergence | llama | `word_type_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.9536 | 56110 |
| convergence | llama | `word_type_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9572 | 56110 |
| convergence | llama | `word_token_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.9549 | 56110 |
| convergence | llama | `word_token_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9659 | 56110 |
| convergence | llama | `word_bigram_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.7842 | 56110 |
| convergence | llama | `word_bigram_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9295 | 56110 |
| convergence | llama | `char3_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.9487 | 56110 |
| convergence | llama | `char3_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9613 | 56110 |
| convergence | llama | `char5_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.9191 | 56110 |
| convergence | llama | `char5_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9565 | 56110 |
| convergence | llama | `char8_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.7661 | 56110 |
| convergence | llama | `char8_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9258 | 56110 |
| convergence | llama | `rouge_l_recall` | pooled | `pairwise_continuous_alpha_raw` | 0.9416 | 56110 |
| convergence | llama | `rouge_l_recall` | pooled | `pairwise_continuous_alpha_rank` | 0.9707 | 56110 |
| convergence | llama | `output_type_token_ratio` | pooled | `pairwise_continuous_alpha_raw` | -0.2276 | 56110 |
| convergence | llama | `output_type_token_ratio` | pooled | `pairwise_continuous_alpha_rank` | 0.0416 | 56110 |
| convergence | llama | `output_bigram_repeat_fraction` | pooled | `pairwise_continuous_alpha_raw` | -0.2819 | 56110 |
| convergence | llama | `output_bigram_repeat_fraction` | pooled | `pairwise_continuous_alpha_rank` | 0.0562 | 56110 |
| convergence | llama | `output_self_bits_per_byte` | pooled | `pairwise_continuous_alpha_raw` | -0.9303 | 56110 |
| convergence | llama | `output_self_bits_per_byte` | pooled | `pairwise_continuous_alpha_rank` | 0.1212 | 56110 |
| convergence | mixtral | `blackbox_actual_ratio` | pooled | `pairwise_continuous_alpha_raw` | 0.8820 | 56110 |
| convergence | mixtral | `blackbox_actual_ratio` | pooled | `pairwise_continuous_alpha_rank` | 0.9563 | 56110 |
| convergence | mixtral | `prompt_bytes` | pooled | `pairwise_continuous_alpha_raw` | -0.3426 | 56110 |
| convergence | mixtral | `prompt_bytes` | pooled | `pairwise_continuous_alpha_rank` | 0.7994 | 56110 |
| convergence | mixtral | `output_bytes` | pooled | `pairwise_continuous_alpha_raw` | -0.4980 | 56110 |
| convergence | mixtral | `output_bytes` | pooled | `pairwise_continuous_alpha_rank` | -0.2876 | 56110 |
| convergence | mixtral | `prompt_words` | pooled | `pairwise_continuous_alpha_raw` | -0.3177 | 56110 |
| convergence | mixtral | `prompt_words` | pooled | `pairwise_continuous_alpha_rank` | 0.8097 | 56110 |
| convergence | mixtral | `output_words` | pooled | `pairwise_continuous_alpha_raw` | -0.5258 | 56110 |
| convergence | mixtral | `output_words` | pooled | `pairwise_continuous_alpha_rank` | -0.2623 | 56110 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | pooled | `pairwise_continuous_alpha_raw` | 0.6439 | 56110 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | pooled | `pairwise_continuous_alpha_rank` | 0.9197 | 56110 |
| convergence | mixtral | `word_type_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.9475 | 56110 |
| convergence | mixtral | `word_type_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9562 | 56110 |
| convergence | mixtral | `word_token_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.9400 | 56110 |
| convergence | mixtral | `word_token_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9633 | 56110 |
| convergence | mixtral | `word_bigram_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.8060 | 56110 |
| convergence | mixtral | `word_bigram_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9292 | 56110 |
| convergence | mixtral | `char3_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.9286 | 56110 |
| convergence | mixtral | `char3_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9583 | 56110 |
| convergence | mixtral | `char5_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.9250 | 56110 |
| convergence | mixtral | `char5_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9544 | 56110 |
| convergence | mixtral | `char8_coverage` | pooled | `pairwise_continuous_alpha_raw` | 0.7888 | 56110 |
| convergence | mixtral | `char8_coverage` | pooled | `pairwise_continuous_alpha_rank` | 0.9236 | 56110 |
| convergence | mixtral | `rouge_l_recall` | pooled | `pairwise_continuous_alpha_raw` | 0.9446 | 56110 |
| convergence | mixtral | `rouge_l_recall` | pooled | `pairwise_continuous_alpha_rank` | 0.9693 | 56110 |
| convergence | mixtral | `output_type_token_ratio` | pooled | `pairwise_continuous_alpha_raw` | -0.2635 | 56110 |
| convergence | mixtral | `output_type_token_ratio` | pooled | `pairwise_continuous_alpha_rank` | 0.0393 | 56110 |
| convergence | mixtral | `output_bigram_repeat_fraction` | pooled | `pairwise_continuous_alpha_raw` | -0.2720 | 56110 |
| convergence | mixtral | `output_bigram_repeat_fraction` | pooled | `pairwise_continuous_alpha_rank` | 0.0577 | 56110 |
| convergence | mixtral | `output_self_bits_per_byte` | pooled | `pairwise_continuous_alpha_raw` | -0.9316 | 56110 |
| convergence | mixtral | `output_self_bits_per_byte` | pooled | `pairwise_continuous_alpha_rank` | 0.1223 | 56110 |
| direct | — | `prompt_bytes` | L1 | `pairwise_continuous_alpha_raw` | -0.5517 | 11222 |
| direct | — | `prompt_bytes` | L1 | `pairwise_continuous_alpha_rank` | 0.1124 | 11222 |
| direct | — | `output_bytes` | L1 | `pairwise_continuous_alpha_raw` | -0.5898 | 11222 |
| direct | — | `output_bytes` | L1 | `pairwise_continuous_alpha_rank` | -0.3771 | 11222 |
| direct | — | `prompt_words` | L1 | `pairwise_continuous_alpha_raw` | -0.5414 | 11222 |
| direct | — | `prompt_words` | L1 | `pairwise_continuous_alpha_rank` | 0.0855 | 11222 |
| direct | — | `output_words` | L1 | `pairwise_continuous_alpha_raw` | -0.5903 | 11222 |
| direct | — | `output_words` | L1 | `pairwise_continuous_alpha_rank` | -0.3338 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | L1 | `pairwise_continuous_alpha_raw` | 0.0429 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | L1 | `pairwise_continuous_alpha_rank` | 0.7752 | 11222 |
| direct | — | `word_type_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.5225 | 11222 |
| direct | — | `word_type_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.9195 | 11222 |
| direct | — | `word_token_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.4858 | 11222 |
| direct | — | `word_token_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.9242 | 11222 |
| direct | — | `word_bigram_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8760 | 11222 |
| direct | — | `word_bigram_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.9298 | 11222 |
| direct | — | `char3_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.5158 | 11222 |
| direct | — | `char3_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.9492 | 11222 |
| direct | — | `char5_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8161 | 11222 |
| direct | — | `char5_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.9640 | 11222 |
| direct | — | `char8_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.9361 | 11222 |
| direct | — | `char8_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.9643 | 11222 |
| direct | — | `rouge_l_recall` | L1 | `pairwise_continuous_alpha_raw` | 0.6839 | 11222 |
| direct | — | `rouge_l_recall` | L1 | `pairwise_continuous_alpha_rank` | 0.9310 | 11222 |
| direct | — | `output_type_token_ratio` | L1 | `pairwise_continuous_alpha_raw` | 0.1346 | 11222 |
| direct | — | `output_type_token_ratio` | L1 | `pairwise_continuous_alpha_rank` | 0.0839 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | L1 | `pairwise_continuous_alpha_raw` | -0.7375 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | L1 | `pairwise_continuous_alpha_rank` | -0.1288 | 11222 |
| direct | — | `output_self_bits_per_byte` | L1 | `pairwise_continuous_alpha_raw` | -0.9228 | 11222 |
| direct | — | `output_self_bits_per_byte` | L1 | `pairwise_continuous_alpha_rank` | 0.1613 | 11222 |
| convergence | llama | `blackbox_actual_ratio` | L1 | `pairwise_continuous_alpha_raw` | 0.6662 | 11222 |
| convergence | llama | `blackbox_actual_ratio` | L1 | `pairwise_continuous_alpha_rank` | 0.8771 | 11222 |
| convergence | llama | `prompt_bytes` | L1 | `pairwise_continuous_alpha_raw` | -0.5517 | 11222 |
| convergence | llama | `prompt_bytes` | L1 | `pairwise_continuous_alpha_rank` | 0.2374 | 11222 |
| convergence | llama | `output_bytes` | L1 | `pairwise_continuous_alpha_raw` | -0.5898 | 11222 |
| convergence | llama | `output_bytes` | L1 | `pairwise_continuous_alpha_rank` | -0.2360 | 11222 |
| convergence | llama | `prompt_words` | L1 | `pairwise_continuous_alpha_raw` | -0.5410 | 11222 |
| convergence | llama | `prompt_words` | L1 | `pairwise_continuous_alpha_rank` | 0.2473 | 11222 |
| convergence | llama | `output_words` | L1 | `pairwise_continuous_alpha_raw` | -0.5900 | 11222 |
| convergence | llama | `output_words` | L1 | `pairwise_continuous_alpha_rank` | -0.1698 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | L1 | `pairwise_continuous_alpha_raw` | 0.3676 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | L1 | `pairwise_continuous_alpha_rank` | 0.6289 | 11222 |
| convergence | llama | `word_type_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8966 | 11222 |
| convergence | llama | `word_type_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.9040 | 11222 |
| convergence | llama | `word_token_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8577 | 11222 |
| convergence | llama | `word_token_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.8884 | 11222 |
| convergence | llama | `word_bigram_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8046 | 11222 |
| convergence | llama | `word_bigram_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.8990 | 11222 |
| convergence | llama | `char3_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8714 | 11222 |
| convergence | llama | `char3_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.8840 | 11222 |
| convergence | llama | `char5_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8992 | 11222 |
| convergence | llama | `char5_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.8907 | 11222 |
| convergence | llama | `char8_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.7269 | 11222 |
| convergence | llama | `char8_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.8824 | 11222 |
| convergence | llama | `rouge_l_recall` | L1 | `pairwise_continuous_alpha_raw` | 0.9141 | 11222 |
| convergence | llama | `rouge_l_recall` | L1 | `pairwise_continuous_alpha_rank` | 0.9119 | 11222 |
| convergence | llama | `output_type_token_ratio` | L1 | `pairwise_continuous_alpha_raw` | 0.0343 | 11222 |
| convergence | llama | `output_type_token_ratio` | L1 | `pairwise_continuous_alpha_rank` | 0.1709 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | L1 | `pairwise_continuous_alpha_raw` | -0.8379 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | L1 | `pairwise_continuous_alpha_rank` | -0.2605 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | L1 | `pairwise_continuous_alpha_raw` | -0.9129 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | L1 | `pairwise_continuous_alpha_rank` | 0.2475 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | L1 | `pairwise_continuous_alpha_raw` | 0.6946 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | L1 | `pairwise_continuous_alpha_rank` | 0.8692 | 11222 |
| convergence | mixtral | `prompt_bytes` | L1 | `pairwise_continuous_alpha_raw` | -0.5517 | 11222 |
| convergence | mixtral | `prompt_bytes` | L1 | `pairwise_continuous_alpha_rank` | 0.2215 | 11222 |
| convergence | mixtral | `output_bytes` | L1 | `pairwise_continuous_alpha_raw` | -0.5898 | 11222 |
| convergence | mixtral | `output_bytes` | L1 | `pairwise_continuous_alpha_rank` | -0.2540 | 11222 |
| convergence | mixtral | `prompt_words` | L1 | `pairwise_continuous_alpha_raw` | -0.5411 | 11222 |
| convergence | mixtral | `prompt_words` | L1 | `pairwise_continuous_alpha_rank` | 0.2317 | 11222 |
| convergence | mixtral | `output_words` | L1 | `pairwise_continuous_alpha_raw` | -0.5901 | 11222 |
| convergence | mixtral | `output_words` | L1 | `pairwise_continuous_alpha_rank` | -0.1861 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | L1 | `pairwise_continuous_alpha_raw` | 0.3224 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | L1 | `pairwise_continuous_alpha_rank` | 0.6339 | 11222 |
| convergence | mixtral | `word_type_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8606 | 11222 |
| convergence | mixtral | `word_type_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.8941 | 11222 |
| convergence | mixtral | `word_token_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8138 | 11222 |
| convergence | mixtral | `word_token_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.8733 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8104 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.8817 | 11222 |
| convergence | mixtral | `char3_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8280 | 11222 |
| convergence | mixtral | `char3_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.8679 | 11222 |
| convergence | mixtral | `char5_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.8868 | 11222 |
| convergence | mixtral | `char5_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.8736 | 11222 |
| convergence | mixtral | `char8_coverage` | L1 | `pairwise_continuous_alpha_raw` | 0.7393 | 11222 |
| convergence | mixtral | `char8_coverage` | L1 | `pairwise_continuous_alpha_rank` | 0.8632 | 11222 |
| convergence | mixtral | `rouge_l_recall` | L1 | `pairwise_continuous_alpha_raw` | 0.8907 | 11222 |
| convergence | mixtral | `rouge_l_recall` | L1 | `pairwise_continuous_alpha_rank` | 0.8960 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | L1 | `pairwise_continuous_alpha_raw` | 0.0485 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | L1 | `pairwise_continuous_alpha_rank` | 0.1629 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | L1 | `pairwise_continuous_alpha_raw` | -0.8262 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | L1 | `pairwise_continuous_alpha_rank` | -0.2519 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | L1 | `pairwise_continuous_alpha_raw` | -0.9142 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | L1 | `pairwise_continuous_alpha_rank` | 0.2409 | 11222 |
| direct | — | `prompt_bytes` | L2 | `pairwise_continuous_alpha_raw` | -0.5600 | 11222 |
| direct | — | `prompt_bytes` | L2 | `pairwise_continuous_alpha_rank` | -0.0254 | 11222 |
| direct | — | `output_bytes` | L2 | `pairwise_continuous_alpha_raw` | -0.5514 | 11222 |
| direct | — | `output_bytes` | L2 | `pairwise_continuous_alpha_rank` | -0.1947 | 11222 |
| direct | — | `prompt_words` | L2 | `pairwise_continuous_alpha_raw` | -0.5489 | 11222 |
| direct | — | `prompt_words` | L2 | `pairwise_continuous_alpha_rank` | -0.1108 | 11222 |
| direct | — | `output_words` | L2 | `pairwise_continuous_alpha_raw` | -0.5475 | 11222 |
| direct | — | `output_words` | L2 | `pairwise_continuous_alpha_rank` | -0.2028 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | L2 | `pairwise_continuous_alpha_raw` | -0.7659 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | L2 | `pairwise_continuous_alpha_rank` | 0.5488 | 11222 |
| direct | — | `word_type_coverage` | L2 | `pairwise_continuous_alpha_raw` | 0.3078 | 11222 |
| direct | — | `word_type_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.8734 | 11222 |
| direct | — | `word_token_coverage` | L2 | `pairwise_continuous_alpha_raw` | -0.1306 | 11222 |
| direct | — | `word_token_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.8373 | 11222 |
| direct | — | `word_bigram_coverage` | L2 | `pairwise_continuous_alpha_raw` | 0.5688 | 11222 |
| direct | — | `word_bigram_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.8814 | 11222 |
| direct | — | `char3_coverage` | L2 | `pairwise_continuous_alpha_raw` | -0.3901 | 11222 |
| direct | — | `char3_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.8016 | 11222 |
| direct | — | `char5_coverage` | L2 | `pairwise_continuous_alpha_raw` | 0.7300 | 11222 |
| direct | — | `char5_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.8994 | 11222 |
| direct | — | `char8_coverage` | L2 | `pairwise_continuous_alpha_raw` | 0.5953 | 11222 |
| direct | — | `char8_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.9251 | 11222 |
| direct | — | `rouge_l_recall` | L2 | `pairwise_continuous_alpha_raw` | 0.5638 | 11222 |
| direct | — | `rouge_l_recall` | L2 | `pairwise_continuous_alpha_rank` | 0.8563 | 11222 |
| direct | — | `output_type_token_ratio` | L2 | `pairwise_continuous_alpha_raw` | -0.7535 | 11222 |
| direct | — | `output_type_token_ratio` | L2 | `pairwise_continuous_alpha_rank` | -0.2701 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | L2 | `pairwise_continuous_alpha_raw` | -0.6678 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | L2 | `pairwise_continuous_alpha_rank` | 0.3546 | 11222 |
| direct | — | `output_self_bits_per_byte` | L2 | `pairwise_continuous_alpha_raw` | -0.9629 | 11222 |
| direct | — | `output_self_bits_per_byte` | L2 | `pairwise_continuous_alpha_rank` | -0.1757 | 11222 |
| convergence | llama | `blackbox_actual_ratio` | L2 | `pairwise_continuous_alpha_raw` | -0.1938 | 11222 |
| convergence | llama | `blackbox_actual_ratio` | L2 | `pairwise_continuous_alpha_rank` | 0.6202 | 11222 |
| convergence | llama | `prompt_bytes` | L2 | `pairwise_continuous_alpha_raw` | -0.5600 | 11222 |
| convergence | llama | `prompt_bytes` | L2 | `pairwise_continuous_alpha_rank` | -0.1041 | 11222 |
| convergence | llama | `output_bytes` | L2 | `pairwise_continuous_alpha_raw` | -0.5513 | 11222 |
| convergence | llama | `output_bytes` | L2 | `pairwise_continuous_alpha_rank` | -0.1824 | 11222 |
| convergence | llama | `prompt_words` | L2 | `pairwise_continuous_alpha_raw` | -0.5486 | 11222 |
| convergence | llama | `prompt_words` | L2 | `pairwise_continuous_alpha_rank` | -0.1151 | 11222 |
| convergence | llama | `output_words` | L2 | `pairwise_continuous_alpha_raw` | -0.5472 | 11222 |
| convergence | llama | `output_words` | L2 | `pairwise_continuous_alpha_rank` | -0.1457 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | L2 | `pairwise_continuous_alpha_raw` | -0.6824 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | L2 | `pairwise_continuous_alpha_rank` | 0.2188 | 11222 |
| convergence | llama | `word_type_coverage` | L2 | `pairwise_continuous_alpha_raw` | 0.4676 | 11222 |
| convergence | llama | `word_type_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.5333 | 11222 |
| convergence | llama | `word_token_coverage` | L2 | `pairwise_continuous_alpha_raw` | 0.4654 | 11222 |
| convergence | llama | `word_token_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.5031 | 11222 |
| convergence | llama | `word_bigram_coverage` | L2 | `pairwise_continuous_alpha_raw` | -0.3702 | 11222 |
| convergence | llama | `word_bigram_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.5728 | 11222 |
| convergence | llama | `char3_coverage` | L2 | `pairwise_continuous_alpha_raw` | 0.2251 | 11222 |
| convergence | llama | `char3_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.4495 | 11222 |
| convergence | llama | `char5_coverage` | L2 | `pairwise_continuous_alpha_raw` | 0.1486 | 11222 |
| convergence | llama | `char5_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.5313 | 11222 |
| convergence | llama | `char8_coverage` | L2 | `pairwise_continuous_alpha_raw` | -0.3914 | 11222 |
| convergence | llama | `char8_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.5621 | 11222 |
| convergence | llama | `rouge_l_recall` | L2 | `pairwise_continuous_alpha_raw` | 0.3861 | 11222 |
| convergence | llama | `rouge_l_recall` | L2 | `pairwise_continuous_alpha_rank` | 0.6845 | 11222 |
| convergence | llama | `output_type_token_ratio` | L2 | `pairwise_continuous_alpha_raw` | -0.3099 | 11222 |
| convergence | llama | `output_type_token_ratio` | L2 | `pairwise_continuous_alpha_rank` | -0.1078 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | L2 | `pairwise_continuous_alpha_raw` | -0.8733 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | L2 | `pairwise_continuous_alpha_rank` | 0.1521 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | L2 | `pairwise_continuous_alpha_raw` | -0.9587 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | L2 | `pairwise_continuous_alpha_rank` | -0.0040 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | L2 | `pairwise_continuous_alpha_raw` | -0.0665 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | L2 | `pairwise_continuous_alpha_rank` | 0.4962 | 11222 |
| convergence | mixtral | `prompt_bytes` | L2 | `pairwise_continuous_alpha_raw` | -0.5600 | 11222 |
| convergence | mixtral | `prompt_bytes` | L2 | `pairwise_continuous_alpha_rank` | -0.0935 | 11222 |
| convergence | mixtral | `output_bytes` | L2 | `pairwise_continuous_alpha_raw` | -0.5513 | 11222 |
| convergence | mixtral | `output_bytes` | L2 | `pairwise_continuous_alpha_rank` | -0.1409 | 11222 |
| convergence | mixtral | `prompt_words` | L2 | `pairwise_continuous_alpha_raw` | -0.5487 | 11222 |
| convergence | mixtral | `prompt_words` | L2 | `pairwise_continuous_alpha_rank` | -0.0776 | 11222 |
| convergence | mixtral | `output_words` | L2 | `pairwise_continuous_alpha_raw` | -0.5473 | 11222 |
| convergence | mixtral | `output_words` | L2 | `pairwise_continuous_alpha_rank` | -0.0898 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | L2 | `pairwise_continuous_alpha_raw` | -0.7275 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | L2 | `pairwise_continuous_alpha_rank` | 0.1128 | 11222 |
| convergence | mixtral | `word_type_coverage` | L2 | `pairwise_continuous_alpha_raw` | 0.4599 | 11222 |
| convergence | mixtral | `word_type_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.4447 | 11222 |
| convergence | mixtral | `word_token_coverage` | L2 | `pairwise_continuous_alpha_raw` | 0.2746 | 11222 |
| convergence | mixtral | `word_token_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.4066 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | L2 | `pairwise_continuous_alpha_raw` | -0.2843 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.4670 | 11222 |
| convergence | mixtral | `char3_coverage` | L2 | `pairwise_continuous_alpha_raw` | -0.0085 | 11222 |
| convergence | mixtral | `char3_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.3550 | 11222 |
| convergence | mixtral | `char5_coverage` | L2 | `pairwise_continuous_alpha_raw` | 0.2271 | 11222 |
| convergence | mixtral | `char5_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.4165 | 11222 |
| convergence | mixtral | `char8_coverage` | L2 | `pairwise_continuous_alpha_raw` | -0.3163 | 11222 |
| convergence | mixtral | `char8_coverage` | L2 | `pairwise_continuous_alpha_rank` | 0.4389 | 11222 |
| convergence | mixtral | `rouge_l_recall` | L2 | `pairwise_continuous_alpha_raw` | 0.4872 | 11222 |
| convergence | mixtral | `rouge_l_recall` | L2 | `pairwise_continuous_alpha_rank` | 0.5922 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | L2 | `pairwise_continuous_alpha_raw` | -0.3900 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | L2 | `pairwise_continuous_alpha_rank` | -0.0541 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | L2 | `pairwise_continuous_alpha_raw` | -0.8532 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | L2 | `pairwise_continuous_alpha_rank` | 0.0665 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | L2 | `pairwise_continuous_alpha_raw` | -0.9592 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | L2 | `pairwise_continuous_alpha_rank` | 0.0484 | 11222 |
| direct | — | `prompt_bytes` | L3 | `pairwise_continuous_alpha_raw` | -0.9341 | 11222 |
| direct | — | `prompt_bytes` | L3 | `pairwise_continuous_alpha_rank` | -0.1050 | 11222 |
| direct | — | `output_bytes` | L3 | `pairwise_continuous_alpha_raw` | -0.6890 | 11222 |
| direct | — | `output_bytes` | L3 | `pairwise_continuous_alpha_rank` | -0.8532 | 11222 |
| direct | — | `prompt_words` | L3 | `pairwise_continuous_alpha_raw` | -0.9267 | 11222 |
| direct | — | `prompt_words` | L3 | `pairwise_continuous_alpha_rank` | -0.0854 | 11222 |
| direct | — | `output_words` | L3 | `pairwise_continuous_alpha_raw` | -0.7127 | 11222 |
| direct | — | `output_words` | L3 | `pairwise_continuous_alpha_rank` | -0.8792 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | L3 | `pairwise_continuous_alpha_raw` | 0.5507 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | L3 | `pairwise_continuous_alpha_rank` | 0.9143 | 11222 |
| direct | — | `word_type_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.6807 | 11222 |
| direct | — | `word_type_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.9692 | 11222 |
| direct | — | `word_token_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.8580 | 11222 |
| direct | — | `word_token_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.9568 | 11222 |
| direct | — | `word_bigram_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.7939 | 11222 |
| direct | — | `word_bigram_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.9415 | 11222 |
| direct | — | `char3_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.8063 | 11222 |
| direct | — | `char3_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.9458 | 11222 |
| direct | — | `char5_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.9805 | 11222 |
| direct | — | `char5_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.9791 | 11222 |
| direct | — | `char8_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.8271 | 11222 |
| direct | — | `char8_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.9665 | 11222 |
| direct | — | `rouge_l_recall` | L3 | `pairwise_continuous_alpha_raw` | 0.9546 | 11222 |
| direct | — | `rouge_l_recall` | L3 | `pairwise_continuous_alpha_rank` | 0.9556 | 11222 |
| direct | — | `output_type_token_ratio` | L3 | `pairwise_continuous_alpha_raw` | -0.5210 | 11222 |
| direct | — | `output_type_token_ratio` | L3 | `pairwise_continuous_alpha_rank` | 0.4477 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | L3 | `pairwise_continuous_alpha_raw` | -0.5235 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | L3 | `pairwise_continuous_alpha_rank` | -0.2186 | 11222 |
| direct | — | `output_self_bits_per_byte` | L3 | `pairwise_continuous_alpha_raw` | -0.9541 | 11222 |
| direct | — | `output_self_bits_per_byte` | L3 | `pairwise_continuous_alpha_rank` | 0.5075 | 11222 |
| convergence | llama | `blackbox_actual_ratio` | L3 | `pairwise_continuous_alpha_raw` | 0.7516 | 11222 |
| convergence | llama | `blackbox_actual_ratio` | L3 | `pairwise_continuous_alpha_rank` | 0.8504 | 11222 |
| convergence | llama | `prompt_bytes` | L3 | `pairwise_continuous_alpha_raw` | -0.9341 | 11222 |
| convergence | llama | `prompt_bytes` | L3 | `pairwise_continuous_alpha_rank` | 0.0603 | 11222 |
| convergence | llama | `output_bytes` | L3 | `pairwise_continuous_alpha_raw` | -0.6890 | 11222 |
| convergence | llama | `output_bytes` | L3 | `pairwise_continuous_alpha_rank` | -0.6923 | 11222 |
| convergence | llama | `prompt_words` | L3 | `pairwise_continuous_alpha_raw` | -0.9265 | 11222 |
| convergence | llama | `prompt_words` | L3 | `pairwise_continuous_alpha_rank` | 0.1034 | 11222 |
| convergence | llama | `output_words` | L3 | `pairwise_continuous_alpha_raw` | -0.7126 | 11222 |
| convergence | llama | `output_words` | L3 | `pairwise_continuous_alpha_rank` | -0.6986 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | L3 | `pairwise_continuous_alpha_raw` | 0.7228 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | L3 | `pairwise_continuous_alpha_rank` | 0.8136 | 11222 |
| convergence | llama | `word_type_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.8499 | 11222 |
| convergence | llama | `word_type_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8572 | 11222 |
| convergence | llama | `word_token_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.8787 | 11222 |
| convergence | llama | `word_token_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8531 | 11222 |
| convergence | llama | `word_bigram_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.4364 | 11222 |
| convergence | llama | `word_bigram_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8403 | 11222 |
| convergence | llama | `char3_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.8755 | 11222 |
| convergence | llama | `char3_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8418 | 11222 |
| convergence | llama | `char5_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.7734 | 11222 |
| convergence | llama | `char5_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8629 | 11222 |
| convergence | llama | `char8_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.4540 | 11222 |
| convergence | llama | `char8_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8448 | 11222 |
| convergence | llama | `rouge_l_recall` | L3 | `pairwise_continuous_alpha_raw` | 0.7759 | 11222 |
| convergence | llama | `rouge_l_recall` | L3 | `pairwise_continuous_alpha_rank` | 0.8797 | 11222 |
| convergence | llama | `output_type_token_ratio` | L3 | `pairwise_continuous_alpha_raw` | -0.3548 | 11222 |
| convergence | llama | `output_type_token_ratio` | L3 | `pairwise_continuous_alpha_rank` | 0.3244 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | L3 | `pairwise_continuous_alpha_raw` | -0.6050 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | L3 | `pairwise_continuous_alpha_rank` | -0.1596 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | L3 | `pairwise_continuous_alpha_raw` | -0.9529 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | L3 | `pairwise_continuous_alpha_rank` | 0.3927 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | L3 | `pairwise_continuous_alpha_raw` | 0.7843 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | L3 | `pairwise_continuous_alpha_rank` | 0.8711 | 11222 |
| convergence | mixtral | `prompt_bytes` | L3 | `pairwise_continuous_alpha_raw` | -0.9341 | 11222 |
| convergence | mixtral | `prompt_bytes` | L3 | `pairwise_continuous_alpha_rank` | -0.0265 | 11222 |
| convergence | mixtral | `output_bytes` | L3 | `pairwise_continuous_alpha_raw` | -0.6890 | 11222 |
| convergence | mixtral | `output_bytes` | L3 | `pairwise_continuous_alpha_rank` | -0.7445 | 11222 |
| convergence | mixtral | `prompt_words` | L3 | `pairwise_continuous_alpha_raw` | -0.9265 | 11222 |
| convergence | mixtral | `prompt_words` | L3 | `pairwise_continuous_alpha_rank` | 0.0134 | 11222 |
| convergence | mixtral | `output_words` | L3 | `pairwise_continuous_alpha_raw` | -0.7126 | 11222 |
| convergence | mixtral | `output_words` | L3 | `pairwise_continuous_alpha_rank` | -0.7490 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | L3 | `pairwise_continuous_alpha_raw` | 0.7053 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | L3 | `pairwise_continuous_alpha_rank` | 0.8297 | 11222 |
| convergence | mixtral | `word_type_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.8306 | 11222 |
| convergence | mixtral | `word_type_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8633 | 11222 |
| convergence | mixtral | `word_token_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.8805 | 11222 |
| convergence | mixtral | `word_token_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8597 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.4568 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8459 | 11222 |
| convergence | mixtral | `char3_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.8780 | 11222 |
| convergence | mixtral | `char3_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8546 | 11222 |
| convergence | mixtral | `char5_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.7980 | 11222 |
| convergence | mixtral | `char5_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8750 | 11222 |
| convergence | mixtral | `char8_coverage` | L3 | `pairwise_continuous_alpha_raw` | 0.4792 | 11222 |
| convergence | mixtral | `char8_coverage` | L3 | `pairwise_continuous_alpha_rank` | 0.8565 | 11222 |
| convergence | mixtral | `rouge_l_recall` | L3 | `pairwise_continuous_alpha_raw` | 0.7965 | 11222 |
| convergence | mixtral | `rouge_l_recall` | L3 | `pairwise_continuous_alpha_rank` | 0.8884 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | L3 | `pairwise_continuous_alpha_raw` | -0.3824 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | L3 | `pairwise_continuous_alpha_rank` | 0.3473 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | L3 | `pairwise_continuous_alpha_raw` | -0.6110 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | L3 | `pairwise_continuous_alpha_rank` | -0.1786 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | L3 | `pairwise_continuous_alpha_raw` | -0.9533 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | L3 | `pairwise_continuous_alpha_rank` | 0.4155 | 11222 |
| direct | — | `prompt_bytes` | L4 | `pairwise_continuous_alpha_raw` | -0.9423 | 11222 |
| direct | — | `prompt_bytes` | L4 | `pairwise_continuous_alpha_rank` | -0.1646 | 11222 |
| direct | — | `output_bytes` | L4 | `pairwise_continuous_alpha_raw` | -0.5983 | 11222 |
| direct | — | `output_bytes` | L4 | `pairwise_continuous_alpha_rank` | -0.8097 | 11222 |
| direct | — | `prompt_words` | L4 | `pairwise_continuous_alpha_raw` | -0.9401 | 11222 |
| direct | — | `prompt_words` | L4 | `pairwise_continuous_alpha_rank` | -0.1107 | 11222 |
| direct | — | `output_words` | L4 | `pairwise_continuous_alpha_raw` | -0.6282 | 11222 |
| direct | — | `output_words` | L4 | `pairwise_continuous_alpha_rank` | -0.8582 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | L4 | `pairwise_continuous_alpha_raw` | 0.6766 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | L4 | `pairwise_continuous_alpha_rank` | 0.8550 | 11222 |
| direct | — | `word_type_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.6607 | 11222 |
| direct | — | `word_type_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.9548 | 11222 |
| direct | — | `word_token_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.9440 | 11222 |
| direct | — | `word_token_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.9578 | 11222 |
| direct | — | `word_bigram_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.0824 | 11222 |
| direct | — | `word_bigram_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.8820 | 11222 |
| direct | — | `char3_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.9004 | 11222 |
| direct | — | `char3_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.9201 | 11222 |
| direct | — | `char5_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.8083 | 11222 |
| direct | — | `char5_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.9767 | 11222 |
| direct | — | `char8_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.2456 | 11222 |
| direct | — | `char8_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.9344 | 11222 |
| direct | — | `rouge_l_recall` | L4 | `pairwise_continuous_alpha_raw` | 0.6085 | 11222 |
| direct | — | `rouge_l_recall` | L4 | `pairwise_continuous_alpha_rank` | 0.9532 | 11222 |
| direct | — | `output_type_token_ratio` | L4 | `pairwise_continuous_alpha_raw` | -0.7966 | 11222 |
| direct | — | `output_type_token_ratio` | L4 | `pairwise_continuous_alpha_rank` | 0.4930 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | L4 | `pairwise_continuous_alpha_raw` | -0.3296 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | L4 | `pairwise_continuous_alpha_rank` | -0.3182 | 11222 |
| direct | — | `output_self_bits_per_byte` | L4 | `pairwise_continuous_alpha_raw` | -0.9632 | 11222 |
| direct | — | `output_self_bits_per_byte` | L4 | `pairwise_continuous_alpha_rank` | 0.4263 | 11222 |
| convergence | llama | `blackbox_actual_ratio` | L4 | `pairwise_continuous_alpha_raw` | 0.7953 | 11222 |
| convergence | llama | `blackbox_actual_ratio` | L4 | `pairwise_continuous_alpha_rank` | 0.8437 | 11222 |
| convergence | llama | `prompt_bytes` | L4 | `pairwise_continuous_alpha_raw` | -0.9423 | 11222 |
| convergence | llama | `prompt_bytes` | L4 | `pairwise_continuous_alpha_rank` | 0.0080 | 11222 |
| convergence | llama | `output_bytes` | L4 | `pairwise_continuous_alpha_raw` | -0.5983 | 11222 |
| convergence | llama | `output_bytes` | L4 | `pairwise_continuous_alpha_rank` | -0.6050 | 11222 |
| convergence | llama | `prompt_words` | L4 | `pairwise_continuous_alpha_raw` | -0.9400 | 11222 |
| convergence | llama | `prompt_words` | L4 | `pairwise_continuous_alpha_rank` | 0.0538 | 11222 |
| convergence | llama | `output_words` | L4 | `pairwise_continuous_alpha_raw` | -0.6282 | 11222 |
| convergence | llama | `output_words` | L4 | `pairwise_continuous_alpha_rank` | -0.6512 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | L4 | `pairwise_continuous_alpha_raw` | 0.6264 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | L4 | `pairwise_continuous_alpha_rank` | 0.6865 | 11222 |
| convergence | llama | `word_type_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.7025 | 11222 |
| convergence | llama | `word_type_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.8604 | 11222 |
| convergence | llama | `word_token_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.7720 | 11222 |
| convergence | llama | `word_token_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.8203 | 11222 |
| convergence | llama | `word_bigram_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.0674 | 11222 |
| convergence | llama | `word_bigram_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.8084 | 11222 |
| convergence | llama | `char3_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.7593 | 11222 |
| convergence | llama | `char3_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.7586 | 11222 |
| convergence | llama | `char5_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.6142 | 11222 |
| convergence | llama | `char5_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.8462 | 11222 |
| convergence | llama | `char8_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.1872 | 11222 |
| convergence | llama | `char8_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.8385 | 11222 |
| convergence | llama | `rouge_l_recall` | L4 | `pairwise_continuous_alpha_raw` | 0.4820 | 11222 |
| convergence | llama | `rouge_l_recall` | L4 | `pairwise_continuous_alpha_rank` | 0.8580 | 11222 |
| convergence | llama | `output_type_token_ratio` | L4 | `pairwise_continuous_alpha_raw` | -0.7789 | 11222 |
| convergence | llama | `output_type_token_ratio` | L4 | `pairwise_continuous_alpha_rank` | 0.2882 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | L4 | `pairwise_continuous_alpha_raw` | -0.1921 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | L4 | `pairwise_continuous_alpha_rank` | -0.1436 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | L4 | `pairwise_continuous_alpha_raw` | -0.9637 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | L4 | `pairwise_continuous_alpha_rank` | 0.2249 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | L4 | `pairwise_continuous_alpha_raw` | 0.8223 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | L4 | `pairwise_continuous_alpha_rank` | 0.8495 | 11222 |
| convergence | mixtral | `prompt_bytes` | L4 | `pairwise_continuous_alpha_raw` | -0.9423 | 11222 |
| convergence | mixtral | `prompt_bytes` | L4 | `pairwise_continuous_alpha_rank` | -0.0454 | 11222 |
| convergence | mixtral | `output_bytes` | L4 | `pairwise_continuous_alpha_raw` | -0.5983 | 11222 |
| convergence | mixtral | `output_bytes` | L4 | `pairwise_continuous_alpha_rank` | -0.6197 | 11222 |
| convergence | mixtral | `prompt_words` | L4 | `pairwise_continuous_alpha_raw` | -0.9400 | 11222 |
| convergence | mixtral | `prompt_words` | L4 | `pairwise_continuous_alpha_rank` | -0.0065 | 11222 |
| convergence | mixtral | `output_words` | L4 | `pairwise_continuous_alpha_raw` | -0.6282 | 11222 |
| convergence | mixtral | `output_words` | L4 | `pairwise_continuous_alpha_rank` | -0.6648 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | L4 | `pairwise_continuous_alpha_raw` | 0.5966 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | L4 | `pairwise_continuous_alpha_rank` | 0.6815 | 11222 |
| convergence | mixtral | `word_type_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.6659 | 11222 |
| convergence | mixtral | `word_type_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.8526 | 11222 |
| convergence | mixtral | `word_token_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.7732 | 11222 |
| convergence | mixtral | `word_token_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.8100 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.0288 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.8007 | 11222 |
| convergence | mixtral | `char3_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.7579 | 11222 |
| convergence | mixtral | `char3_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.7534 | 11222 |
| convergence | mixtral | `char5_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.6242 | 11222 |
| convergence | mixtral | `char5_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.8434 | 11222 |
| convergence | mixtral | `char8_coverage` | L4 | `pairwise_continuous_alpha_raw` | 0.1610 | 11222 |
| convergence | mixtral | `char8_coverage` | L4 | `pairwise_continuous_alpha_rank` | 0.8368 | 11222 |
| convergence | mixtral | `rouge_l_recall` | L4 | `pairwise_continuous_alpha_raw` | 0.4708 | 11222 |
| convergence | mixtral | `rouge_l_recall` | L4 | `pairwise_continuous_alpha_rank` | 0.8477 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | L4 | `pairwise_continuous_alpha_raw` | -0.7958 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | L4 | `pairwise_continuous_alpha_rank` | 0.2932 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | L4 | `pairwise_continuous_alpha_raw` | -0.2004 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | L4 | `pairwise_continuous_alpha_rank` | -0.1524 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | L4 | `pairwise_continuous_alpha_raw` | -0.9641 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | L4 | `pairwise_continuous_alpha_rank` | 0.2302 | 11222 |
| direct | — | `prompt_bytes` | L5 | `pairwise_continuous_alpha_raw` | -0.9848 | 11222 |
| direct | — | `prompt_bytes` | L5 | `pairwise_continuous_alpha_rank` | 0.0288 | 11222 |
| direct | — | `output_bytes` | L5 | `pairwise_continuous_alpha_raw` | -0.5942 | 11222 |
| direct | — | `output_bytes` | L5 | `pairwise_continuous_alpha_rank` | -0.9517 | 11222 |
| direct | — | `prompt_words` | L5 | `pairwise_continuous_alpha_raw` | -0.9930 | 11222 |
| direct | — | `prompt_words` | L5 | `pairwise_continuous_alpha_rank` | 0.0807 | 11222 |
| direct | — | `output_words` | L5 | `pairwise_continuous_alpha_raw` | -0.6224 | 11222 |
| direct | — | `output_words` | L5 | `pairwise_continuous_alpha_rank` | -0.9549 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | L5 | `pairwise_continuous_alpha_raw` | 0.8507 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | L5 | `pairwise_continuous_alpha_rank` | 0.9682 | 11222 |
| direct | — | `word_type_coverage` | L5 | `pairwise_continuous_alpha_raw` | 0.7180 | 11222 |
| direct | — | `word_type_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.9078 | 11222 |
| direct | — | `word_token_coverage` | L5 | `pairwise_continuous_alpha_raw` | 0.5449 | 11222 |
| direct | — | `word_token_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.9537 | 11222 |
| direct | — | `word_bigram_coverage` | L5 | `pairwise_continuous_alpha_raw` | -0.4172 | 11222 |
| direct | — | `word_bigram_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.2514 | 11222 |
| direct | — | `char3_coverage` | L5 | `pairwise_continuous_alpha_raw` | 0.5040 | 11222 |
| direct | — | `char3_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.9589 | 11222 |
| direct | — | `char5_coverage` | L5 | `pairwise_continuous_alpha_raw` | -0.1666 | 11222 |
| direct | — | `char5_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.7657 | 11222 |
| direct | — | `char8_coverage` | L5 | `pairwise_continuous_alpha_raw` | -0.4494 | 11222 |
| direct | — | `char8_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.3510 | 11222 |
| direct | — | `rouge_l_recall` | L5 | `pairwise_continuous_alpha_raw` | 0.2997 | 11222 |
| direct | — | `rouge_l_recall` | L5 | `pairwise_continuous_alpha_rank` | 0.9434 | 11222 |
| direct | — | `output_type_token_ratio` | L5 | `pairwise_continuous_alpha_raw` | -0.9167 | 11222 |
| direct | — | `output_type_token_ratio` | L5 | `pairwise_continuous_alpha_rank` | 0.7585 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | L5 | `pairwise_continuous_alpha_raw` | -0.4922 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | L5 | `pairwise_continuous_alpha_rank` | -0.5563 | 11222 |
| direct | — | `output_self_bits_per_byte` | L5 | `pairwise_continuous_alpha_raw` | -0.9586 | 11222 |
| direct | — | `output_self_bits_per_byte` | L5 | `pairwise_continuous_alpha_rank` | 0.8752 | 11222 |
| convergence | llama | `blackbox_actual_ratio` | L5 | `pairwise_continuous_alpha_raw` | 0.6653 | 11222 |
| convergence | llama | `blackbox_actual_ratio` | L5 | `pairwise_continuous_alpha_rank` | 0.6598 | 11222 |
| convergence | llama | `prompt_bytes` | L5 | `pairwise_continuous_alpha_raw` | -0.9847 | 11222 |
| convergence | llama | `prompt_bytes` | L5 | `pairwise_continuous_alpha_rank` | 0.2318 | 11222 |
| convergence | llama | `output_bytes` | L5 | `pairwise_continuous_alpha_raw` | -0.5941 | 11222 |
| convergence | llama | `output_bytes` | L5 | `pairwise_continuous_alpha_rank` | -0.5966 | 11222 |
| convergence | llama | `prompt_words` | L5 | `pairwise_continuous_alpha_raw` | -0.9927 | 11222 |
| convergence | llama | `prompt_words` | L5 | `pairwise_continuous_alpha_rank` | 0.3287 | 11222 |
| convergence | llama | `output_words` | L5 | `pairwise_continuous_alpha_raw` | -0.6224 | 11222 |
| convergence | llama | `output_words` | L5 | `pairwise_continuous_alpha_rank` | -0.6177 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | L5 | `pairwise_continuous_alpha_raw` | 0.6405 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | L5 | `pairwise_continuous_alpha_rank` | 0.6482 | 11222 |
| convergence | llama | `word_type_coverage` | L5 | `pairwise_continuous_alpha_raw` | 0.3865 | 11222 |
| convergence | llama | `word_type_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.7013 | 11222 |
| convergence | llama | `word_token_coverage` | L5 | `pairwise_continuous_alpha_raw` | 0.2246 | 11222 |
| convergence | llama | `word_token_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.6855 | 11222 |
| convergence | llama | `word_bigram_coverage` | L5 | `pairwise_continuous_alpha_raw` | -0.4386 | 11222 |
| convergence | llama | `word_bigram_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.1787 | 11222 |
| convergence | llama | `char3_coverage` | L5 | `pairwise_continuous_alpha_raw` | 0.1852 | 11222 |
| convergence | llama | `char3_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.6567 | 11222 |
| convergence | llama | `char5_coverage` | L5 | `pairwise_continuous_alpha_raw` | -0.2666 | 11222 |
| convergence | llama | `char5_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.5769 | 11222 |
| convergence | llama | `char8_coverage` | L5 | `pairwise_continuous_alpha_raw` | -0.4477 | 11222 |
| convergence | llama | `char8_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.3426 | 11222 |
| convergence | llama | `rouge_l_recall` | L5 | `pairwise_continuous_alpha_raw` | 0.0366 | 11222 |
| convergence | llama | `rouge_l_recall` | L5 | `pairwise_continuous_alpha_rank` | 0.6669 | 11222 |
| convergence | llama | `output_type_token_ratio` | L5 | `pairwise_continuous_alpha_raw` | -0.9092 | 11222 |
| convergence | llama | `output_type_token_ratio` | L5 | `pairwise_continuous_alpha_rank` | 0.5685 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | L5 | `pairwise_continuous_alpha_raw` | -0.4488 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | L5 | `pairwise_continuous_alpha_rank` | -0.4486 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | L5 | `pairwise_continuous_alpha_raw` | -0.9590 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | L5 | `pairwise_continuous_alpha_rank` | 0.5468 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | L5 | `pairwise_continuous_alpha_raw` | 0.7038 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | L5 | `pairwise_continuous_alpha_rank` | 0.7157 | 11222 |
| convergence | mixtral | `prompt_bytes` | L5 | `pairwise_continuous_alpha_raw` | -0.9847 | 11222 |
| convergence | mixtral | `prompt_bytes` | L5 | `pairwise_continuous_alpha_rank` | 0.1642 | 11222 |
| convergence | mixtral | `output_bytes` | L5 | `pairwise_continuous_alpha_raw` | -0.5941 | 11222 |
| convergence | mixtral | `output_bytes` | L5 | `pairwise_continuous_alpha_rank` | -0.6547 | 11222 |
| convergence | mixtral | `prompt_words` | L5 | `pairwise_continuous_alpha_raw` | -0.9928 | 11222 |
| convergence | mixtral | `prompt_words` | L5 | `pairwise_continuous_alpha_rank` | 0.2391 | 11222 |
| convergence | mixtral | `output_words` | L5 | `pairwise_continuous_alpha_raw` | -0.6224 | 11222 |
| convergence | mixtral | `output_words` | L5 | `pairwise_continuous_alpha_rank` | -0.6616 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | L5 | `pairwise_continuous_alpha_raw` | 0.6790 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | L5 | `pairwise_continuous_alpha_rank` | 0.6926 | 11222 |
| convergence | mixtral | `word_type_coverage` | L5 | `pairwise_continuous_alpha_raw` | 0.4349 | 11222 |
| convergence | mixtral | `word_type_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.7468 | 11222 |
| convergence | mixtral | `word_token_coverage` | L5 | `pairwise_continuous_alpha_raw` | 0.2614 | 11222 |
| convergence | mixtral | `word_token_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.7259 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | L5 | `pairwise_continuous_alpha_raw` | -0.4231 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.2522 | 11222 |
| convergence | mixtral | `char3_coverage` | L5 | `pairwise_continuous_alpha_raw` | 0.2123 | 11222 |
| convergence | mixtral | `char3_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.7086 | 11222 |
| convergence | mixtral | `char5_coverage` | L5 | `pairwise_continuous_alpha_raw` | -0.2440 | 11222 |
| convergence | mixtral | `char5_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.6336 | 11222 |
| convergence | mixtral | `char8_coverage` | L5 | `pairwise_continuous_alpha_raw` | -0.4431 | 11222 |
| convergence | mixtral | `char8_coverage` | L5 | `pairwise_continuous_alpha_rank` | 0.3773 | 11222 |
| convergence | mixtral | `rouge_l_recall` | L5 | `pairwise_continuous_alpha_raw` | 0.0627 | 11222 |
| convergence | mixtral | `rouge_l_recall` | L5 | `pairwise_continuous_alpha_rank` | 0.7088 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | L5 | `pairwise_continuous_alpha_raw` | -0.9083 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | L5 | `pairwise_continuous_alpha_rank` | 0.5515 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | L5 | `pairwise_continuous_alpha_raw` | -0.4189 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | L5 | `pairwise_continuous_alpha_rank` | -0.4239 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | L5 | `pairwise_continuous_alpha_raw` | -0.9586 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | L5 | `pairwise_continuous_alpha_rank` | 0.5951 | 11222 |
| direct | — | `prompt_bytes` | item_centered | `pairwise_continuous_alpha_raw` | 0.0003 | 56110 |
| direct | — | `prompt_bytes` | item_centered | `pairwise_continuous_alpha_rank` | 0.7557 | 56110 |
| direct | — | `output_bytes` | item_centered | `pairwise_continuous_alpha_raw` | -0.0001 | 56110 |
| direct | — | `output_bytes` | item_centered | `pairwise_continuous_alpha_rank` | -0.1985 | 56110 |
| direct | — | `prompt_words` | item_centered | `pairwise_continuous_alpha_raw` | 0.0017 | 56110 |
| direct | — | `prompt_words` | item_centered | `pairwise_continuous_alpha_rank` | 0.7502 | 56110 |
| direct | — | `output_words` | item_centered | `pairwise_continuous_alpha_raw` | -0.0004 | 56110 |
| direct | — | `output_words` | item_centered | `pairwise_continuous_alpha_rank` | -0.1670 | 56110 |
| direct | — | `prompt_to_output_byte_ratio` | item_centered | `pairwise_continuous_alpha_raw` | 0.6311 | 56110 |
| direct | — | `prompt_to_output_byte_ratio` | item_centered | `pairwise_continuous_alpha_rank` | 0.9152 | 56110 |
| direct | — | `word_type_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9343 | 56110 |
| direct | — | `word_type_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9858 | 56110 |
| direct | — | `word_token_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.8848 | 56110 |
| direct | — | `word_token_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9771 | 56110 |
| direct | — | `word_bigram_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9446 | 56110 |
| direct | — | `word_bigram_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9700 | 56110 |
| direct | — | `char3_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.8702 | 56110 |
| direct | — | `char3_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9717 | 56110 |
| direct | — | `char5_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9505 | 56110 |
| direct | — | `char5_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9858 | 56110 |
| direct | — | `char8_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9655 | 56110 |
| direct | — | `char8_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9776 | 56110 |
| direct | — | `rouge_l_recall` | item_centered | `pairwise_continuous_alpha_raw` | 0.9249 | 56110 |
| direct | — | `rouge_l_recall` | item_centered | `pairwise_continuous_alpha_rank` | 0.9793 | 56110 |
| direct | — | `output_type_token_ratio` | item_centered | `pairwise_continuous_alpha_raw` | -0.0202 | 56110 |
| direct | — | `output_type_token_ratio` | item_centered | `pairwise_continuous_alpha_rank` | -0.0095 | 56110 |
| direct | — | `output_bigram_repeat_fraction` | item_centered | `pairwise_continuous_alpha_raw` | 0.1370 | 56110 |
| direct | — | `output_bigram_repeat_fraction` | item_centered | `pairwise_continuous_alpha_rank` | 0.1584 | 56110 |
| direct | — | `output_self_bits_per_byte` | item_centered | `pairwise_continuous_alpha_raw` | 0.0507 | 56110 |
| direct | — | `output_self_bits_per_byte` | item_centered | `pairwise_continuous_alpha_rank` | 0.1000 | 56110 |
| convergence | llama | `blackbox_actual_ratio` | item_centered | `pairwise_continuous_alpha_raw` | 0.9245 | 56110 |
| convergence | llama | `blackbox_actual_ratio` | item_centered | `pairwise_continuous_alpha_rank` | 0.9654 | 56110 |
| convergence | llama | `prompt_bytes` | item_centered | `pairwise_continuous_alpha_raw` | 0.0004 | 56110 |
| convergence | llama | `prompt_bytes` | item_centered | `pairwise_continuous_alpha_rank` | 0.8010 | 56110 |
| convergence | llama | `output_bytes` | item_centered | `pairwise_continuous_alpha_raw` | -0.0001 | 56110 |
| convergence | llama | `output_bytes` | item_centered | `pairwise_continuous_alpha_rank` | -0.1945 | 56110 |
| convergence | llama | `prompt_words` | item_centered | `pairwise_continuous_alpha_raw` | 0.0024 | 56110 |
| convergence | llama | `prompt_words` | item_centered | `pairwise_continuous_alpha_rank` | 0.8007 | 56110 |
| convergence | llama | `output_words` | item_centered | `pairwise_continuous_alpha_raw` | -0.0005 | 56110 |
| convergence | llama | `output_words` | item_centered | `pairwise_continuous_alpha_rank` | -0.1635 | 56110 |
| convergence | llama | `prompt_to_output_byte_ratio` | item_centered | `pairwise_continuous_alpha_raw` | 0.7913 | 56110 |
| convergence | llama | `prompt_to_output_byte_ratio` | item_centered | `pairwise_continuous_alpha_rank` | 0.9217 | 56110 |
| convergence | llama | `word_type_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9647 | 56110 |
| convergence | llama | `word_type_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9663 | 56110 |
| convergence | llama | `word_token_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9651 | 56110 |
| convergence | llama | `word_token_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9722 | 56110 |
| convergence | llama | `word_bigram_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9118 | 56110 |
| convergence | llama | `word_bigram_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9335 | 56110 |
| convergence | llama | `char3_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9608 | 56110 |
| convergence | llama | `char3_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9698 | 56110 |
| convergence | llama | `char5_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9604 | 56110 |
| convergence | llama | `char5_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9629 | 56110 |
| convergence | llama | `char8_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9099 | 56110 |
| convergence | llama | `char8_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9329 | 56110 |
| convergence | llama | `rouge_l_recall` | item_centered | `pairwise_continuous_alpha_raw` | 0.9665 | 56110 |
| convergence | llama | `rouge_l_recall` | item_centered | `pairwise_continuous_alpha_rank` | 0.9723 | 56110 |
| convergence | llama | `output_type_token_ratio` | item_centered | `pairwise_continuous_alpha_raw` | 0.0220 | 56110 |
| convergence | llama | `output_type_token_ratio` | item_centered | `pairwise_continuous_alpha_rank` | 0.0249 | 56110 |
| convergence | llama | `output_bigram_repeat_fraction` | item_centered | `pairwise_continuous_alpha_raw` | 0.0821 | 56110 |
| convergence | llama | `output_bigram_repeat_fraction` | item_centered | `pairwise_continuous_alpha_rank` | 0.1170 | 56110 |
| convergence | llama | `output_self_bits_per_byte` | item_centered | `pairwise_continuous_alpha_raw` | 0.0849 | 56110 |
| convergence | llama | `output_self_bits_per_byte` | item_centered | `pairwise_continuous_alpha_rank` | 0.1217 | 56110 |
| convergence | mixtral | `blackbox_actual_ratio` | item_centered | `pairwise_continuous_alpha_raw` | 0.9370 | 56110 |
| convergence | mixtral | `blackbox_actual_ratio` | item_centered | `pairwise_continuous_alpha_rank` | 0.9648 | 56110 |
| convergence | mixtral | `prompt_bytes` | item_centered | `pairwise_continuous_alpha_raw` | 0.0004 | 56110 |
| convergence | mixtral | `prompt_bytes` | item_centered | `pairwise_continuous_alpha_rank` | 0.7976 | 56110 |
| convergence | mixtral | `output_bytes` | item_centered | `pairwise_continuous_alpha_raw` | -0.0001 | 56110 |
| convergence | mixtral | `output_bytes` | item_centered | `pairwise_continuous_alpha_rank` | -0.1893 | 56110 |
| convergence | mixtral | `prompt_words` | item_centered | `pairwise_continuous_alpha_raw` | 0.0023 | 56110 |
| convergence | mixtral | `prompt_words` | item_centered | `pairwise_continuous_alpha_rank` | 0.7977 | 56110 |
| convergence | mixtral | `output_words` | item_centered | `pairwise_continuous_alpha_raw` | -0.0005 | 56110 |
| convergence | mixtral | `output_words` | item_centered | `pairwise_continuous_alpha_rank` | -0.1575 | 56110 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | item_centered | `pairwise_continuous_alpha_raw` | 0.7592 | 56110 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | item_centered | `pairwise_continuous_alpha_rank` | 0.9108 | 56110 |
| convergence | mixtral | `word_type_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9641 | 56110 |
| convergence | mixtral | `word_type_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9662 | 56110 |
| convergence | mixtral | `word_token_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9544 | 56110 |
| convergence | mixtral | `word_token_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9687 | 56110 |
| convergence | mixtral | `word_bigram_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9229 | 56110 |
| convergence | mixtral | `word_bigram_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9355 | 56110 |
| convergence | mixtral | `char3_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9468 | 56110 |
| convergence | mixtral | `char3_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9650 | 56110 |
| convergence | mixtral | `char5_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9611 | 56110 |
| convergence | mixtral | `char5_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9610 | 56110 |
| convergence | mixtral | `char8_coverage` | item_centered | `pairwise_continuous_alpha_raw` | 0.9221 | 56110 |
| convergence | mixtral | `char8_coverage` | item_centered | `pairwise_continuous_alpha_rank` | 0.9338 | 56110 |
| convergence | mixtral | `rouge_l_recall` | item_centered | `pairwise_continuous_alpha_raw` | 0.9649 | 56110 |
| convergence | mixtral | `rouge_l_recall` | item_centered | `pairwise_continuous_alpha_rank` | 0.9708 | 56110 |
| convergence | mixtral | `output_type_token_ratio` | item_centered | `pairwise_continuous_alpha_raw` | 0.0092 | 56110 |
| convergence | mixtral | `output_type_token_ratio` | item_centered | `pairwise_continuous_alpha_rank` | 0.0127 | 56110 |
| convergence | mixtral | `output_bigram_repeat_fraction` | item_centered | `pairwise_continuous_alpha_raw` | 0.0934 | 56110 |
| convergence | mixtral | `output_bigram_repeat_fraction` | item_centered | `pairwise_continuous_alpha_rank` | 0.1299 | 56110 |
| convergence | mixtral | `output_self_bits_per_byte` | item_centered | `pairwise_continuous_alpha_raw` | 0.0719 | 56110 |
| convergence | mixtral | `output_self_bits_per_byte` | item_centered | `pairwise_continuous_alpha_rank` | 0.1111 | 56110 |
| convergence | llama | `blackbox_actual_ratio` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7702 | 11222 |
| convergence | llama | `blackbox_actual_ratio` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.5369 | 11222 |
| convergence | llama | `char3_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7181 | 11222 |
| convergence | llama | `char3_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.5833 | 11222 |
| convergence | llama | `char5_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7416 | 11222 |
| convergence | llama | `char5_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.4338 | 11222 |
| convergence | llama | `char8_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.6941 | 11222 |
| convergence | llama | `char8_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.1058 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | macro_within_level | `pairwise_continuous_alpha_rank` | -0.1720 | 11222 |
| convergence | llama | `output_bigram_repeat_fraction` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.5914 | 11222 |
| convergence | llama | `output_bytes` | macro_within_level | `pairwise_continuous_alpha_rank` | -0.4625 | 11222 |
| convergence | llama | `output_bytes` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.6045 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.2816 | 11222 |
| convergence | llama | `output_self_bits_per_byte` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.9495 | 11222 |
| convergence | llama | `output_type_token_ratio` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.2489 | 11222 |
| convergence | llama | `output_type_token_ratio` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.4637 | 11222 |
| convergence | llama | `output_words` | macro_within_level | `pairwise_continuous_alpha_rank` | -0.4566 | 11222 |
| convergence | llama | `output_words` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.6201 | 11222 |
| convergence | llama | `prompt_bytes` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.0867 | 11222 |
| convergence | llama | `prompt_bytes` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.7946 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.5992 | 11222 |
| convergence | llama | `prompt_to_output_byte_ratio` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.3350 | 11222 |
| convergence | llama | `prompt_words` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.1236 | 11222 |
| convergence | llama | `prompt_words` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.7898 | 11222 |
| convergence | llama | `rouge_l_recall` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.8002 | 11222 |
| convergence | llama | `rouge_l_recall` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.5189 | 11222 |
| convergence | llama | `word_bigram_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.6598 | 11222 |
| convergence | llama | `word_bigram_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.0999 | 11222 |
| convergence | llama | `word_token_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7501 | 11222 |
| convergence | llama | `word_token_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.6397 | 11222 |
| convergence | llama | `word_type_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7712 | 11222 |
| convergence | llama | `word_type_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.6606 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7603 | 11222 |
| convergence | mixtral | `blackbox_actual_ratio` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.5877 | 11222 |
| convergence | mixtral | `char3_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7079 | 11222 |
| convergence | mixtral | `char3_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.5335 | 11222 |
| convergence | mixtral | `char5_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7284 | 11222 |
| convergence | mixtral | `char5_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.4584 | 11222 |
| convergence | mixtral | `char8_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.6745 | 11222 |
| convergence | mixtral | `char8_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.1240 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | macro_within_level | `pairwise_continuous_alpha_rank` | -0.1881 | 11222 |
| convergence | mixtral | `output_bigram_repeat_fraction` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.5820 | 11222 |
| convergence | mixtral | `output_bytes` | macro_within_level | `pairwise_continuous_alpha_rank` | -0.4827 | 11222 |
| convergence | mixtral | `output_bytes` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.6045 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.3060 | 11222 |
| convergence | mixtral | `output_self_bits_per_byte` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.9499 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.2602 | 11222 |
| convergence | mixtral | `output_type_token_ratio` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.4856 | 11222 |
| convergence | mixtral | `output_words` | macro_within_level | `pairwise_continuous_alpha_rank` | -0.4703 | 11222 |
| convergence | mixtral | `output_words` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.6201 | 11222 |
| convergence | mixtral | `prompt_bytes` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.0441 | 11222 |
| convergence | mixtral | `prompt_bytes` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.7946 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.5901 | 11222 |
| convergence | mixtral | `prompt_to_output_byte_ratio` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.3152 | 11222 |
| convergence | mixtral | `prompt_words` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.0800 | 11222 |
| convergence | mixtral | `prompt_words` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.7898 | 11222 |
| convergence | mixtral | `rouge_l_recall` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7866 | 11222 |
| convergence | mixtral | `rouge_l_recall` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.5416 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.6495 | 11222 |
| convergence | mixtral | `word_bigram_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.1177 | 11222 |
| convergence | mixtral | `word_token_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7351 | 11222 |
| convergence | mixtral | `word_token_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.6007 | 11222 |
| convergence | mixtral | `word_type_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7603 | 11222 |
| convergence | mixtral | `word_type_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.6504 | 11222 |
| direct | — | `char3_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.9151 | 11222 |
| direct | — | `char3_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.4673 | 11222 |
| direct | — | `char5_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.9170 | 11222 |
| direct | — | `char5_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.6337 | 11222 |
| direct | — | `char8_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.8283 | 11222 |
| direct | — | `char8_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.4309 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | macro_within_level | `pairwise_continuous_alpha_rank` | -0.1735 | 11222 |
| direct | — | `output_bigram_repeat_fraction` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.5501 | 11222 |
| direct | — | `output_bytes` | macro_within_level | `pairwise_continuous_alpha_rank` | -0.6373 | 11222 |
| direct | — | `output_bytes` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.6045 | 11222 |
| direct | — | `output_self_bits_per_byte` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.3589 | 11222 |
| direct | — | `output_self_bits_per_byte` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.9523 | 11222 |
| direct | — | `output_type_token_ratio` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.3026 | 11222 |
| direct | — | `output_type_token_ratio` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.5706 | 11222 |
| direct | — | `output_words` | macro_within_level | `pairwise_continuous_alpha_rank` | -0.6458 | 11222 |
| direct | — | `output_words` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.6202 | 11222 |
| direct | — | `prompt_bytes` | macro_within_level | `pairwise_continuous_alpha_rank` | -0.0308 | 11222 |
| direct | — | `prompt_bytes` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.7946 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.8123 | 11222 |
| direct | — | `prompt_to_output_byte_ratio` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.2710 | 11222 |
| direct | — | `prompt_words` | macro_within_level | `pairwise_continuous_alpha_rank` | -0.0281 | 11222 |
| direct | — | `prompt_words` | macro_within_level | `pairwise_continuous_alpha_raw` | -0.7900 | 11222 |
| direct | — | `rouge_l_recall` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.9279 | 11222 |
| direct | — | `rouge_l_recall` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.6221 | 11222 |
| direct | — | `word_bigram_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.7772 | 11222 |
| direct | — | `word_bigram_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.3808 | 11222 |
| direct | — | `word_token_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.9260 | 11222 |
| direct | — | `word_token_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.5404 | 11222 |
| direct | — | `word_type_coverage` | macro_within_level | `pairwise_continuous_alpha_rank` | 0.9249 | 11222 |
| direct | — | `word_type_coverage` | macro_within_level | `pairwise_continuous_alpha_raw` | 0.5779 | 11222 |

# Appendix C — Tie and undefined diagnostics

| Score | Distinct values | Tied observations | Tied fraction | Largest tie block | Pooled constant | Constant level cells |
|---|---:|---:|---:|---:|---|---|
| `blackbox_actual_ratio` | 55210 | 1702 | 0.0303 | 12 | False | none |
| `char3_coverage` | 53007 | 5483 | 0.0977 | 20 | False | none |
| `char5_coverage` | 52030 | 6926 | 0.1234 | 15 | False | none |
| `char8_coverage` | 49494 | 9419 | 0.1679 | 2711 | False | none |
| `output_bigram_repeat_fraction` | 18911 | 45145 | 0.8046 | 1676 | False | none |
| `output_bytes` | 7093 | 54255 | 0.9669 | 48 | False | none |
| `output_self_bits_per_byte` | 54084 | 3668 | 0.0654 | 28 | False | none |
| `output_type_token_ratio` | 23304 | 42868 | 0.7640 | 242 | False | none |
| `output_words` | 1535 | 55880 | 0.9959 | 209 | False | none |
| `phi_actual_llama` | 56105 | 10 | 0.0002 | 2 | False | none |
| `phi_actual_mixtral` | 56105 | 10 | 0.0002 | 2 | False | none |
| `prompt_bytes` | 2388 | 56038 | 0.9987 | 1082 | False | none |
| `prompt_to_output_byte_ratio` | 53103 | 5435 | 0.0969 | 40 | False | none |
| `prompt_words` | 617 | 56107 | 0.9999 | 8925 | False | none |
| `rouge_l_recall` | 28649 | 36951 | 0.6585 | 103 | False | none |
| `word_bigram_coverage` | 26615 | 38583 | 0.6876 | 5027 | False | none |
| `word_token_coverage` | 29518 | 36121 | 0.6438 | 114 | False | none |
| `word_type_coverage` | 17821 | 47336 | 0.8436 | 214 | False | none |

## Bootstrap undefined replicates

| Metric ID | Finite | Undefined | Effective n all draws | Effective n finite draws |
|---|---:|---:|---|---|
| `subgroup|domain|news|convergence|llama|prompt_words|macro_within_level|alpha_z` | 0 | 2000 | 2544–3177 | NA |
| `subgroup|domain|news|convergence|llama|prompt_words|macro_within_level|rho` | 0 | 2000 | 2544–3177 | NA |
| `subgroup|domain|news|convergence|mixtral|prompt_words|macro_within_level|alpha_z` | 0 | 2000 | 2544–3177 | NA |
| `subgroup|domain|news|convergence|mixtral|prompt_words|macro_within_level|rho` | 0 | 2000 | 2544–3177 | NA |
| `subgroup|domain|news|direct|prompt_words|macro_within_level|alpha_z` | 0 | 2000 | 2544–3177 | NA |
| `subgroup|domain|news|direct|prompt_words|macro_within_level|rho` | 0 | 2000 | 2544–3177 | NA |

# Appendix D — Feature definitions

- Unicode normalization: NFC
- Case normalization: Unicode casefold
- Whitespace normalization: collapse Unicode whitespace to one ASCII space and strip
- Word-token regex: `\w+ with Python Unicode semantics`
- Byte encoding: UTF-8 with errors=replace
- Coverage orientation: fraction of output units recoverable from prompt units
- Coverage numerator: sum over output-unit types of min(output count, prompt count)
- Coverage denominator: number of output units
- Zero denominator: 0.0
- ROUGE-L: exact Hunt-Szymanski word-token LCS length divided by output-token count
- Empty-string handling: permitted by feature functions and mapped through explicit zero-denominator rules; canonical cohort requires non-empty actual text

| Feature | Frozen definition |
|---|---|
| `prompt_bytes` | UTF-8 byte length of actual prompt |
| `output_bytes` | UTF-8 byte length of actual output |
| `prompt_words` | Number of normalized prompt word tokens |
| `output_words` | Number of normalized output word tokens |
| `prompt_to_output_byte_ratio` | prompt bytes / output bytes |
| `word_type_coverage` | Distinct output word types present in prompt / distinct output word types |
| `word_token_coverage` | Multiset output word tokens recoverable from prompt / output word tokens |
| `word_bigram_coverage` | Multiset output word bigrams recoverable from prompt / output word bigrams |
| `char3_coverage` / `char5_coverage` / `char8_coverage` | Multiset normalized output character n-grams recoverable from prompt / output n-grams |
| `rouge_l_recall` | exact Hunt-Szymanski word-token LCS length divided by output-token count |
| `output_type_token_ratio` | distinct output word tokens / output word tokens |
| `output_bigram_repeat_fraction` | 1 - distinct output word bigrams / output word bigrams |
| `output_self_bits_per_byte` | mean calibrated zlib-9/bz2-9/lzma-preset-9 output-only bits / UTF-8 output bytes |
