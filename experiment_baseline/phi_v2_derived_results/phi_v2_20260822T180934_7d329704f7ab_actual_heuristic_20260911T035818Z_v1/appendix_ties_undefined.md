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
