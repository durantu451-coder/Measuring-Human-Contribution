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
