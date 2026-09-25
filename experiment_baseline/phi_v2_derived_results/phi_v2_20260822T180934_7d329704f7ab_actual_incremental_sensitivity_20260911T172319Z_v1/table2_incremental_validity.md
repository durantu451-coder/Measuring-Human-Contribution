# Table 2. Cross-fitted incremental validity

Primary rows use source-grouped nested-CV OOF predictions. All agreement cells pair rho with `pairwise_continuous_alpha_z`.

| Learner | Target | Predictor set | Status | Macro rho / alpha_z | Item-centered rho / alpha_z | OOF R2 / MAE (auxiliary) |
|---|---|---|---|---:|---:|---:|
| hgb | phi_actual_llama | AUX-strongest-single | auxiliary frozen strongest-single | 0.797541 / 0.805630 | 0.978839 / 0.982601 | 0.951532 / 0.041468 |
| hgb | phi_actual_llama | G-only | primary | 0.193353 / 0.172139 | 0.758340 / 0.770226 | 0.519464 / 0.140534 |
| hgb | phi_actual_llama | H | primary | 0.859487 / 0.874379 | 0.987361 / 0.989655 | 0.969527 / 0.032824 |
| hgb | phi_actual_llama | H+R | primary | 0.860078 / 0.874804 | 0.987344 / 0.989679 | 0.969780 / 0.032723 |
| hgb | phi_actual_llama | L | primary | 0.663014 / 0.718795 | 0.945953 / 0.946077 | 0.875900 / 0.064207 |
| hgb | phi_actual_llama | O | primary | 0.835834 / 0.848291 | 0.984764 / 0.987826 | 0.964376 / 0.035868 |
| hgb | phi_actual_llama | R-only | primary | 0.768871 / 0.784931 | 0.966231 / 0.969576 | 0.916523 / 0.053218 |
| hgb | phi_actual_mixtral | AUX-strongest-single | auxiliary frozen strongest-single | 0.784818 / 0.800852 | 0.977110 / 0.980921 | 0.944246 / 0.042143 |
| hgb | phi_actual_mixtral | G-only | primary | 0.181463 / 0.156044 | 0.761960 / 0.773714 | 0.512545 / 0.136570 |
| hgb | phi_actual_mixtral | H | primary | 0.855125 / 0.869771 | 0.985414 / 0.987409 | 0.963690 / 0.033672 |
| hgb | phi_actual_mixtral | H+R | primary | 0.856583 / 0.870433 | 0.985497 / 0.987534 | 0.964149 / 0.033534 |
| hgb | phi_actual_mixtral | L | primary | 0.646690 / 0.694572 | 0.937496 / 0.931260 | 0.847489 / 0.067568 |
| hgb | phi_actual_mixtral | O | primary | 0.834636 / 0.848307 | 0.983141 / 0.985774 | 0.958083 / 0.036523 |
| hgb | phi_actual_mixtral | R-only | primary | 0.758749 / 0.773325 | 0.965477 / 0.969618 | 0.912780 / 0.051394 |
| ridge | phi_actual_llama | AUX-strongest-single | auxiliary frozen strongest-single | 0.799963 / 0.798992 | 0.972319 / 0.969106 | 0.926773 / 0.053070 |
| ridge | phi_actual_llama | G-only | primary | 0.212735 / 0.195735 | 0.728198 / 0.705797 | 0.404051 / 0.164502 |
| ridge | phi_actual_llama | H | primary | 0.802997 / 0.825886 | 0.982979 / 0.985888 | 0.959309 / 0.038539 |
| ridge | phi_actual_llama | H+R | primary | 0.804550 / 0.827903 | 0.983127 / 0.986011 | 0.959610 / 0.038427 |
| ridge | phi_actual_llama | L | primary | 0.549913 / 0.643788 | 0.924223 / 0.929978 | 0.843756 / 0.071861 |
| ridge | phi_actual_llama | O | primary | 0.805582 / 0.819543 | 0.981445 / 0.984424 | 0.956875 / 0.039921 |
| ridge | phi_actual_llama | R-only | primary | 0.770158 / 0.791824 | 0.965366 / 0.959933 | 0.899166 / 0.059516 |
| ridge | phi_actual_mixtral | AUX-strongest-single | auxiliary frozen strongest-single | 0.786497 / 0.796181 | 0.970818 / 0.970906 | 0.925948 / 0.049727 |
| ridge | phi_actual_mixtral | G-only | primary | 0.183511 / 0.166191 | 0.734759 / 0.714139 | 0.399603 / 0.157845 |
| ridge | phi_actual_mixtral | H | primary | 0.804888 / 0.825099 | 0.980781 / 0.983308 | 0.953269 / 0.038839 |
| ridge | phi_actual_mixtral | H+R | primary | 0.808375 / 0.828696 | 0.981132 / 0.983710 | 0.954002 / 0.038694 |
| ridge | phi_actual_mixtral | L | primary | 0.564101 / 0.632492 | 0.913528 / 0.912164 | 0.810516 / 0.074746 |
| ridge | phi_actual_mixtral | O | primary | 0.806238 / 0.820611 | 0.979260 / 0.981825 | 0.949924 / 0.040400 |
| ridge | phi_actual_mixtral | R-only | primary | 0.760288 / 0.781634 | 0.964839 / 0.963577 | 0.901921 / 0.054397 |

