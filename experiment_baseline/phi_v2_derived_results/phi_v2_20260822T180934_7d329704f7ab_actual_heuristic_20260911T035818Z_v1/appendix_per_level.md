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