## Direct paired OOF contrasts

| Contrast ID | Point | 95% paired cluster-bootstrap CI |
|---|---:|---:|
| incremental_delta|hgb|phi_actual_llama|H+R-minus-H|item_centered|pairwise_continuous_alpha_z | 0.000025 | [-0.000027, 0.000080] |
| incremental_delta|hgb|phi_actual_llama|H+R-minus-H|item_centered|rho | -0.000017 | [-0.000082, 0.000049] |
| incremental_delta|hgb|phi_actual_llama|H+R-minus-H|macro_within_level|pairwise_continuous_alpha_z | 0.000425 | [-0.000232, 0.001023] |
| incremental_delta|hgb|phi_actual_llama|H+R-minus-H|macro_within_level|rho | 0.000591 | [-0.000028, 0.001167] |
| incremental_delta|hgb|phi_actual_llama|H-minus-L|item_centered|pairwise_continuous_alpha_z | 0.043577 | [0.042642, 0.044545] |
| incremental_delta|hgb|phi_actual_llama|H-minus-L|item_centered|rho | 0.041408 | [0.040509, 0.042343] |
| incremental_delta|hgb|phi_actual_llama|H-minus-L|macro_within_level|pairwise_continuous_alpha_z | 0.155584 | [0.150226, 0.161000] |
| incremental_delta|hgb|phi_actual_llama|H-minus-L|macro_within_level|rho | 0.196473 | [0.191125, 0.202087] |
| incremental_delta|hgb|phi_actual_llama|H-minus-O|item_centered|pairwise_continuous_alpha_z | 0.001828 | [0.001678, 0.001979] |
| incremental_delta|hgb|phi_actual_llama|H-minus-O|item_centered|rho | 0.002597 | [0.002408, 0.002781] |
| incremental_delta|hgb|phi_actual_llama|H-minus-O|macro_within_level|pairwise_continuous_alpha_z | 0.026088 | [0.023686, 0.028406] |
| incremental_delta|hgb|phi_actual_llama|H-minus-O|macro_within_level|rho | 0.023652 | [0.021757, 0.025518] |
| incremental_delta|hgb|phi_actual_llama|R-only-minus-AUX-strongest-single|item_centered|pairwise_continuous_alpha_z | -0.013026 | [-0.014069, -0.012145] |
| incremental_delta|hgb|phi_actual_llama|R-only-minus-AUX-strongest-single|item_centered|rho | -0.012608 | [-0.013638, -0.011754] |
| incremental_delta|hgb|phi_actual_llama|R-only-minus-AUX-strongest-single|macro_within_level|pairwise_continuous_alpha_z | -0.020699 | [-0.026243, -0.015870] |
| incremental_delta|hgb|phi_actual_llama|R-only-minus-AUX-strongest-single|macro_within_level|rho | -0.028670 | [-0.032194, -0.025119] |
| incremental_delta|hgb|phi_actual_llama|R-only-minus-G-only|item_centered|pairwise_continuous_alpha_z | 0.199350 | [0.193813, 0.204785] |
| incremental_delta|hgb|phi_actual_llama|R-only-minus-G-only|item_centered|rho | 0.207891 | [0.200402, 0.214870] |
| incremental_delta|hgb|phi_actual_llama|R-only-minus-G-only|macro_within_level|pairwise_continuous_alpha_z | 0.612792 | [0.600972, 0.623943] |
| incremental_delta|hgb|phi_actual_llama|R-only-minus-G-only|macro_within_level|rho | 0.575518 | [0.564176, 0.586410] |
| incremental_delta|hgb|phi_actual_mixtral|H+R-minus-H|item_centered|pairwise_continuous_alpha_z | 0.000126 | [0.000040, 0.000220] |
| incremental_delta|hgb|phi_actual_mixtral|H+R-minus-H|item_centered|rho | 0.000083 | [0.000011, 0.000161] |
| incremental_delta|hgb|phi_actual_mixtral|H+R-minus-H|macro_within_level|pairwise_continuous_alpha_z | 0.000662 | [0.000089, 0.001232] |
| incremental_delta|hgb|phi_actual_mixtral|H+R-minus-H|macro_within_level|rho | 0.001458 | [0.000779, 0.002121] |
| incremental_delta|hgb|phi_actual_mixtral|H-minus-L|item_centered|pairwise_continuous_alpha_z | 0.056148 | [0.054937, 0.057347] |
| incremental_delta|hgb|phi_actual_mixtral|H-minus-L|item_centered|rho | 0.047919 | [0.046809, 0.048992] |
| incremental_delta|hgb|phi_actual_mixtral|H-minus-L|macro_within_level|pairwise_continuous_alpha_z | 0.175198 | [0.169409, 0.181123] |
| incremental_delta|hgb|phi_actual_mixtral|H-minus-L|macro_within_level|rho | 0.208435 | [0.202642, 0.214330] |
| incremental_delta|hgb|phi_actual_mixtral|H-minus-O|item_centered|pairwise_continuous_alpha_z | 0.001635 | [0.001460, 0.001806] |
| incremental_delta|hgb|phi_actual_mixtral|H-minus-O|item_centered|rho | 0.002274 | [0.002074, 0.002461] |
| incremental_delta|hgb|phi_actual_mixtral|H-minus-O|macro_within_level|pairwise_continuous_alpha_z | 0.021464 | [0.019794, 0.023121] |
| incremental_delta|hgb|phi_actual_mixtral|H-minus-O|macro_within_level|rho | 0.020489 | [0.018635, 0.022285] |
| incremental_delta|hgb|phi_actual_mixtral|R-only-minus-AUX-strongest-single|item_centered|pairwise_continuous_alpha_z | -0.011303 | [-0.012369, -0.010444] |
| incremental_delta|hgb|phi_actual_mixtral|R-only-minus-AUX-strongest-single|item_centered|rho | -0.011633 | [-0.012777, -0.010746] |
| incremental_delta|hgb|phi_actual_mixtral|R-only-minus-AUX-strongest-single|macro_within_level|pairwise_continuous_alpha_z | -0.027528 | [-0.032505, -0.023109] |
| incremental_delta|hgb|phi_actual_mixtral|R-only-minus-AUX-strongest-single|macro_within_level|rho | -0.026069 | [-0.029700, -0.022524] |
| incremental_delta|hgb|phi_actual_mixtral|R-only-minus-G-only|item_centered|pairwise_continuous_alpha_z | 0.195905 | [0.190592, 0.201109] |
| incremental_delta|hgb|phi_actual_mixtral|R-only-minus-G-only|item_centered|rho | 0.203516 | [0.196469, 0.210374] |
| incremental_delta|hgb|phi_actual_mixtral|R-only-minus-G-only|macro_within_level|pairwise_continuous_alpha_z | 0.617280 | [0.605408, 0.628454] |
| incremental_delta|hgb|phi_actual_mixtral|R-only-minus-G-only|macro_within_level|rho | 0.577286 | [0.565618, 0.588431] |
| incremental_delta|ridge|phi_actual_llama|H+R-minus-H|item_centered|pairwise_continuous_alpha_z | 0.000123 | [0.000064, 0.000176] |
| incremental_delta|ridge|phi_actual_llama|H+R-minus-H|item_centered|rho | 0.000149 | [0.000084, 0.000204] |
| incremental_delta|ridge|phi_actual_llama|H+R-minus-H|macro_within_level|pairwise_continuous_alpha_z | 0.002017 | [0.001497, 0.002504] |
| incremental_delta|ridge|phi_actual_llama|H+R-minus-H|macro_within_level|rho | 0.001553 | [0.000942, 0.002070] |
| incremental_delta|ridge|phi_actual_llama|H-minus-L|item_centered|pairwise_continuous_alpha_z | 0.055911 | [0.054539, 0.057259] |
| incremental_delta|ridge|phi_actual_llama|H-minus-L|item_centered|rho | 0.058755 | [0.057546, 0.059957] |
| incremental_delta|ridge|phi_actual_llama|H-minus-L|macro_within_level|pairwise_continuous_alpha_z | 0.182098 | [0.174229, 0.190388] |
| incremental_delta|ridge|phi_actual_llama|H-minus-L|macro_within_level|rho | 0.253085 | [0.247326, 0.259525] |
| incremental_delta|ridge|phi_actual_llama|H-minus-O|item_centered|pairwise_continuous_alpha_z | 0.001465 | [0.001361, 0.001571] |
| incremental_delta|ridge|phi_actual_llama|H-minus-O|item_centered|rho | 0.001533 | [0.001394, 0.001674] |
| incremental_delta|ridge|phi_actual_llama|H-minus-O|macro_within_level|pairwise_continuous_alpha_z | 0.006344 | [0.004113, 0.008534] |
| incremental_delta|ridge|phi_actual_llama|H-minus-O|macro_within_level|rho | -0.002585 | [-0.003840, -0.001281] |
| incremental_delta|ridge|phi_actual_llama|R-only-minus-AUX-strongest-single|item_centered|pairwise_continuous_alpha_z | -0.009174 | [-0.010226, -0.008177] |
| incremental_delta|ridge|phi_actual_llama|R-only-minus-AUX-strongest-single|item_centered|rho | -0.006953 | [-0.008024, -0.006010] |
| incremental_delta|ridge|phi_actual_llama|R-only-minus-AUX-strongest-single|macro_within_level|pairwise_continuous_alpha_z | -0.007168 | [-0.012751, -0.002221] |
| incremental_delta|ridge|phi_actual_llama|R-only-minus-AUX-strongest-single|macro_within_level|rho | -0.029806 | [-0.033213, -0.026495] |
| incremental_delta|ridge|phi_actual_llama|R-only-minus-G-only|item_centered|pairwise_continuous_alpha_z | 0.254135 | [0.247006, 0.261073] |
| incremental_delta|ridge|phi_actual_llama|R-only-minus-G-only|item_centered|rho | 0.237168 | [0.229492, 0.244877] |
| incremental_delta|ridge|phi_actual_llama|R-only-minus-G-only|macro_within_level|pairwise_continuous_alpha_z | 0.596090 | [0.583561, 0.608174] |
| incremental_delta|ridge|phi_actual_llama|R-only-minus-G-only|macro_within_level|rho | 0.557423 | [0.544538, 0.569670] |
| incremental_delta|ridge|phi_actual_mixtral|H+R-minus-H|item_centered|pairwise_continuous_alpha_z | 0.000401 | [0.000262, 0.000540] |
| incremental_delta|ridge|phi_actual_mixtral|H+R-minus-H|item_centered|rho | 0.000351 | [0.000222, 0.000458] |
| incremental_delta|ridge|phi_actual_mixtral|H+R-minus-H|macro_within_level|pairwise_continuous_alpha_z | 0.003598 | [0.002697, 0.004380] |
| incremental_delta|ridge|phi_actual_mixtral|H+R-minus-H|macro_within_level|rho | 0.003487 | [0.002518, 0.004328] |
| incremental_delta|ridge|phi_actual_mixtral|H-minus-L|item_centered|pairwise_continuous_alpha_z | 0.071144 | [0.069458, 0.072833] |
| incremental_delta|ridge|phi_actual_mixtral|H-minus-L|item_centered|rho | 0.067254 | [0.065855, 0.068635] |
| incremental_delta|ridge|phi_actual_mixtral|H-minus-L|macro_within_level|pairwise_continuous_alpha_z | 0.192607 | [0.184775, 0.200894] |
| incremental_delta|ridge|phi_actual_mixtral|H-minus-L|macro_within_level|rho | 0.240786 | [0.234235, 0.247688] |
| incremental_delta|ridge|phi_actual_mixtral|H-minus-O|item_centered|pairwise_continuous_alpha_z | 0.001483 | [0.001341, 0.001622] |
| incremental_delta|ridge|phi_actual_mixtral|H-minus-O|item_centered|rho | 0.001522 | [0.001366, 0.001675] |
| incremental_delta|ridge|phi_actual_mixtral|H-minus-O|macro_within_level|pairwise_continuous_alpha_z | 0.004488 | [0.002751, 0.006314] |
| incremental_delta|ridge|phi_actual_mixtral|H-minus-O|macro_within_level|rho | -0.001351 | [-0.002508, -0.000155] |
| incremental_delta|ridge|phi_actual_mixtral|R-only-minus-AUX-strongest-single|item_centered|pairwise_continuous_alpha_z | -0.007329 | [-0.008395, -0.006335] |
| incremental_delta|ridge|phi_actual_mixtral|R-only-minus-AUX-strongest-single|item_centered|rho | -0.005979 | [-0.007128, -0.004990] |
| incremental_delta|ridge|phi_actual_mixtral|R-only-minus-AUX-strongest-single|macro_within_level|pairwise_continuous_alpha_z | -0.014546 | [-0.019225, -0.010206] |
| incremental_delta|ridge|phi_actual_mixtral|R-only-minus-AUX-strongest-single|macro_within_level|rho | -0.026209 | [-0.029900, -0.022667] |
| incremental_delta|ridge|phi_actual_mixtral|R-only-minus-G-only|item_centered|pairwise_continuous_alpha_z | 0.249438 | [0.242546, 0.255981] |
| incremental_delta|ridge|phi_actual_mixtral|R-only-minus-G-only|item_centered|rho | 0.230079 | [0.223051, 0.237080] |
| incremental_delta|ridge|phi_actual_mixtral|R-only-minus-G-only|macro_within_level|pairwise_continuous_alpha_z | 0.615443 | [0.603055, 0.626955] |
| incremental_delta|ridge|phi_actual_mixtral|R-only-minus-G-only|macro_within_level|rho | 0.576778 | [0.564230, 0.589049] |
