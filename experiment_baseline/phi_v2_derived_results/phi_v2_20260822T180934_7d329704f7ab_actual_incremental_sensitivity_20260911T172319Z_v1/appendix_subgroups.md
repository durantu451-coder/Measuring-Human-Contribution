# Appendix: complete subgroup and secondary inventory

## C_y_bits

### Reference: consensus_global_z
- per_level:
  - L1: rho=-0.191236; pairwise_continuous_alpha_z=-0.178716; n=11222; reason=None
  - L2: rho=-0.179258; pairwise_continuous_alpha_z=-0.101902; n=11222; reason=None
  - L3: rho=-0.746318; pairwise_continuous_alpha_z=-0.721449; n=11222; reason=None
  - L4: rho=-0.682344; pairwise_continuous_alpha_z=-0.634386; n=11222; reason=None
  - L5: rho=-0.675965; pairwise_continuous_alpha_z=-0.632487; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.664465; pairwise_continuous_alpha_z=-0.595106; n=14685
  - news: rho=0.437698; pairwise_continuous_alpha_z=0.425340; n=14280
  - patent: rho=-0.581443; pairwise_continuous_alpha_z=-0.531672; n=13800
  - poetry: rho=-0.366093; pairwise_continuous_alpha_z=-0.377267; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.284405; pairwise_continuous_alpha_z=-0.232907; n=9460
  - claude-sonnet-5: rho=-0.412213; pairwise_continuous_alpha_z=-0.459339; n=11600
  - gemini-3.6-flash: rho=-0.273948; pairwise_continuous_alpha_z=-0.306318; n=11200
  - gpt-5.5: rho=-0.124705; pairwise_continuous_alpha_z=-0.109621; n=12230
  - gpt-5.6-sol: rho=-0.065259; pairwise_continuous_alpha_z=-0.034339; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=-0.189872; pairwise_continuous_alpha_z=-0.173699; n=11222; reason=None
  - L2: rho=-0.179835; pairwise_continuous_alpha_z=-0.106267; n=11222; reason=None
  - L3: rho=-0.746951; pairwise_continuous_alpha_z=-0.730886; n=11222; reason=None
  - L4: rho=-0.682135; pairwise_continuous_alpha_z=-0.668327; n=11222; reason=None
  - L5: rho=-0.679355; pairwise_continuous_alpha_z=-0.667078; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.664494; pairwise_continuous_alpha_z=-0.609446; n=14685
  - news: rho=0.437730; pairwise_continuous_alpha_z=0.403905; n=14280
  - patent: rho=-0.580737; pairwise_continuous_alpha_z=-0.510609; n=13800
  - poetry: rho=-0.365256; pairwise_continuous_alpha_z=-0.374148; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.283797; pairwise_continuous_alpha_z=-0.220465; n=9460
  - claude-sonnet-5: rho=-0.412053; pairwise_continuous_alpha_z=-0.423963; n=11600
  - gemini-3.6-flash: rho=-0.274384; pairwise_continuous_alpha_z=-0.347507; n=11200
  - gpt-5.5: rho=-0.124117; pairwise_continuous_alpha_z=-0.106575; n=12230
  - gpt-5.6-sol: rho=-0.064421; pairwise_continuous_alpha_z=-0.054954; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.134064; n=56110; reason=None
  - macro_within_level: 0.011591; n=11222; reason=None
  - item_centered: 0.164784; n=56110; reason=None
  - level:L1: 0.206685; n=11222; reason=None
  - level:L2: 0.243716; n=11222; reason=None
  - level:L3: -0.153929; n=11222; reason=None
  - level:L4: -0.101556; n=11222; reason=None
  - level:L5: -0.136959; n=11222; reason=None
  - by_domain:arxiv: -0.065510; n=14685; reason=None
  - by_domain:news: 0.613699; n=14280; reason=None
  - by_domain:patent: -0.023603; n=13800; reason=None
  - by_domain:poetry: 0.079182; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.175138; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.024783; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.125878; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.257535; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.306602; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=-0.180770; pairwise_continuous_alpha_z=-0.168373; n=11222; reason=None
  - L2: rho=-0.204401; pairwise_continuous_alpha_z=-0.100063; n=11222; reason=None
  - L3: rho=-0.712645; pairwise_continuous_alpha_z=-0.693421; n=11222; reason=None
  - L4: rho=-0.666697; pairwise_continuous_alpha_z=-0.617048; n=11222; reason=None
  - L5: rho=-0.599471; pairwise_continuous_alpha_z=-0.579124; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.661195; pairwise_continuous_alpha_z=-0.595410; n=14685
  - news: rho=0.443621; pairwise_continuous_alpha_z=0.431691; n=14280
  - patent: rho=-0.576899; pairwise_continuous_alpha_z=-0.531778; n=13800
  - poetry: rho=-0.363623; pairwise_continuous_alpha_z=-0.377242; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.279351; pairwise_continuous_alpha_z=-0.233897; n=9460
  - claude-sonnet-5: rho=-0.412731; pairwise_continuous_alpha_z=-0.460282; n=11600
  - gemini-3.6-flash: rho=-0.278976; pairwise_continuous_alpha_z=-0.305414; n=11200
  - gpt-5.5: rho=-0.134996; pairwise_continuous_alpha_z=-0.115659; n=12230
  - gpt-5.6-sol: rho=-0.062685; pairwise_continuous_alpha_z=-0.032451; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=-0.202461; pairwise_continuous_alpha_z=-0.186493; n=11222; reason=None
  - L2: rho=-0.149885; pairwise_continuous_alpha_z=-0.100216; n=11222; reason=None
  - L3: rho=-0.768524; pairwise_continuous_alpha_z=-0.739069; n=11222; reason=None
  - L4: rho=-0.682503; pairwise_continuous_alpha_z=-0.636102; n=11222; reason=None
  - L5: rho=-0.658225; pairwise_continuous_alpha_z=-0.614026; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.663984; pairwise_continuous_alpha_z=-0.592074; n=14685
  - news: rho=0.431470; pairwise_continuous_alpha_z=0.417342; n=14280
  - patent: rho=-0.583866; pairwise_continuous_alpha_z=-0.528873; n=13800
  - poetry: rho=-0.362712; pairwise_continuous_alpha_z=-0.375481; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.285550; pairwise_continuous_alpha_z=-0.230772; n=9460
  - claude-sonnet-5: rho=-0.412150; pairwise_continuous_alpha_z=-0.456273; n=11600
  - gemini-3.6-flash: rho=-0.266648; pairwise_continuous_alpha_z=-0.305466; n=11200
  - gpt-5.5: rho=-0.116432; pairwise_continuous_alpha_z=-0.103145; n=12230
  - gpt-5.6-sol: rho=-0.064908; pairwise_continuous_alpha_z=-0.036013; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=-0.469475; pairwise_continuous_alpha_z=-0.406025; n=14685
  - news: rho=0.636763; pairwise_continuous_alpha_z=0.614622; n=14280
  - patent: rho=-0.390531; pairwise_continuous_alpha_z=-0.355025; n=13800
  - poetry: rho=-0.119074; pairwise_continuous_alpha_z=-0.118192; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.256262; pairwise_continuous_alpha_z=-0.193799; n=9460
  - claude-sonnet-5: rho=-0.360747; pairwise_continuous_alpha_z=-0.342162; n=11600
  - gemini-3.6-flash: rho=-0.106279; pairwise_continuous_alpha_z=-0.174911; n=11200
  - gpt-5.5: rho=-0.043236; pairwise_continuous_alpha_z=0.006048; n=12230
  - gpt-5.6-sol: rho=0.126601; pairwise_continuous_alpha_z=0.138313; n=11620
- per-item ordinal: mean Spearman=-0.115671; finite Spearman items=11222; mean Kendall tau-b=-0.122901; finite tau-b items=11222; strict monotonic=41/11222 (0.003654); nonstrict monotonic=43/11222 (0.003832)

## G_raw_bits

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.375548; pairwise_continuous_alpha_z=0.333495; n=11222; reason=None
  - L2: rho=0.159946; pairwise_continuous_alpha_z=0.130491; n=11222; reason=None
  - L3: rho=0.205648; pairwise_continuous_alpha_z=0.196149; n=11222; reason=None
  - L4: rho=0.159037; pairwise_continuous_alpha_z=0.174629; n=11222; reason=None
  - L5: rho=0.105260; pairwise_continuous_alpha_z=0.081404; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.478980; pairwise_continuous_alpha_z=0.494907; n=14685
  - news: rho=0.932219; pairwise_continuous_alpha_z=0.919708; n=14280
  - patent: rho=0.632590; pairwise_continuous_alpha_z=0.661248; n=13800
  - poetry: rho=0.797574; pairwise_continuous_alpha_z=0.803310; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.734803; pairwise_continuous_alpha_z=0.663175; n=9460
  - claude-sonnet-5: rho=0.662838; pairwise_continuous_alpha_z=0.596582; n=11600
  - gemini-3.6-flash: rho=0.662121; pairwise_continuous_alpha_z=0.707793; n=11200
  - gpt-5.5: rho=0.789443; pairwise_continuous_alpha_z=0.662669; n=12230
  - gpt-5.6-sol: rho=0.748946; pairwise_continuous_alpha_z=0.635624; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.376311; pairwise_continuous_alpha_z=0.328000; n=11222; reason=None
  - L2: rho=0.160037; pairwise_continuous_alpha_z=0.125948; n=11222; reason=None
  - L3: rho=0.204627; pairwise_continuous_alpha_z=0.206477; n=11222; reason=None
  - L4: rho=0.159059; pairwise_continuous_alpha_z=0.180900; n=11222; reason=None
  - L5: rho=0.102224; pairwise_continuous_alpha_z=0.080182; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.479124; pairwise_continuous_alpha_z=0.529289; n=14685
  - news: rho=0.932242; pairwise_continuous_alpha_z=0.885727; n=14280
  - patent: rho=0.633217; pairwise_continuous_alpha_z=0.699977; n=13800
  - poetry: rho=0.797707; pairwise_continuous_alpha_z=0.789020; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.734966; pairwise_continuous_alpha_z=0.642805; n=9460
  - claude-sonnet-5: rho=0.662864; pairwise_continuous_alpha_z=0.608049; n=11600
  - gemini-3.6-flash: rho=0.661972; pairwise_continuous_alpha_z=0.683574; n=11200
  - gpt-5.5: rho=0.789653; pairwise_continuous_alpha_z=0.644025; n=12230
  - gpt-5.6-sol: rho=0.749232; pairwise_continuous_alpha_z=0.603994; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.752720; n=56110; reason=None
  - macro_within_level: 0.427721; n=11222; reason=None
  - item_centered: 0.804052; n=56110; reason=None
  - level:L1: 0.546051; n=11222; reason=None
  - level:L2: 0.396337; n=11222; reason=None
  - level:L3: 0.453293; n=11222; reason=None
  - level:L4: 0.430853; n=11222; reason=None
  - level:L5: 0.312072; n=11222; reason=None
  - by_domain:arxiv: 0.659575; n=14685; reason=None
  - by_domain:news: 0.942613; n=14280; reason=None
  - by_domain:patent: 0.769669; n=13800; reason=None
  - by_domain:poetry: 0.864344; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.771063; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.727098; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.800002; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.771305; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.751940; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.383781; pairwise_continuous_alpha_z=0.343329; n=11222; reason=None
  - L2: rho=0.165780; pairwise_continuous_alpha_z=0.144117; n=11222; reason=None
  - L3: rho=0.235721; pairwise_continuous_alpha_z=0.228317; n=11222; reason=None
  - L4: rho=0.168101; pairwise_continuous_alpha_z=0.180393; n=11222; reason=None
  - L5: rho=0.106624; pairwise_continuous_alpha_z=0.080535; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.475780; pairwise_continuous_alpha_z=0.487828; n=14685
  - news: rho=0.931606; pairwise_continuous_alpha_z=0.917280; n=14280
  - patent: rho=0.624664; pairwise_continuous_alpha_z=0.653749; n=13800
  - poetry: rho=0.794575; pairwise_continuous_alpha_z=0.801796; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.733294; pairwise_continuous_alpha_z=0.661309; n=9460
  - claude-sonnet-5: rho=0.660010; pairwise_continuous_alpha_z=0.600228; n=11600
  - gemini-3.6-flash: rho=0.655829; pairwise_continuous_alpha_z=0.708285; n=11200
  - gpt-5.5: rho=0.783480; pairwise_continuous_alpha_z=0.658845; n=12230
  - gpt-5.6-sol: rho=0.749163; pairwise_continuous_alpha_z=0.634953; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.360812; pairwise_continuous_alpha_z=0.319889; n=11222; reason=None
  - L2: rho=0.149453; pairwise_continuous_alpha_z=0.113462; n=11222; reason=None
  - L3: rho=0.171070; pairwise_continuous_alpha_z=0.160833; n=11222; reason=None
  - L4: rho=0.144686; pairwise_continuous_alpha_z=0.163661; n=11222; reason=None
  - L5: rho=0.091228; pairwise_continuous_alpha_z=0.073388; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.478403; pairwise_continuous_alpha_z=0.499917; n=14685
  - news: rho=0.928857; pairwise_continuous_alpha_z=0.918485; n=14280
  - patent: rho=0.636998; pairwise_continuous_alpha_z=0.665388; n=13800
  - poetry: rho=0.795620; pairwise_continuous_alpha_z=0.800936; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.732102; pairwise_continuous_alpha_z=0.661762; n=9460
  - claude-sonnet-5: rho=0.658973; pairwise_continuous_alpha_z=0.590130; n=11600
  - gemini-3.6-flash: rho=0.665904; pairwise_continuous_alpha_z=0.703177; n=11200
  - gpt-5.5: rho=0.789750; pairwise_continuous_alpha_z=0.663641; n=12230
  - gpt-5.6-sol: rho=0.746004; pairwise_continuous_alpha_z=0.632579; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.570990; pairwise_continuous_alpha_z=0.629148; n=14685
  - news: rho=0.969131; pairwise_continuous_alpha_z=0.917096; n=14280
  - patent: rho=0.688892; pairwise_continuous_alpha_z=0.746858; n=13800
  - poetry: rho=0.828999; pairwise_continuous_alpha_z=0.825260; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.703323; pairwise_continuous_alpha_z=0.616357; n=9460
  - claude-sonnet-5: rho=0.661762; pairwise_continuous_alpha_z=0.608458; n=11600
  - gemini-3.6-flash: rho=0.732126; pairwise_continuous_alpha_z=0.672396; n=11200
  - gpt-5.5: rho=0.796699; pairwise_continuous_alpha_z=0.647470; n=12230
  - gpt-5.6-sol: rho=0.785376; pairwise_continuous_alpha_z=0.650048; n=11620
- per-item ordinal: mean Spearman=0.799363; finite Spearman items=11222; mean Kendall tau-b=0.735356; finite tau-b items=11222; strict monotonic=3998/11222 (0.356264); nonstrict monotonic=4002/11222 (0.356621)

## G_raw_bits_per_output_byte

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.804253; pairwise_continuous_alpha_z=0.827609; n=11222; reason=None
  - L2: rho=0.547121; pairwise_continuous_alpha_z=0.501141; n=11222; reason=None
  - L3: rho=0.830293; pairwise_continuous_alpha_z=0.859990; n=11222; reason=None
  - L4: rho=0.791943; pairwise_continuous_alpha_z=0.784213; n=11222; reason=None
  - L5: rho=0.729757; pairwise_continuous_alpha_z=0.737097; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.968284; pairwise_continuous_alpha_z=0.934818; n=14685
  - news: rho=0.959855; pairwise_continuous_alpha_z=0.952025; n=14280
  - patent: rho=0.954091; pairwise_continuous_alpha_z=0.947346; n=13800
  - poetry: rho=0.942248; pairwise_continuous_alpha_z=0.914652; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.955759; pairwise_continuous_alpha_z=0.932522; n=9460
  - claude-sonnet-5: rho=0.965627; pairwise_continuous_alpha_z=0.932358; n=11600
  - gemini-3.6-flash: rho=0.926470; pairwise_continuous_alpha_z=0.912057; n=11200
  - gpt-5.5: rho=0.956496; pairwise_continuous_alpha_z=0.926480; n=12230
  - gpt-5.6-sol: rho=0.928148; pairwise_continuous_alpha_z=0.899682; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.803866; pairwise_continuous_alpha_z=0.813622; n=11222; reason=None
  - L2: rho=0.548241; pairwise_continuous_alpha_z=0.498497; n=11222; reason=None
  - L3: rho=0.830419; pairwise_continuous_alpha_z=0.845355; n=11222; reason=None
  - L4: rho=0.791665; pairwise_continuous_alpha_z=0.772368; n=11222; reason=None
  - L5: rho=0.732560; pairwise_continuous_alpha_z=0.715275; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.968440; pairwise_continuous_alpha_z=0.906720; n=14685
  - news: rho=0.959892; pairwise_continuous_alpha_z=0.945050; n=14280
  - patent: rho=0.953851; pairwise_continuous_alpha_z=0.914542; n=13800
  - poetry: rho=0.941935; pairwise_continuous_alpha_z=0.861478; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.955742; pairwise_continuous_alpha_z=0.901592; n=9460
  - claude-sonnet-5: rho=0.965511; pairwise_continuous_alpha_z=0.900296; n=11600
  - gemini-3.6-flash: rho=0.926111; pairwise_continuous_alpha_z=0.907389; n=11200
  - gpt-5.5: rho=0.956493; pairwise_continuous_alpha_z=0.900510; n=12230
  - gpt-5.6-sol: rho=0.927921; pairwise_continuous_alpha_z=0.882895; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.942457; n=56110; reason=None
  - macro_within_level: 0.792472; n=11222; reason=None
  - item_centered: 0.957436; n=56110; reason=None
  - level:L1: 0.873359; n=11222; reason=None
  - level:L2: 0.639959; n=11222; reason=None
  - level:L3: 0.892716; n=11222; reason=None
  - level:L4: 0.832268; n=11222; reason=None
  - level:L5: 0.724057; n=11222; reason=None
  - by_domain:arxiv: 0.952143; n=14685; reason=None
  - by_domain:news: 0.964114; n=14280; reason=None
  - by_domain:patent: 0.959921; n=13800; reason=None
  - by_domain:poetry: 0.938392; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.950188; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.950473; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.935753; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.946814; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.927465; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.808382; pairwise_continuous_alpha_z=0.831128; n=11222; reason=None
  - L2: rho=0.595052; pairwise_continuous_alpha_z=0.542312; n=11222; reason=None
  - L3: rho=0.811665; pairwise_continuous_alpha_z=0.848764; n=11222; reason=None
  - L4: rho=0.778607; pairwise_continuous_alpha_z=0.772513; n=11222; reason=None
  - L5: rho=0.651897; pairwise_continuous_alpha_z=0.664028; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.964370; pairwise_continuous_alpha_z=0.932002; n=14685
  - news: rho=0.954114; pairwise_continuous_alpha_z=0.948363; n=14280
  - patent: rho=0.948319; pairwise_continuous_alpha_z=0.940464; n=13800
  - poetry: rho=0.938473; pairwise_continuous_alpha_z=0.912800; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.954540; pairwise_continuous_alpha_z=0.931110; n=9460
  - claude-sonnet-5: rho=0.962668; pairwise_continuous_alpha_z=0.931031; n=11600
  - gemini-3.6-flash: rho=0.927327; pairwise_continuous_alpha_z=0.915973; n=11200
  - gpt-5.5: rho=0.956841; pairwise_continuous_alpha_z=0.927004; n=12230
  - gpt-5.6-sol: rho=0.926350; pairwise_continuous_alpha_z=0.898143; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.793373; pairwise_continuous_alpha_z=0.814000; n=11222; reason=None
  - L2: rho=0.484867; pairwise_continuous_alpha_z=0.446121; n=11222; reason=None
  - L3: rho=0.835283; pairwise_continuous_alpha_z=0.858634; n=11222; reason=None
  - L4: rho=0.786234; pairwise_continuous_alpha_z=0.775769; n=11222; reason=None
  - L5: rho=0.706086; pairwise_continuous_alpha_z=0.725831; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.966909; pairwise_continuous_alpha_z=0.933438; n=14685
  - news: rho=0.960462; pairwise_continuous_alpha_z=0.951902; n=14280
  - patent: rho=0.955168; pairwise_continuous_alpha_z=0.949421; n=13800
  - poetry: rho=0.937950; pairwise_continuous_alpha_z=0.912074; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.951138; pairwise_continuous_alpha_z=0.929329; n=9460
  - claude-sonnet-5: rho=0.961867; pairwise_continuous_alpha_z=0.929444; n=11600
  - gemini-3.6-flash: rho=0.918806; pairwise_continuous_alpha_z=0.902736; n=11200
  - gpt-5.5: rho=0.950840; pairwise_continuous_alpha_z=0.921999; n=12230
  - gpt-5.6-sol: rho=0.922668; pairwise_continuous_alpha_z=0.895957; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.871746; pairwise_continuous_alpha_z=0.802381; n=14685
  - news: rho=0.879101; pairwise_continuous_alpha_z=0.856667; n=14280
  - patent: rho=0.839804; pairwise_continuous_alpha_z=0.795664; n=13800
  - poetry: rho=0.835498; pairwise_continuous_alpha_z=0.755732; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.912289; pairwise_continuous_alpha_z=0.871548; n=9460
  - claude-sonnet-5: rho=0.936503; pairwise_continuous_alpha_z=0.861858; n=11600
  - gemini-3.6-flash: rho=0.822610; pairwise_continuous_alpha_z=0.772668; n=11200
  - gpt-5.5: rho=0.925803; pairwise_continuous_alpha_z=0.878670; n=12230
  - gpt-5.6-sol: rho=0.829655; pairwise_continuous_alpha_z=0.802982; n=11620
- per-item ordinal: mean Spearman=0.921690; finite Spearman items=11222; mean Kendall tau-b=0.869453; finite tau-b items=11222; strict monotonic=6041/11222 (0.538318); nonstrict monotonic=6041/11222 (0.538318)

## R_actual

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.878647; pairwise_continuous_alpha_z=0.916050; n=11222; reason=None
  - L2: rho=0.565037; pairwise_continuous_alpha_z=0.571647; n=11222; reason=None
  - L3: rho=0.867903; pairwise_continuous_alpha_z=0.899779; n=11222; reason=None
  - L4: rho=0.856958; pairwise_continuous_alpha_z=0.848260; n=11222; reason=None
  - L5: rho=0.739036; pairwise_continuous_alpha_z=0.773141; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.975689; pairwise_continuous_alpha_z=0.970702; n=14685
  - news: rho=0.971691; pairwise_continuous_alpha_z=0.972487; n=14280
  - patent: rho=0.974941; pairwise_continuous_alpha_z=0.966536; n=13800
  - poetry: rho=0.949086; pairwise_continuous_alpha_z=0.920798; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.959911; pairwise_continuous_alpha_z=0.949463; n=9460
  - claude-sonnet-5: rho=0.971195; pairwise_continuous_alpha_z=0.952388; n=11600
  - gemini-3.6-flash: rho=0.920394; pairwise_continuous_alpha_z=0.923582; n=11200
  - gpt-5.5: rho=0.967786; pairwise_continuous_alpha_z=0.961240; n=12230
  - gpt-5.6-sol: rho=0.953562; pairwise_continuous_alpha_z=0.952037; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.878142; pairwise_continuous_alpha_z=0.897070; n=11222; reason=None
  - L2: rho=0.566554; pairwise_continuous_alpha_z=0.569936; n=11222; reason=None
  - L3: rho=0.867968; pairwise_continuous_alpha_z=0.887817; n=11222; reason=None
  - L4: rho=0.856689; pairwise_continuous_alpha_z=0.843361; n=11222; reason=None
  - L5: rho=0.741704; pairwise_continuous_alpha_z=0.761533; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.975849; pairwise_continuous_alpha_z=0.951138; n=14685
  - news: rho=0.971748; pairwise_continuous_alpha_z=0.958254; n=14280
  - patent: rho=0.974925; pairwise_continuous_alpha_z=0.929095; n=13800
  - poetry: rho=0.948896; pairwise_continuous_alpha_z=0.871605; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.959992; pairwise_continuous_alpha_z=0.919227; n=9460
  - claude-sonnet-5: rho=0.971152; pairwise_continuous_alpha_z=0.925269; n=11600
  - gemini-3.6-flash: rho=0.920168; pairwise_continuous_alpha_z=0.925868; n=11200
  - gpt-5.5: rho=0.967816; pairwise_continuous_alpha_z=0.936275; n=12230
  - gpt-5.6-sol: rho=0.953536; pairwise_continuous_alpha_z=0.930498; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.962747; n=56110; reason=None
  - macro_within_level: 0.831703; n=11222; reason=None
  - item_centered: 0.971900; n=56110; reason=None
  - level:L1: 0.931921; n=11222; reason=None
  - level:L2: 0.686295; n=11222; reason=None
  - level:L3: 0.919049; n=11222; reason=None
  - level:L4: 0.874431; n=11222; reason=None
  - level:L5: 0.746821; n=11222; reason=None
  - by_domain:arxiv: 0.976034; n=14685; reason=None
  - by_domain:news: 0.977728; n=14280; reason=None
  - by_domain:patent: 0.972681; n=13800; reason=None
  - by_domain:poetry: 0.942482; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.961454; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.963794; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.943458; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.969934; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.962266; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.877058; pairwise_continuous_alpha_z=0.916469; n=11222; reason=None
  - L2: rho=0.620144; pairwise_continuous_alpha_z=0.617773; n=11222; reason=None
  - L3: rho=0.850353; pairwise_continuous_alpha_z=0.887771; n=11222; reason=None
  - L4: rho=0.843670; pairwise_continuous_alpha_z=0.835179; n=11222; reason=None
  - L5: rho=0.659791; pairwise_continuous_alpha_z=0.702078; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.971389; pairwise_continuous_alpha_z=0.965402; n=14685
  - news: rho=0.966599; pairwise_continuous_alpha_z=0.968459; n=14280
  - patent: rho=0.969621; pairwise_continuous_alpha_z=0.957884; n=13800
  - poetry: rho=0.944972; pairwise_continuous_alpha_z=0.919267; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.960009; pairwise_continuous_alpha_z=0.947759; n=9460
  - claude-sonnet-5: rho=0.969192; pairwise_continuous_alpha_z=0.951253; n=11600
  - gemini-3.6-flash: rho=0.917986; pairwise_continuous_alpha_z=0.922794; n=11200
  - gpt-5.5: rho=0.967295; pairwise_continuous_alpha_z=0.959285; n=12230
  - gpt-5.6-sol: rho=0.952590; pairwise_continuous_alpha_z=0.949704; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.869184; pairwise_continuous_alpha_z=0.904341; n=11222; reason=None
  - L2: rho=0.496129; pairwise_continuous_alpha_z=0.509665; n=11222; reason=None
  - L3: rho=0.871116; pairwise_continuous_alpha_z=0.898624; n=11222; reason=None
  - L4: rho=0.849515; pairwise_continuous_alpha_z=0.839588; n=11222; reason=None
  - L5: rho=0.715641; pairwise_continuous_alpha_z=0.756074; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.974848; pairwise_continuous_alpha_z=0.971709; n=14685
  - news: rho=0.971760; pairwise_continuous_alpha_z=0.972647; n=14280
  - patent: rho=0.975520; pairwise_continuous_alpha_z=0.970283; n=13800
  - poetry: rho=0.945689; pairwise_continuous_alpha_z=0.917877; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.954503; pairwise_continuous_alpha_z=0.946477; n=9460
  - claude-sonnet-5: rho=0.966832; pairwise_continuous_alpha_z=0.949185; n=11600
  - gemini-3.6-flash: rho=0.917095; pairwise_continuous_alpha_z=0.919027; n=11200
  - gpt-5.5: rho=0.962870; pairwise_continuous_alpha_z=0.959078; n=12230
  - gpt-5.6-sol: rho=0.947832; pairwise_continuous_alpha_z=0.948795; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.902487; pairwise_continuous_alpha_z=0.868832; n=14685
  - news: rho=0.910303; pairwise_continuous_alpha_z=0.893995; n=14280
  - patent: rho=0.883203; pairwise_continuous_alpha_z=0.833576; n=13800
  - poetry: rho=0.868658; pairwise_continuous_alpha_z=0.783525; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.921415; pairwise_continuous_alpha_z=0.894735; n=9460
  - claude-sonnet-5: rho=0.946755; pairwise_continuous_alpha_z=0.894774; n=11600
  - gemini-3.6-flash: rho=0.873985; pairwise_continuous_alpha_z=0.847214; n=11200
  - gpt-5.5: rho=0.944745; pairwise_continuous_alpha_z=0.919921; n=12230
  - gpt-5.6-sol: rho=0.884168; pairwise_continuous_alpha_z=0.874584; n=11620
- per-item ordinal: mean Spearman=0.951265; finite Spearman items=11222; mean Kendall tau-b=0.911210; finite tau-b items=11222; strict monotonic=7173/11222 (0.639191); nonstrict monotonic=7173/11222 (0.639191)

## char3_coverage

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.880639; pairwise_continuous_alpha_z=0.917067; n=11222; reason=None
  - L2: rho=0.406900; pairwise_continuous_alpha_z=0.453641; n=11222; reason=None
  - L3: rho=0.855354; pairwise_continuous_alpha_z=0.893014; n=11222; reason=None
  - L4: rho=0.765415; pairwise_continuous_alpha_z=0.778059; n=11222; reason=None
  - L5: rho=0.733443; pairwise_continuous_alpha_z=0.740980; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.971196; pairwise_continuous_alpha_z=0.975452; n=14685
  - news: rho=0.966907; pairwise_continuous_alpha_z=0.954198; n=14280
  - patent: rho=0.973615; pairwise_continuous_alpha_z=0.969666; n=13800
  - poetry: rho=0.959772; pairwise_continuous_alpha_z=0.971240; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.971252; pairwise_continuous_alpha_z=0.969133; n=9460
  - claude-sonnet-5: rho=0.961786; pairwise_continuous_alpha_z=0.965882; n=11600
  - gemini-3.6-flash: rho=0.930247; pairwise_continuous_alpha_z=0.907268; n=11200
  - gpt-5.5: rho=0.972125; pairwise_continuous_alpha_z=0.976593; n=12230
  - gpt-5.6-sol: rho=0.953248; pairwise_continuous_alpha_z=0.963776; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.880166; pairwise_continuous_alpha_z=0.915471; n=11222; reason=None
  - L2: rho=0.408004; pairwise_continuous_alpha_z=0.452702; n=11222; reason=None
  - L3: rho=0.855441; pairwise_continuous_alpha_z=0.880494; n=11222; reason=None
  - L4: rho=0.765129; pairwise_continuous_alpha_z=0.766671; n=11222; reason=None
  - L5: rho=0.735731; pairwise_continuous_alpha_z=0.722941; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.971284; pairwise_continuous_alpha_z=0.957736; n=14685
  - news: rho=0.966898; pairwise_continuous_alpha_z=0.958634; n=14280
  - patent: rho=0.973665; pairwise_continuous_alpha_z=0.947959; n=13800
  - poetry: rho=0.959722; pairwise_continuous_alpha_z=0.949302; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.971304; pairwise_continuous_alpha_z=0.949199; n=9460
  - claude-sonnet-5: rho=0.961808; pairwise_continuous_alpha_z=0.950173; n=11600
  - gemini-3.6-flash: rho=0.929753; pairwise_continuous_alpha_z=0.901939; n=11200
  - gpt-5.5: rho=0.972162; pairwise_continuous_alpha_z=0.967827; n=12230
  - gpt-5.6-sol: rho=0.953248; pairwise_continuous_alpha_z=0.958043; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.969564; n=56110; reason=None
  - macro_within_level: 0.802075; n=11222; reason=None
  - item_centered: 0.977035; n=56110; reason=None
  - level:L1: 0.932671; n=11222; reason=None
  - level:L2: 0.608830; n=11222; reason=None
  - level:L3: 0.914571; n=11222; reason=None
  - level:L4: 0.828060; n=11222; reason=None
  - level:L5: 0.726244; n=11222; reason=None
  - by_domain:arxiv: 0.979154; n=14685; reason=None
  - by_domain:news: 0.965574; n=14280; reason=None
  - by_domain:patent: 0.974767; n=13800; reason=None
  - by_domain:poetry: 0.976054; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.974538; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.972746; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.932531; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.980154; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.970082; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.883968; pairwise_continuous_alpha_z=0.924059; n=11222; reason=None
  - L2: rho=0.449483; pairwise_continuous_alpha_z=0.495249; n=11222; reason=None
  - L3: rho=0.841814; pairwise_continuous_alpha_z=0.881120; n=11222; reason=None
  - L4: rho=0.758584; pairwise_continuous_alpha_z=0.771997; n=11222; reason=None
  - L5: rho=0.656679; pairwise_continuous_alpha_z=0.654661; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.967870; pairwise_continuous_alpha_z=0.974457; n=14685
  - news: rho=0.963937; pairwise_continuous_alpha_z=0.958322; n=14280
  - patent: rho=0.971964; pairwise_continuous_alpha_z=0.969945; n=13800
  - poetry: rho=0.957959; pairwise_continuous_alpha_z=0.972812; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.970364; pairwise_continuous_alpha_z=0.970140; n=9460
  - claude-sonnet-5: rho=0.960054; pairwise_continuous_alpha_z=0.968379; n=11600
  - gemini-3.6-flash: rho=0.931622; pairwise_continuous_alpha_z=0.915378; n=11200
  - gpt-5.5: rho=0.970551; pairwise_continuous_alpha_z=0.978733; n=12230
  - gpt-5.6-sol: rho=0.956310; pairwise_continuous_alpha_z=0.967458; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.867878; pairwise_continuous_alpha_z=0.899003; n=11222; reason=None
  - L2: rho=0.354981; pairwise_continuous_alpha_z=0.399797; n=11222; reason=None
  - L3: rho=0.854562; pairwise_continuous_alpha_z=0.891844; n=11222; reason=None
  - L4: rho=0.753402; pairwise_continuous_alpha_z=0.763660; n=11222; reason=None
  - L5: rho=0.708626; pairwise_continuous_alpha_z=0.741760; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.969439; pairwise_continuous_alpha_z=0.972016; n=14685
  - news: rho=0.965007; pairwise_continuous_alpha_z=0.946324; n=14280
  - patent: rho=0.970455; pairwise_continuous_alpha_z=0.964477; n=13800
  - poetry: rho=0.955192; pairwise_continuous_alpha_z=0.965046; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.966476; pairwise_continuous_alpha_z=0.963348; n=9460
  - claude-sonnet-5: rho=0.957376; pairwise_continuous_alpha_z=0.958914; n=11600
  - gemini-3.6-flash: rho=0.922556; pairwise_continuous_alpha_z=0.893665; n=11200
  - gpt-5.5: rho=0.968496; pairwise_continuous_alpha_z=0.970290; n=12230
  - gpt-5.6-sol: rho=0.944156; pairwise_continuous_alpha_z=0.954490; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.908197; pairwise_continuous_alpha_z=0.869804; n=14685
  - news: rho=0.960839; pairwise_continuous_alpha_z=0.960961; n=14280
  - patent: rho=0.922726; pairwise_continuous_alpha_z=0.893438; n=13800
  - poetry: rho=0.932968; pairwise_continuous_alpha_z=0.894560; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.942166; pairwise_continuous_alpha_z=0.933108; n=9460
  - claude-sonnet-5: rho=0.951320; pairwise_continuous_alpha_z=0.931252; n=11600
  - gemini-3.6-flash: rho=0.860849; pairwise_continuous_alpha_z=0.803268; n=11200
  - gpt-5.5: rho=0.968183; pairwise_continuous_alpha_z=0.957076; n=12230
  - gpt-5.6-sol: rho=0.953835; pairwise_continuous_alpha_z=0.956075; n=11620
- per-item ordinal: mean Spearman=0.968437; finite Spearman items=11222; mean Kendall tau-b=0.943539; finite tau-b items=11222; strict monotonic=8467/11222 (0.754500); nonstrict monotonic=8467/11222 (0.754500)

## char5_coverage

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.886942; pairwise_continuous_alpha_z=0.921892; n=11222; reason=None
  - L2: rho=0.479172; pairwise_continuous_alpha_z=0.496942; n=11222; reason=None
  - L3: rho=0.876219; pairwise_continuous_alpha_z=0.904879; n=11222; reason=None
  - L4: rho=0.855504; pairwise_continuous_alpha_z=0.849643; n=11222; reason=None
  - L5: rho=0.649690; pairwise_continuous_alpha_z=0.655146; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.967510; pairwise_continuous_alpha_z=0.966387; n=14685
  - news: rho=0.973765; pairwise_continuous_alpha_z=0.980244; n=14280
  - patent: rho=0.975284; pairwise_continuous_alpha_z=0.970023; n=13800
  - poetry: rho=0.947112; pairwise_continuous_alpha_z=0.920657; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.963977; pairwise_continuous_alpha_z=0.950843; n=9460
  - claude-sonnet-5: rho=0.967410; pairwise_continuous_alpha_z=0.945915; n=11600
  - gemini-3.6-flash: rho=0.902683; pairwise_continuous_alpha_z=0.894357; n=11200
  - gpt-5.5: rho=0.969411; pairwise_continuous_alpha_z=0.967519; n=12230
  - gpt-5.6-sol: rho=0.949261; pairwise_continuous_alpha_z=0.956992; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.886506; pairwise_continuous_alpha_z=0.908419; n=11222; reason=None
  - L2: rho=0.480715; pairwise_continuous_alpha_z=0.495659; n=11222; reason=None
  - L3: rho=0.876250; pairwise_continuous_alpha_z=0.890920; n=11222; reason=None
  - L4: rho=0.855231; pairwise_continuous_alpha_z=0.836385; n=11222; reason=None
  - L5: rho=0.650236; pairwise_continuous_alpha_z=0.630557; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.967613; pairwise_continuous_alpha_z=0.936475; n=14685
  - news: rho=0.973793; pairwise_continuous_alpha_z=0.963242; n=14280
  - patent: rho=0.975368; pairwise_continuous_alpha_z=0.931885; n=13800
  - poetry: rho=0.947104; pairwise_continuous_alpha_z=0.865929; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.964034; pairwise_continuous_alpha_z=0.916483; n=9460
  - claude-sonnet-5: rho=0.967432; pairwise_continuous_alpha_z=0.916798; n=11600
  - gemini-3.6-flash: rho=0.902380; pairwise_continuous_alpha_z=0.886956; n=11200
  - gpt-5.5: rho=0.969448; pairwise_continuous_alpha_z=0.940924; n=12230
  - gpt-5.6-sol: rho=0.949365; pairwise_continuous_alpha_z=0.930895; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.963174; n=56110; reason=None
  - macro_within_level: 0.808515; n=11222; reason=None
  - item_centered: 0.971509; n=56110; reason=None
  - level:L1: 0.935843; n=11222; reason=None
  - level:L2: 0.637328; n=11222; reason=None
  - level:L3: 0.922419; n=11222; reason=None
  - level:L4: 0.875180; n=11222; reason=None
  - level:L5: 0.671803; n=11222; reason=None
  - by_domain:arxiv: 0.973166; n=14685; reason=None
  - by_domain:news: 0.982894; n=14280; reason=None
  - by_domain:patent: 0.975001; n=13800; reason=None
  - by_domain:poetry: 0.942403; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.962373; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.959482; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.924003; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.974112; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.965564; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.890744; pairwise_continuous_alpha_z=0.926765; n=11222; reason=None
  - L2: rho=0.531271; pairwise_continuous_alpha_z=0.543361; n=11222; reason=None
  - L3: rho=0.862848; pairwise_continuous_alpha_z=0.894519; n=11222; reason=None
  - L4: rho=0.846201; pairwise_continuous_alpha_z=0.842178; n=11222; reason=None
  - L5: rho=0.576883; pairwise_continuous_alpha_z=0.552367; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.963594; pairwise_continuous_alpha_z=0.960822; n=14685
  - news: rho=0.970180; pairwise_continuous_alpha_z=0.978852; n=14280
  - patent: rho=0.971710; pairwise_continuous_alpha_z=0.964227; n=13800
  - poetry: rho=0.943796; pairwise_continuous_alpha_z=0.920976; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.964202; pairwise_continuous_alpha_z=0.950035; n=9460
  - claude-sonnet-5: rho=0.965999; pairwise_continuous_alpha_z=0.945805; n=11600
  - gemini-3.6-flash: rho=0.901261; pairwise_continuous_alpha_z=0.896508; n=11200
  - gpt-5.5: rho=0.967706; pairwise_continuous_alpha_z=0.966338; n=12230
  - gpt-5.6-sol: rho=0.950359; pairwise_continuous_alpha_z=0.956746; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.873588; pairwise_continuous_alpha_z=0.905813; n=11222; reason=None
  - L2: rho=0.416449; pairwise_continuous_alpha_z=0.437178; n=11222; reason=None
  - L3: rho=0.875026; pairwise_continuous_alpha_z=0.901988; n=11222; reason=None
  - L4: rho=0.843402; pairwise_continuous_alpha_z=0.834836; n=11222; reason=None
  - L5: rho=0.633607; pairwise_continuous_alpha_z=0.680733; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.966677; pairwise_continuous_alpha_z=0.967686; n=14685
  - news: rho=0.972624; pairwise_continuous_alpha_z=0.977753; n=14280
  - patent: rho=0.974082; pairwise_continuous_alpha_z=0.970900; n=13800
  - poetry: rho=0.944380; pairwise_continuous_alpha_z=0.915929; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.958629; pairwise_continuous_alpha_z=0.946959; n=9460
  - claude-sonnet-5: rho=0.963084; pairwise_continuous_alpha_z=0.941697; n=11600
  - gemini-3.6-flash: rho=0.899241; pairwise_continuous_alpha_z=0.886951; n=11200
  - gpt-5.5: rho=0.966134; pairwise_continuous_alpha_z=0.964559; n=12230
  - gpt-5.6-sol: rho=0.942444; pairwise_continuous_alpha_z=0.951649; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.910734; pairwise_continuous_alpha_z=0.858580; n=14685
  - news: rho=0.948907; pairwise_continuous_alpha_z=0.937654; n=14280
  - patent: rho=0.919395; pairwise_continuous_alpha_z=0.866413; n=13800
  - poetry: rho=0.912053; pairwise_continuous_alpha_z=0.799678; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.930395; pairwise_continuous_alpha_z=0.899722; n=9460
  - claude-sonnet-5: rho=0.952191; pairwise_continuous_alpha_z=0.894951; n=11600
  - gemini-3.6-flash: rho=0.866471; pairwise_continuous_alpha_z=0.808820; n=11200
  - gpt-5.5: rho=0.962876; pairwise_continuous_alpha_z=0.932191; n=12230
  - gpt-5.6-sol: rho=0.926829; pairwise_continuous_alpha_z=0.915368; n=11620
- per-item ordinal: mean Spearman=0.965176; finite Spearman items=11222; mean Kendall tau-b=0.938656; finite tau-b items=11222; strict monotonic=8347/11222 (0.743807); nonstrict monotonic=8347/11222 (0.743807)

## char8_coverage

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.877450; pairwise_continuous_alpha_z=0.897099; n=11222; reason=None
  - L2: rho=0.506097; pairwise_continuous_alpha_z=0.521832; n=11222; reason=None
  - L3: rho=0.857644; pairwise_continuous_alpha_z=0.892077; n=11222; reason=None
  - L4: rho=0.848252; pairwise_continuous_alpha_z=0.840909; n=11222; reason=None
  - L5: rho=0.385532; pairwise_continuous_alpha_z=0.490017; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.953454; pairwise_continuous_alpha_z=0.934171; n=14685
  - news: rho=0.966249; pairwise_continuous_alpha_z=0.966714; n=14280
  - patent: rho=0.961073; pairwise_continuous_alpha_z=0.938041; n=13800
  - poetry: rho=0.879494; pairwise_continuous_alpha_z=0.840846; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.931178; pairwise_continuous_alpha_z=0.904366; n=9460
  - claude-sonnet-5: rho=0.939375; pairwise_continuous_alpha_z=0.891929; n=11600
  - gemini-3.6-flash: rho=0.842688; pairwise_continuous_alpha_z=0.829438; n=11200
  - gpt-5.5: rho=0.950484; pairwise_continuous_alpha_z=0.936607; n=12230
  - gpt-5.6-sol: rho=0.925762; pairwise_continuous_alpha_z=0.924651; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.877106; pairwise_continuous_alpha_z=0.873128; n=11222; reason=None
  - L2: rho=0.507797; pairwise_continuous_alpha_z=0.519912; n=11222; reason=None
  - L3: rho=0.857613; pairwise_continuous_alpha_z=0.876652; n=11222; reason=None
  - L4: rho=0.848043; pairwise_continuous_alpha_z=0.822799; n=11222; reason=None
  - L5: rho=0.384099; pairwise_continuous_alpha_z=0.471507; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.953577; pairwise_continuous_alpha_z=0.893241; n=14685
  - news: rho=0.966351; pairwise_continuous_alpha_z=0.930027; n=14280
  - patent: rho=0.961233; pairwise_continuous_alpha_z=0.884927; n=13800
  - poetry: rho=0.879548; pairwise_continuous_alpha_z=0.765524; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.931284; pairwise_continuous_alpha_z=0.857970; n=9460
  - claude-sonnet-5: rho=0.939390; pairwise_continuous_alpha_z=0.850094; n=11600
  - gemini-3.6-flash: rho=0.842603; pairwise_continuous_alpha_z=0.816657; n=11200
  - gpt-5.5: rho=0.950557; pairwise_continuous_alpha_z=0.894758; n=12230
  - gpt-5.6-sol: rho=0.925993; pairwise_continuous_alpha_z=0.881947; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.936736; n=56110; reason=None
  - macro_within_level: 0.784937; n=11222; reason=None
  - item_centered: 0.944752; n=56110; reason=None
  - level:L1: 0.919402; n=11222; reason=None
  - level:L2: 0.653595; n=11222; reason=None
  - level:L3: 0.913944; n=11222; reason=None
  - level:L4: 0.869450; n=11222; reason=None
  - level:L5: 0.568295; n=11222; reason=None
  - by_domain:arxiv: 0.951768; n=14685; reason=None
  - by_domain:news: 0.973883; n=14280; reason=None
  - by_domain:patent: 0.953732; n=13800; reason=None
  - by_domain:poetry: 0.889322; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.931462; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.923590; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.880903; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.953543; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.944059; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.882379; pairwise_continuous_alpha_z=0.900657; n=11222; reason=None
  - L2: rho=0.562033; pairwise_continuous_alpha_z=0.566082; n=11222; reason=None
  - L3: rho=0.844787; pairwise_continuous_alpha_z=0.883189; n=11222; reason=None
  - L4: rho=0.838536; pairwise_continuous_alpha_z=0.832944; n=11222; reason=None
  - L5: rho=0.342561; pairwise_continuous_alpha_z=0.417895; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.949171; pairwise_continuous_alpha_z=0.925291; n=14685
  - news: rho=0.962274; pairwise_continuous_alpha_z=0.960642; n=14280
  - patent: rho=0.956079; pairwise_continuous_alpha_z=0.927515; n=13800
  - poetry: rho=0.874417; pairwise_continuous_alpha_z=0.841139; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.932868; pairwise_continuous_alpha_z=0.902059; n=9460
  - claude-sonnet-5: rho=0.939085; pairwise_continuous_alpha_z=0.889337; n=11600
  - gemini-3.6-flash: rho=0.837866; pairwise_continuous_alpha_z=0.825684; n=11200
  - gpt-5.5: rho=0.949144; pairwise_continuous_alpha_z=0.932749; n=12230
  - gpt-5.6-sol: rho=0.925584; pairwise_continuous_alpha_z=0.921305; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.863148; pairwise_continuous_alpha_z=0.882596; n=11222; reason=None
  - L2: rho=0.438843; pairwise_continuous_alpha_z=0.463258; n=11222; reason=None
  - L3: rho=0.856456; pairwise_continuous_alpha_z=0.887891; n=11222; reason=None
  - L4: rho=0.836785; pairwise_continuous_alpha_z=0.826881; n=11222; reason=None
  - L5: rho=0.377233; pairwise_continuous_alpha_z=0.504686; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.953458; pairwise_continuous_alpha_z=0.939024; n=14685
  - news: rho=0.965958; pairwise_continuous_alpha_z=0.968930; n=14280
  - patent: rho=0.961396; pairwise_continuous_alpha_z=0.943804; n=13800
  - poetry: rho=0.878855; pairwise_continuous_alpha_z=0.836528; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.924964; pairwise_continuous_alpha_z=0.902204; n=9460
  - claude-sonnet-5: rho=0.934104; pairwise_continuous_alpha_z=0.890490; n=11600
  - gemini-3.6-flash: rho=0.844256; pairwise_continuous_alpha_z=0.828476; n=11200
  - gpt-5.5: rho=0.947066; pairwise_continuous_alpha_z=0.936443; n=12230
  - gpt-5.6-sol: rho=0.920722; pairwise_continuous_alpha_z=0.922574; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.907060; pairwise_continuous_alpha_z=0.823980; n=14685
  - news: rho=0.927216; pairwise_continuous_alpha_z=0.881560; n=14280
  - patent: rho=0.901388; pairwise_continuous_alpha_z=0.815796; n=13800
  - poetry: rho=0.850138; pairwise_continuous_alpha_z=0.698154; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.897031; pairwise_continuous_alpha_z=0.844975; n=9460
  - claude-sonnet-5: rho=0.922502; pairwise_continuous_alpha_z=0.828768; n=11600
  - gemini-3.6-flash: rho=0.850335; pairwise_continuous_alpha_z=0.760359; n=11200
  - gpt-5.5: rho=0.942507; pairwise_continuous_alpha_z=0.886612; n=12230
  - gpt-5.6-sol: rho=0.892837; pairwise_continuous_alpha_z=0.856941; n=11620
- per-item ordinal: mean Spearman=0.942272; finite Spearman items=11222; mean Kendall tau-b=0.900512; finite tau-b items=11222; strict monotonic=6660/11222 (0.593477); nonstrict monotonic=6661/11222 (0.593566)

## output_bigram_repeat_fraction

### Reference: consensus_global_z
- per_level:
  - L1: rho=-0.255536; pairwise_continuous_alpha_z=-0.332783; n=11222; reason=None
  - L2: rho=0.108625; pairwise_continuous_alpha_z=0.131977; n=11222; reason=None
  - L3: rho=-0.170489; pairwise_continuous_alpha_z=-0.095838; n=11222; reason=None
  - L4: rho=-0.149694; pairwise_continuous_alpha_z=-0.150956; n=11222; reason=None
  - L5: rho=-0.464688; pairwise_continuous_alpha_z=-0.434109; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.282299; pairwise_continuous_alpha_z=-0.293789; n=14685
  - news: rho=0.332992; pairwise_continuous_alpha_z=0.387038; n=14280
  - patent: rho=0.533179; pairwise_continuous_alpha_z=0.508316; n=13800
  - poetry: rho=-0.258962; pairwise_continuous_alpha_z=-0.083172; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.090501; pairwise_continuous_alpha_z=0.141966; n=9460
  - claude-sonnet-5: rho=-0.088300; pairwise_continuous_alpha_z=-0.071337; n=11600
  - gemini-3.6-flash: rho=-0.050240; pairwise_continuous_alpha_z=0.071315; n=11200
  - gpt-5.5: rho=0.155596; pairwise_continuous_alpha_z=0.178718; n=12230
  - gpt-5.6-sol: rho=0.246259; pairwise_continuous_alpha_z=0.301102; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=-0.255405; pairwise_continuous_alpha_z=-0.340906; n=11222; reason=None
  - L2: rho=0.109998; pairwise_continuous_alpha_z=0.134242; n=11222; reason=None
  - L3: rho=-0.170820; pairwise_continuous_alpha_z=-0.098704; n=11222; reason=None
  - L4: rho=-0.149565; pairwise_continuous_alpha_z=-0.157101; n=11222; reason=None
  - L5: rho=-0.467904; pairwise_continuous_alpha_z=-0.455488; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.282358; pairwise_continuous_alpha_z=-0.268889; n=14685
  - news: rho=0.333086; pairwise_continuous_alpha_z=0.339088; n=14280
  - patent: rho=0.533776; pairwise_continuous_alpha_z=0.520352; n=13800
  - poetry: rho=-0.258710; pairwise_continuous_alpha_z=-0.090352; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.091205; pairwise_continuous_alpha_z=0.154109; n=9460
  - claude-sonnet-5: rho=-0.088198; pairwise_continuous_alpha_z=-0.050450; n=11600
  - gemini-3.6-flash: rho=-0.049642; pairwise_continuous_alpha_z=0.093132; n=11200
  - gpt-5.5: rho=0.155829; pairwise_continuous_alpha_z=0.193758; n=12230
  - gpt-5.6-sol: rho=0.246690; pairwise_continuous_alpha_z=0.288952; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.401930; n=56110; reason=None
  - macro_within_level: 0.193183; n=11222; reason=None
  - item_centered: 0.455637; n=56110; reason=None
  - level:L1: 0.104344; n=11222; reason=None
  - level:L2: 0.397567; n=11222; reason=None
  - level:L3: 0.260140; n=11222; reason=None
  - level:L4: 0.216743; n=11222; reason=None
  - level:L5: -0.012878; n=11222; reason=None
  - by_domain:arxiv: 0.134974; n=14685; reason=None
  - by_domain:news: 0.588196; n=14280; reason=None
  - by_domain:patent: 0.667971; n=13800; reason=None
  - by_domain:poetry: 0.274781; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.424442; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.282884; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.377114; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.449358; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.529575; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=-0.260547; pairwise_continuous_alpha_z=-0.344930; n=11222; reason=None
  - L2: rho=0.152048; pairwise_continuous_alpha_z=0.156681; n=11222; reason=None
  - L3: rho=-0.159691; pairwise_continuous_alpha_z=-0.090895; n=11222; reason=None
  - L4: rho=-0.143616; pairwise_continuous_alpha_z=-0.145969; n=11222; reason=None
  - L5: rho=-0.448629; pairwise_continuous_alpha_z=-0.431227; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.286117; pairwise_continuous_alpha_z=-0.301018; n=14685
  - news: rho=0.336760; pairwise_continuous_alpha_z=0.383344; n=14280
  - patent: rho=0.528910; pairwise_continuous_alpha_z=0.498977; n=13800
  - poetry: rho=-0.260123; pairwise_continuous_alpha_z=-0.082711; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.094499; pairwise_continuous_alpha_z=0.141180; n=9460
  - claude-sonnet-5: rho=-0.090457; pairwise_continuous_alpha_z=-0.075549; n=11600
  - gemini-3.6-flash: rho=-0.066344; pairwise_continuous_alpha_z=0.049341; n=11200
  - gpt-5.5: rho=0.152268; pairwise_continuous_alpha_z=0.175856; n=12230
  - gpt-5.6-sol: rho=0.250443; pairwise_continuous_alpha_z=0.301008; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=-0.251963; pairwise_continuous_alpha_z=-0.316953; n=11222; reason=None
  - L2: rho=0.066497; pairwise_continuous_alpha_z=0.104587; n=11222; reason=None
  - L3: rho=-0.178607; pairwise_continuous_alpha_z=-0.099408; n=11222; reason=None
  - L4: rho=-0.152498; pairwise_continuous_alpha_z=-0.152299; n=11222; reason=None
  - L5: rho=-0.424005; pairwise_continuous_alpha_z=-0.389686; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.277818; pairwise_continuous_alpha_z=-0.285021; n=14685
  - news: rho=0.330889; pairwise_continuous_alpha_z=0.389181; n=14280
  - patent: rho=0.534437; pairwise_continuous_alpha_z=0.515070; n=13800
  - poetry: rho=-0.254299; pairwise_continuous_alpha_z=-0.083224; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.088484; pairwise_continuous_alpha_z=0.142048; n=9460
  - claude-sonnet-5: rho=-0.087974; pairwise_continuous_alpha_z=-0.066713; n=11600
  - gemini-3.6-flash: rho=-0.027894; pairwise_continuous_alpha_z=0.093476; n=11200
  - gpt-5.5: rho=0.157262; pairwise_continuous_alpha_z=0.180801; n=12230
  - gpt-5.6-sol: rho=0.241767; pairwise_continuous_alpha_z=0.299438; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=-0.056276; pairwise_continuous_alpha_z=-0.001580; n=14685
  - news: rho=0.391192; pairwise_continuous_alpha_z=0.403865; n=14280
  - patent: rho=0.599374; pairwise_continuous_alpha_z=0.592917; n=13800
  - poetry: rho=-0.090759; pairwise_continuous_alpha_z=0.085715; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.155523; pairwise_continuous_alpha_z=0.206722; n=9460
  - claude-sonnet-5: rho=-0.030840; pairwise_continuous_alpha_z=0.022813; n=11600
  - gemini-3.6-flash: rho=0.248342; pairwise_continuous_alpha_z=0.380243; n=11200
  - gpt-5.5: rho=0.208320; pairwise_continuous_alpha_z=0.234818; n=12230
  - gpt-5.6-sol: rho=0.318030; pairwise_continuous_alpha_z=0.333595; n=11620
- per-item ordinal: mean Spearman=0.218541; finite Spearman items=11222; mean Kendall tau-b=0.188995; finite tau-b items=11222; strict monotonic=670/11222 (0.059704); nonstrict monotonic=671/11222 (0.059793)

## output_bytes

### Reference: consensus_global_z
- per_level:
  - L1: rho=-0.244584; pairwise_continuous_alpha_z=-0.262502; n=11222; reason=None
  - L2: rho=-0.163931; pairwise_continuous_alpha_z=-0.084383; n=11222; reason=None
  - L3: rho=-0.724029; pairwise_continuous_alpha_z=-0.677719; n=11222; reason=None
  - L4: rho=-0.619527; pairwise_continuous_alpha_z=-0.560956; n=11222; reason=None
  - L5: rho=-0.672676; pairwise_continuous_alpha_z=-0.609375; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.649565; pairwise_continuous_alpha_z=-0.566686; n=14685
  - news: rho=0.435401; pairwise_continuous_alpha_z=0.418559; n=14280
  - patent: rho=-0.448940; pairwise_continuous_alpha_z=-0.452188; n=13800
  - poetry: rho=-0.378696; pairwise_continuous_alpha_z=-0.383484; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.275174; pairwise_continuous_alpha_z=-0.240587; n=9460
  - claude-sonnet-5: rho=-0.429346; pairwise_continuous_alpha_z=-0.442603; n=11600
  - gemini-3.6-flash: rho=-0.235235; pairwise_continuous_alpha_z=-0.304872; n=11200
  - gpt-5.5: rho=-0.091010; pairwise_continuous_alpha_z=-0.140032; n=12230
  - gpt-5.6-sol: rho=-0.025685; pairwise_continuous_alpha_z=-0.043301; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=-0.243221; pairwise_continuous_alpha_z=-0.261035; n=11222; reason=None
  - L2: rho=-0.164301; pairwise_continuous_alpha_z=-0.088594; n=11222; reason=None
  - L3: rho=-0.724638; pairwise_continuous_alpha_z=-0.688182; n=11222; reason=None
  - L4: rho=-0.619311; pairwise_continuous_alpha_z=-0.589667; n=11222; reason=None
  - L5: rho=-0.676030; pairwise_continuous_alpha_z=-0.646167; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.649587; pairwise_continuous_alpha_z=-0.578639; n=14685
  - news: rho=0.435454; pairwise_continuous_alpha_z=0.394989; n=14280
  - patent: rho=-0.448177; pairwise_continuous_alpha_z=-0.424539; n=13800
  - poetry: rho=-0.377863; pairwise_continuous_alpha_z=-0.381273; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.274473; pairwise_continuous_alpha_z=-0.219893; n=9460
  - claude-sonnet-5: rho=-0.429164; pairwise_continuous_alpha_z=-0.406828; n=11600
  - gemini-3.6-flash: rho=-0.235490; pairwise_continuous_alpha_z=-0.337921; n=11200
  - gpt-5.5: rho=-0.090447; pairwise_continuous_alpha_z=-0.131591; n=12230
  - gpt-5.6-sol: rho=-0.024829; pairwise_continuous_alpha_z=-0.063903; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.131909; n=56110; reason=None
  - macro_within_level: 0.021166; n=11222; reason=None
  - item_centered: 0.163597; n=56110; reason=None
  - level:L1: 0.151137; n=11222; reason=None
  - level:L2: 0.255294; n=11222; reason=None
  - level:L3: -0.124984; n=11222; reason=None
  - level:L4: -0.053174; n=11222; reason=None
  - level:L5: -0.122441; n=11222; reason=None
  - by_domain:arxiv: -0.046602; n=14685; reason=None
  - by_domain:news: 0.609185; n=14280; reason=None
  - by_domain:patent: 0.029252; n=13800; reason=None
  - by_domain:poetry: 0.075045; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.170031; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.035925; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.126863; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.237304; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.300644; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=-0.236078; pairwise_continuous_alpha_z=-0.255063; n=11222; reason=None
  - L2: rho=-0.182488; pairwise_continuous_alpha_z=-0.078500; n=11222; reason=None
  - L3: rho=-0.692383; pairwise_continuous_alpha_z=-0.651910; n=11222; reason=None
  - L4: rho=-0.605057; pairwise_continuous_alpha_z=-0.546697; n=11222; reason=None
  - L5: rho=-0.596718; pairwise_continuous_alpha_z=-0.558742; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.647219; pairwise_continuous_alpha_z=-0.567414; n=14685
  - news: rho=0.441078; pairwise_continuous_alpha_z=0.423795; n=14280
  - patent: rho=-0.445429; pairwise_continuous_alpha_z=-0.453310; n=13800
  - poetry: rho=-0.376380; pairwise_continuous_alpha_z=-0.383669; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.269806; pairwise_continuous_alpha_z=-0.242132; n=9460
  - claude-sonnet-5: rho=-0.429768; pairwise_continuous_alpha_z=-0.445060; n=11600
  - gemini-3.6-flash: rho=-0.244386; pairwise_continuous_alpha_z=-0.306581; n=11200
  - gpt-5.5: rho=-0.101160; pairwise_continuous_alpha_z=-0.145775; n=12230
  - gpt-5.6-sol: rho=-0.023209; pairwise_continuous_alpha_z=-0.041475; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=-0.254081; pairwise_continuous_alpha_z=-0.266442; n=11222; reason=None
  - L2: rho=-0.140929; pairwise_continuous_alpha_z=-0.087045; n=11222; reason=None
  - L3: rho=-0.744554; pairwise_continuous_alpha_z=-0.693746; n=11222; reason=None
  - L4: rho=-0.619780; pairwise_continuous_alpha_z=-0.561309; n=11222; reason=None
  - L5: rho=-0.654726; pairwise_continuous_alpha_z=-0.590854; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.648545; pairwise_continuous_alpha_z=-0.563348; n=14685
  - news: rho=0.429313; pairwise_continuous_alpha_z=0.411697; n=14280
  - patent: rho=-0.451144; pairwise_continuous_alpha_z=-0.448777; n=13800
  - poetry: rho=-0.375146; pairwise_continuous_alpha_z=-0.381465; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.276298; pairwise_continuous_alpha_z=-0.237861; n=9460
  - claude-sonnet-5: rho=-0.429181; pairwise_continuous_alpha_z=-0.438070; n=11600
  - gemini-3.6-flash: rho=-0.223174; pairwise_continuous_alpha_z=-0.301345; n=11200
  - gpt-5.5: rho=-0.083309; pairwise_continuous_alpha_z=-0.133720; n=12230
  - gpt-5.6-sol: rho=-0.025872; pairwise_continuous_alpha_z=-0.044862; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=-0.448030; pairwise_continuous_alpha_z=-0.374569; n=14685
  - news: rho=0.627816; pairwise_continuous_alpha_z=0.599055; n=14280
  - patent: rho=-0.260591; pairwise_continuous_alpha_z=-0.277654; n=13800
  - poetry: rho=-0.134459; pairwise_continuous_alpha_z=-0.130435; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.243196; pairwise_continuous_alpha_z=-0.192386; n=9460
  - claude-sonnet-5: rho=-0.378422; pairwise_continuous_alpha_z=-0.326289; n=11600
  - gemini-3.6-flash: rho=-0.015642; pairwise_continuous_alpha_z=-0.139950; n=11200
  - gpt-5.5: rho=-0.007779; pairwise_continuous_alpha_z=-0.012343; n=12230
  - gpt-5.6-sol: rho=0.168488; pairwise_continuous_alpha_z=0.130997; n=11620
- per-item ordinal: mean Spearman=-0.061715; finite Spearman items=11222; mean Kendall tau-b=-0.070765; finite tau-b items=11222; strict monotonic=59/11222 (0.005258); nonstrict monotonic=61/11222 (0.005436)

## output_self_bits_per_byte

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.242937; pairwise_continuous_alpha_z=0.286592; n=11222; reason=None
  - L2: rho=0.024682; pairwise_continuous_alpha_z=0.050987; n=11222; reason=None
  - L3: rho=0.407304; pairwise_continuous_alpha_z=0.436633; n=11222; reason=None
  - L4: rho=0.230294; pairwise_continuous_alpha_z=0.253772; n=11222; reason=None
  - L5: rho=0.613491; pairwise_continuous_alpha_z=0.681627; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.549090; pairwise_continuous_alpha_z=0.558551; n=14685
  - news: rho=-0.296729; pairwise_continuous_alpha_z=-0.292605; n=14280
  - patent: rho=-0.165277; pairwise_continuous_alpha_z=-0.185131; n=13800
  - poetry: rho=0.371386; pairwise_continuous_alpha_z=0.281047; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.072350; pairwise_continuous_alpha_z=0.096702; n=9460
  - claude-sonnet-5: rho=0.334553; pairwise_continuous_alpha_z=0.406339; n=11600
  - gemini-3.6-flash: rho=0.149045; pairwise_continuous_alpha_z=0.155783; n=11200
  - gpt-5.5: rho=-0.003460; pairwise_continuous_alpha_z=0.072002; n=12230
  - gpt-5.6-sol: rho=-0.112503; pairwise_continuous_alpha_z=-0.137893; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.242559; pairwise_continuous_alpha_z=0.294708; n=11222; reason=None
  - L2: rho=0.023666; pairwise_continuous_alpha_z=0.049104; n=11222; reason=None
  - L3: rho=0.407650; pairwise_continuous_alpha_z=0.431543; n=11222; reason=None
  - L4: rho=0.230111; pairwise_continuous_alpha_z=0.247144; n=11222; reason=None
  - L5: rho=0.616484; pairwise_continuous_alpha_z=0.682818; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.549060; pairwise_continuous_alpha_z=0.534525; n=14685
  - news: rho=-0.296962; pairwise_continuous_alpha_z=-0.273415; n=14280
  - patent: rho=-0.166033; pairwise_continuous_alpha_z=-0.218791; n=13800
  - poetry: rho=0.370679; pairwise_continuous_alpha_z=0.266899; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.071441; pairwise_continuous_alpha_z=0.067927; n=9460
  - claude-sonnet-5: rho=0.334335; pairwise_continuous_alpha_z=0.365951; n=11600
  - gemini-3.6-flash: rho=0.148736; pairwise_continuous_alpha_z=0.137081; n=11200
  - gpt-5.5: rho=-0.003801; pairwise_continuous_alpha_z=0.041915; n=12230
  - gpt-5.6-sol: rho=-0.113333; pairwise_continuous_alpha_z=-0.134397; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.417789; n=56110; reason=None
  - macro_within_level: 0.528732; n=11222; reason=None
  - item_centered: 0.402001; n=56110; reason=None
  - level:L1: 0.514953; n=11222; reason=None
  - level:L2: 0.343733; n=11222; reason=None
  - level:L3: 0.612551; n=11222; reason=None
  - level:L4: 0.483203; n=11222; reason=None
  - level:L5: 0.689219; n=11222; reason=None
  - by_domain:arxiv: 0.701785; n=14685; reason=None
  - by_domain:news: 0.135992; n=14280; reason=None
  - by_domain:patent: 0.206842; n=13800; reason=None
  - by_domain:poetry: 0.517019; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.394337; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.600584; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.432911; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.378383; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.237760; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.247431; pairwise_continuous_alpha_z=0.294506; n=11222; reason=None
  - L2: rho=-0.004035; pairwise_continuous_alpha_z=0.043656; n=11222; reason=None
  - L3: rho=0.392691; pairwise_continuous_alpha_z=0.426076; n=11222; reason=None
  - L4: rho=0.224871; pairwise_continuous_alpha_z=0.249106; n=11222; reason=None
  - L5: rho=0.546770; pairwise_continuous_alpha_z=0.615454; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.550282; pairwise_continuous_alpha_z=0.564996; n=14685
  - news: rho=-0.301825; pairwise_continuous_alpha_z=-0.295939; n=14280
  - patent: rho=-0.164539; pairwise_continuous_alpha_z=-0.185409; n=13800
  - poetry: rho=0.370067; pairwise_continuous_alpha_z=0.282073; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.065415; pairwise_continuous_alpha_z=0.093549; n=9460
  - claude-sonnet-5: rho=0.333488; pairwise_continuous_alpha_z=0.405983; n=11600
  - gemini-3.6-flash: rho=0.164714; pairwise_continuous_alpha_z=0.172464; n=11200
  - gpt-5.5: rho=0.004130; pairwise_continuous_alpha_z=0.079702; n=12230
  - gpt-5.6-sol: rho=-0.115029; pairwise_continuous_alpha_z=-0.138692; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.240863; pairwise_continuous_alpha_z=0.275418; n=11222; reason=None
  - L2: rho=0.048335; pairwise_continuous_alpha_z=0.056112; n=11222; reason=None
  - L3: rho=0.415454; pairwise_continuous_alpha_z=0.440841; n=11222; reason=None
  - L4: rho=0.230213; pairwise_continuous_alpha_z=0.251996; n=11222; reason=None
  - L5: rho=0.595065; pairwise_continuous_alpha_z=0.669894; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.546206; pairwise_continuous_alpha_z=0.549378; n=14685
  - news: rho=-0.291896; pairwise_continuous_alpha_z=-0.288131; n=14280
  - patent: rho=-0.164062; pairwise_continuous_alpha_z=-0.183915; n=13800
  - poetry: rho=0.367685; pairwise_continuous_alpha_z=0.278697; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.075284; pairwise_continuous_alpha_z=0.099366; n=9460
  - claude-sonnet-5: rho=0.335437; pairwise_continuous_alpha_z=0.404841; n=11600
  - gemini-3.6-flash: rho=0.127899; pairwise_continuous_alpha_z=0.137740; n=11200
  - gpt-5.5: rho=-0.008278; pairwise_continuous_alpha_z=0.064033; n=12230
  - gpt-5.6-sol: rho=-0.110186; pairwise_continuous_alpha_z=-0.136294; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.341193; pairwise_continuous_alpha_z=0.329014; n=14685
  - news: rho=-0.437074; pairwise_continuous_alpha_z=-0.454441; n=14280
  - patent: rho=-0.270069; pairwise_continuous_alpha_z=-0.327314; n=13800
  - poetry: rho=0.166203; pairwise_continuous_alpha_z=0.040391; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.018267; pairwise_continuous_alpha_z=0.032654; n=9460
  - claude-sonnet-5: rho=0.285442; pairwise_continuous_alpha_z=0.291528; n=11600
  - gemini-3.6-flash: rho=-0.157875; pairwise_continuous_alpha_z=-0.157618; n=11200
  - gpt-5.5: rho=-0.071534; pairwise_continuous_alpha_z=-0.042726; n=12230
  - gpt-5.6-sol: rho=-0.254554; pairwise_continuous_alpha_z=-0.281708; n=11620
- per-item ordinal: mean Spearman=-0.050538; finite Spearman items=11222; mean Kendall tau-b=-0.038199; finite tau-b items=11222; strict monotonic=20/11222 (0.001782); nonstrict monotonic=20/11222 (0.001782)

## output_type_token_ratio

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.165166; pairwise_continuous_alpha_z=0.228929; n=11222; reason=None
  - L2: rho=-0.080196; pairwise_continuous_alpha_z=-0.078472; n=11222; reason=None
  - L3: rho=0.338522; pairwise_continuous_alpha_z=0.344870; n=11222; reason=None
  - L4: rho=0.294146; pairwise_continuous_alpha_z=0.315212; n=11222; reason=None
  - L5: rho=0.598380; pairwise_continuous_alpha_z=0.644259; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.475522; pairwise_continuous_alpha_z=0.497829; n=14685
  - news: rho=-0.447356; pairwise_continuous_alpha_z=-0.451260; n=14280
  - patent: rho=-0.315749; pairwise_continuous_alpha_z=-0.314647; n=13800
  - poetry: rho=0.330473; pairwise_continuous_alpha_z=0.283903; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.004670; pairwise_continuous_alpha_z=0.030212; n=9460
  - claude-sonnet-5: rho=0.251464; pairwise_continuous_alpha_z=0.337239; n=11600
  - gemini-3.6-flash: rho=0.167434; pairwise_continuous_alpha_z=0.151224; n=11200
  - gpt-5.5: rho=-0.097559; pairwise_continuous_alpha_z=-0.046785; n=12230
  - gpt-5.6-sol: rho=-0.219906; pairwise_continuous_alpha_z=-0.238336; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.164912; pairwise_continuous_alpha_z=0.237527; n=11222; reason=None
  - L2: rho=-0.081172; pairwise_continuous_alpha_z=-0.078961; n=11222; reason=None
  - L3: rho=0.338887; pairwise_continuous_alpha_z=0.344782; n=11222; reason=None
  - L4: rho=0.293994; pairwise_continuous_alpha_z=0.321134; n=11222; reason=None
  - L5: rho=0.601346; pairwise_continuous_alpha_z=0.654676; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.475577; pairwise_continuous_alpha_z=0.485121; n=14685
  - news: rho=-0.447458; pairwise_continuous_alpha_z=-0.410891; n=14280
  - patent: rho=-0.316471; pairwise_continuous_alpha_z=-0.337537; n=13800
  - poetry: rho=0.330007; pairwise_continuous_alpha_z=0.293747; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.003877; pairwise_continuous_alpha_z=0.013307; n=9460
  - claude-sonnet-5: rho=0.251216; pairwise_continuous_alpha_z=0.305139; n=11600
  - gemini-3.6-flash: rho=0.166909; pairwise_continuous_alpha_z=0.146165; n=11200
  - gpt-5.5: rho=-0.097841; pairwise_continuous_alpha_z=-0.065329; n=12230
  - gpt-5.6-sol: rho=-0.220488; pairwise_continuous_alpha_z=-0.221120; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.362185; n=56110; reason=None
  - macro_within_level: 0.495475; n=11222; reason=None
  - item_centered: 0.345982; n=56110; reason=None
  - level:L1: 0.476752; n=11222; reason=None
  - level:L2: 0.258651; n=11222; reason=None
  - level:L3: 0.551827; n=11222; reason=None
  - level:L4: 0.523657; n=11222; reason=None
  - level:L5: 0.666489; n=11222; reason=None
  - by_domain:arxiv: 0.661381; n=14685; reason=None
  - by_domain:news: 0.030438; n=14280; reason=None
  - by_domain:patent: 0.120718; n=13800; reason=None
  - by_domain:poetry: 0.518925; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.350125; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.554595; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.429869; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.299359; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.170994; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.170856; pairwise_continuous_alpha_z=0.237281; n=11222; reason=None
  - L2: rho=-0.107824; pairwise_continuous_alpha_z=-0.095042; n=11222; reason=None
  - L3: rho=0.324399; pairwise_continuous_alpha_z=0.333790; n=11222; reason=None
  - L4: rho=0.288204; pairwise_continuous_alpha_z=0.308952; n=11222; reason=None
  - L5: rho=0.568470; pairwise_continuous_alpha_z=0.620233; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.478250; pairwise_continuous_alpha_z=0.505937; n=14685
  - news: rho=-0.450773; pairwise_continuous_alpha_z=-0.450102; n=14280
  - patent: rho=-0.312798; pairwise_continuous_alpha_z=-0.309132; n=13800
  - poetry: rho=0.330707; pairwise_continuous_alpha_z=0.285787; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.002842; pairwise_continuous_alpha_z=0.032256; n=9460
  - claude-sonnet-5: rho=0.255722; pairwise_continuous_alpha_z=0.340947; n=11600
  - gemini-3.6-flash: rho=0.183917; pairwise_continuous_alpha_z=0.169165; n=11200
  - gpt-5.5: rho=-0.090553; pairwise_continuous_alpha_z=-0.039378; n=12230
  - gpt-5.6-sol: rho=-0.223939; pairwise_continuous_alpha_z=-0.238595; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.162867; pairwise_continuous_alpha_z=0.218044; n=11222; reason=None
  - L2: rho=-0.054192; pairwise_continuous_alpha_z=-0.060433; n=11222; reason=None
  - L3: rho=0.347295; pairwise_continuous_alpha_z=0.350958; n=11222; reason=None
  - L4: rho=0.293140; pairwise_continuous_alpha_z=0.313509; n=11222; reason=None
  - L5: rho=0.551491; pairwise_continuous_alpha_z=0.596926; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.471257; pairwise_continuous_alpha_z=0.487226; n=14685
  - news: rho=-0.443973; pairwise_continuous_alpha_z=-0.450627; n=14280
  - patent: rho=-0.316578; pairwise_continuous_alpha_z=-0.318560; n=13800
  - poetry: rho=0.326100; pairwise_continuous_alpha_z=0.280702; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.004546; pairwise_continuous_alpha_z=0.028026; n=9460
  - claude-sonnet-5: rho=0.248635; pairwise_continuous_alpha_z=0.331912; n=11600
  - gemini-3.6-flash: rho=0.144308; pairwise_continuous_alpha_z=0.131914; n=11200
  - gpt-5.5: rho=-0.101971; pairwise_continuous_alpha_z=-0.053956; n=12230
  - gpt-5.6-sol: rho=-0.215638; pairwise_continuous_alpha_z=-0.236686; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.260768; pairwise_continuous_alpha_z=0.261837; n=14685
  - news: rho=-0.540208; pairwise_continuous_alpha_z=-0.536984; n=14280
  - patent: rho=-0.400011; pairwise_continuous_alpha_z=-0.420459; n=13800
  - poetry: rho=0.133840; pairwise_continuous_alpha_z=0.084581; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.057473; pairwise_continuous_alpha_z=-0.036402; n=9460
  - claude-sonnet-5: rho=0.188578; pairwise_continuous_alpha_z=0.217269; n=11600
  - gemini-3.6-flash: rho=-0.143979; pairwise_continuous_alpha_z=-0.147690; n=11200
  - gpt-5.5: rho=-0.165555; pairwise_continuous_alpha_z=-0.151197; n=12230
  - gpt-5.6-sol: rho=-0.342026; pairwise_continuous_alpha_z=-0.350792; n=11620
- per-item ordinal: mean Spearman=-0.141324; finite Spearman items=11222; mean Kendall tau-b=-0.128410; finite tau-b items=11222; strict monotonic=16/11222 (0.001426); nonstrict monotonic=16/11222 (0.001426)

## output_words

### Reference: consensus_global_z
- per_level:
  - L1: rho=-0.177292; pairwise_continuous_alpha_z=-0.188687; n=11222; reason=None
  - L2: rho=-0.118862; pairwise_continuous_alpha_z=-0.049886; n=11222; reason=None
  - L3: rho=-0.729453; pairwise_continuous_alpha_z=-0.696290; n=11222; reason=None
  - L4: rho=-0.665759; pairwise_continuous_alpha_z=-0.600164; n=11222; reason=None
  - L5: rho=-0.687425; pairwise_continuous_alpha_z=-0.634445; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.646519; pairwise_continuous_alpha_z=-0.564521; n=14685
  - news: rho=0.485273; pairwise_continuous_alpha_z=0.483464; n=14280
  - patent: rho=-0.441483; pairwise_continuous_alpha_z=-0.448396; n=13800
  - poetry: rho=-0.352361; pairwise_continuous_alpha_z=-0.361422; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.246782; pairwise_continuous_alpha_z=-0.191265; n=9460
  - claude-sonnet-5: rho=-0.406698; pairwise_continuous_alpha_z=-0.432374; n=11600
  - gemini-3.6-flash: rho=-0.245296; pairwise_continuous_alpha_z=-0.286773; n=11200
  - gpt-5.5: rho=-0.051029; pairwise_continuous_alpha_z=-0.094088; n=12230
  - gpt-5.6-sol: rho=0.020331; pairwise_continuous_alpha_z=0.010435; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=-0.176189; pairwise_continuous_alpha_z=-0.188311; n=11222; reason=None
  - L2: rho=-0.119456; pairwise_continuous_alpha_z=-0.054293; n=11222; reason=None
  - L3: rho=-0.730045; pairwise_continuous_alpha_z=-0.706953; n=11222; reason=None
  - L4: rho=-0.665563; pairwise_continuous_alpha_z=-0.631925; n=11222; reason=None
  - L5: rho=-0.691052; pairwise_continuous_alpha_z=-0.670383; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.646555; pairwise_continuous_alpha_z=-0.577696; n=14685
  - news: rho=0.485305; pairwise_continuous_alpha_z=0.456357; n=14280
  - patent: rho=-0.440709; pairwise_continuous_alpha_z=-0.420452; n=13800
  - poetry: rho=-0.351558; pairwise_continuous_alpha_z=-0.365628; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.246149; pairwise_continuous_alpha_z=-0.176579; n=9460
  - claude-sonnet-5: rho=-0.406514; pairwise_continuous_alpha_z=-0.398819; n=11600
  - gemini-3.6-flash: rho=-0.245535; pairwise_continuous_alpha_z=-0.327343; n=11200
  - gpt-5.5: rho=-0.050529; pairwise_continuous_alpha_z=-0.090914; n=12230
  - gpt-5.6-sol: rho=0.021115; pairwise_continuous_alpha_z=-0.014649; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.153139; n=56110; reason=None
  - macro_within_level: 0.024655; n=11222; reason=None
  - item_centered: 0.184799; n=56110; reason=None
  - level:L1: 0.200040; n=11222; reason=None
  - level:L2: 0.277777; n=11222; reason=None
  - level:L3: -0.137273; n=11222; reason=None
  - level:L4: -0.078952; n=11222; reason=None
  - level:L5: -0.138320; n=11222; reason=None
  - by_domain:arxiv: -0.045160; n=14685; reason=None
  - by_domain:news: 0.652368; n=14280; reason=None
  - by_domain:patent: 0.031773; n=13800; reason=None
  - by_domain:poetry: 0.089720; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.202829; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.042735; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.138900; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.267869; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.336364; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=-0.169862; pairwise_continuous_alpha_z=-0.181604; n=11222; reason=None
  - L2: rho=-0.145719; pairwise_continuous_alpha_z=-0.049736; n=11222; reason=None
  - L3: rho=-0.698680; pairwise_continuous_alpha_z=-0.671101; n=11222; reason=None
  - L4: rho=-0.651226; pairwise_continuous_alpha_z=-0.586195; n=11222; reason=None
  - L5: rho=-0.617760; pairwise_continuous_alpha_z=-0.587491; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.644370; pairwise_continuous_alpha_z=-0.565524; n=14685
  - news: rho=0.490368; pairwise_continuous_alpha_z=0.487533; n=14280
  - patent: rho=-0.438667; pairwise_continuous_alpha_z=-0.450101; n=13800
  - poetry: rho=-0.349676; pairwise_continuous_alpha_z=-0.361390; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.243656; pairwise_continuous_alpha_z=-0.194204; n=9460
  - claude-sonnet-5: rho=-0.409213; pairwise_continuous_alpha_z=-0.435813; n=11600
  - gemini-3.6-flash: rho=-0.254838; pairwise_continuous_alpha_z=-0.289123; n=11200
  - gpt-5.5: rho=-0.062036; pairwise_continuous_alpha_z=-0.100181; n=12230
  - gpt-5.6-sol: rho=0.022950; pairwise_continuous_alpha_z=0.012149; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=-0.186154; pairwise_continuous_alpha_z=-0.193195; n=11222; reason=None
  - L2: rho=-0.089823; pairwise_continuous_alpha_z=-0.048361; n=11222; reason=None
  - L3: rho=-0.749121; pairwise_continuous_alpha_z=-0.711420; n=11222; reason=None
  - L4: rho=-0.664904; pairwise_continuous_alpha_z=-0.599144; n=11222; reason=None
  - L5: rho=-0.661675; pairwise_continuous_alpha_z=-0.609740; n=11222; reason=None
- by_domain:
  - arxiv: rho=-0.645312; pairwise_continuous_alpha_z=-0.560911; n=14685
  - news: rho=0.479596; pairwise_continuous_alpha_z=0.477506; n=14280
  - patent: rho=-0.442902; pairwise_continuous_alpha_z=-0.444422; n=13800
  - poetry: rho=-0.349418; pairwise_continuous_alpha_z=-0.359720; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.246369; pairwise_continuous_alpha_z=-0.187393; n=9460
  - claude-sonnet-5: rho=-0.405258; pairwise_continuous_alpha_z=-0.426886; n=11600
  - gemini-3.6-flash: rho=-0.232810; pairwise_continuous_alpha_z=-0.282692; n=11200
  - gpt-5.5: rho=-0.042698; pairwise_continuous_alpha_z=-0.087623; n=12230
  - gpt-5.6-sol: rho=0.019572; pairwise_continuous_alpha_z=0.008672; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=-0.447356; pairwise_continuous_alpha_z=-0.374944; n=14685
  - news: rho=0.666168; pairwise_continuous_alpha_z=0.645285; n=14280
  - patent: rho=-0.254687; pairwise_continuous_alpha_z=-0.274934; n=13800
  - poetry: rho=-0.105760; pairwise_continuous_alpha_z=-0.112719; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=-0.213313; pairwise_continuous_alpha_z=-0.142712; n=9460
  - claude-sonnet-5: rho=-0.352517; pairwise_continuous_alpha_z=-0.310357; n=11600
  - gemini-3.6-flash: rho=-0.033093; pairwise_continuous_alpha_z=-0.127911; n=11200
  - gpt-5.5: rho=0.033627; pairwise_continuous_alpha_z=0.027996; n=12230
  - gpt-5.6-sol: rho=0.214219; pairwise_continuous_alpha_z=0.178240; n=11620
- per-item ordinal: mean Spearman=-0.037759; finite Spearman items=11222; mean Kendall tau-b=-0.039796; finite tau-b items=11222; strict monotonic=110/11222 (0.009802); nonstrict monotonic=115/11222 (0.010248)

## prompt_bytes

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.231744; pairwise_continuous_alpha_z=0.232826; n=11222; reason=None
  - L2: rho=-0.100763; pairwise_continuous_alpha_z=-0.071405; n=11222; reason=None
  - L3: rho=0.017708; pairwise_continuous_alpha_z=-0.013223; n=11222; reason=None
  - L4: rho=-0.018000; pairwise_continuous_alpha_z=0.000539; n=11222; reason=None
  - L5: rho=0.203820; pairwise_continuous_alpha_z=0.213496; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.651516; pairwise_continuous_alpha_z=0.607622; n=14685
  - news: rho=0.856001; pairwise_continuous_alpha_z=0.819206; n=14280
  - patent: rho=0.825386; pairwise_continuous_alpha_z=0.785147; n=13800
  - poetry: rho=0.844354; pairwise_continuous_alpha_z=0.807262; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.860875; pairwise_continuous_alpha_z=0.681717; n=9460
  - claude-sonnet-5: rho=0.811949; pairwise_continuous_alpha_z=0.626376; n=11600
  - gemini-3.6-flash: rho=0.862773; pairwise_continuous_alpha_z=0.717810; n=11200
  - gpt-5.5: rho=0.860887; pairwise_continuous_alpha_z=0.658433; n=12230
  - gpt-5.6-sol: rho=0.795704; pairwise_continuous_alpha_z=0.585348; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.232667; pairwise_continuous_alpha_z=0.242315; n=11222; reason=None
  - L2: rho=-0.100913; pairwise_continuous_alpha_z=-0.074800; n=11222; reason=None
  - L3: rho=0.016605; pairwise_continuous_alpha_z=-0.002592; n=11222; reason=None
  - L4: rho=-0.017927; pairwise_continuous_alpha_z=-0.000130; n=11222; reason=None
  - L5: rho=0.203286; pairwise_continuous_alpha_z=0.209398; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.651646; pairwise_continuous_alpha_z=0.644521; n=14685
  - news: rho=0.855997; pairwise_continuous_alpha_z=0.816406; n=14280
  - patent: rho=0.825639; pairwise_continuous_alpha_z=0.830521; n=13800
  - poetry: rho=0.844460; pairwise_continuous_alpha_z=0.844179; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.861109; pairwise_continuous_alpha_z=0.673046; n=9460
  - claude-sonnet-5: rho=0.811985; pairwise_continuous_alpha_z=0.644226; n=11600
  - gemini-3.6-flash: rho=0.862296; pairwise_continuous_alpha_z=0.696554; n=11200
  - gpt-5.5: rho=0.861074; pairwise_continuous_alpha_z=0.662312; n=12230
  - gpt-5.6-sol: rho=0.795857; pairwise_continuous_alpha_z=0.580521; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.740937; n=56110; reason=None
  - macro_within_level: 0.354067; n=11222; reason=None
  - item_centered: 0.797232; n=56110; reason=None
  - level:L1: 0.479390; n=11222; reason=None
  - level:L2: 0.263998; n=11222; reason=None
  - level:L3: 0.314722; n=11222; reason=None
  - level:L4: 0.315859; n=11222; reason=None
  - level:L5: 0.396365; n=11222; reason=None
  - by_domain:arxiv: 0.734467; n=14685; reason=None
  - by_domain:news: 0.875762; n=14280; reason=None
  - by_domain:patent: 0.852067; n=13800; reason=None
  - by_domain:poetry: 0.867012; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.783398; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.746879; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.806554; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.768498; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.718540; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.237406; pairwise_continuous_alpha_z=0.245962; n=11222; reason=None
  - L2: rho=-0.104188; pairwise_continuous_alpha_z=-0.057026; n=11222; reason=None
  - L3: rho=0.060232; pairwise_continuous_alpha_z=0.024996; n=11222; reason=None
  - L4: rho=0.007906; pairwise_continuous_alpha_z=0.023695; n=11222; reason=None
  - L5: rho=0.231782; pairwise_continuous_alpha_z=0.263987; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.651062; pairwise_continuous_alpha_z=0.609338; n=14685
  - news: rho=0.856776; pairwise_continuous_alpha_z=0.826784; n=14280
  - patent: rho=0.829480; pairwise_continuous_alpha_z=0.793892; n=13800
  - poetry: rho=0.845229; pairwise_continuous_alpha_z=0.810869; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.859542; pairwise_continuous_alpha_z=0.682983; n=9460
  - claude-sonnet-5: rho=0.809239; pairwise_continuous_alpha_z=0.635382; n=11600
  - gemini-3.6-flash: rho=0.863043; pairwise_continuous_alpha_z=0.729913; n=11200
  - gpt-5.5: rho=0.855763; pairwise_continuous_alpha_z=0.660619; n=12230
  - gpt-5.6-sol: rho=0.800709; pairwise_continuous_alpha_z=0.593532; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.221462; pairwise_continuous_alpha_z=0.217276; n=11222; reason=None
  - L2: rho=-0.093550; pairwise_continuous_alpha_z=-0.082407; n=11222; reason=None
  - L3: rho=-0.026534; pairwise_continuous_alpha_z=-0.051553; n=11222; reason=None
  - L4: rho=-0.045446; pairwise_continuous_alpha_z=-0.024617; n=11222; reason=None
  - L5: rho=0.164195; pairwise_continuous_alpha_z=0.142813; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.648288; pairwise_continuous_alpha_z=0.603083; n=14685
  - news: rho=0.851583; pairwise_continuous_alpha_z=0.808431; n=14280
  - patent: rho=0.816714; pairwise_continuous_alpha_z=0.772436; n=13800
  - poetry: rho=0.839477; pairwise_continuous_alpha_z=0.799867; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.858178; pairwise_continuous_alpha_z=0.677094; n=9460
  - claude-sonnet-5: rho=0.809733; pairwise_continuous_alpha_z=0.614319; n=11600
  - gemini-3.6-flash: rho=0.857502; pairwise_continuous_alpha_z=0.701205; n=11200
  - gpt-5.5: rho=0.861274; pairwise_continuous_alpha_z=0.653445; n=12230
  - gpt-5.6-sol: rho=0.787883; pairwise_continuous_alpha_z=0.573802; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.695525; pairwise_continuous_alpha_z=0.693891; n=14685
  - news: rho=0.928395; pairwise_continuous_alpha_z=0.899787; n=14280
  - patent: rho=0.914581; pairwise_continuous_alpha_z=0.919759; n=13800
  - poetry: rho=0.918277; pairwise_continuous_alpha_z=0.927249; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.855556; pairwise_continuous_alpha_z=0.659265; n=9460
  - claude-sonnet-5: rho=0.837237; pairwise_continuous_alpha_z=0.654523; n=11600
  - gemini-3.6-flash: rho=0.870254; pairwise_continuous_alpha_z=0.659849; n=11200
  - gpt-5.5: rho=0.881854; pairwise_continuous_alpha_z=0.663367; n=12230
  - gpt-5.6-sol: rho=0.884937; pairwise_continuous_alpha_z=0.666685; n=11620
- per-item ordinal: mean Spearman=0.859522; finite Spearman items=11222; mean Kendall tau-b=0.755424; finite tau-b items=11222; strict monotonic=0/11222 (0.000000); nonstrict monotonic=0/11222 (0.000000)

## prompt_to_output_byte_ratio

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.633730; pairwise_continuous_alpha_z=0.783785; n=11222; reason=None
  - L2: rho=0.167177; pairwise_continuous_alpha_z=0.128481; n=11222; reason=None
  - L3: rho=0.828567; pairwise_continuous_alpha_z=0.870174; n=11222; reason=None
  - L4: rho=0.692347; pairwise_continuous_alpha_z=0.698583; n=11222; reason=None
  - L5: rho=0.719561; pairwise_continuous_alpha_z=0.722645; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.953328; pairwise_continuous_alpha_z=0.921060; n=14685
  - news: rho=0.894827; pairwise_continuous_alpha_z=0.880096; n=14280
  - patent: rho=0.915073; pairwise_continuous_alpha_z=0.873260; n=13800
  - poetry: rho=0.934052; pairwise_continuous_alpha_z=0.890541; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.934618; pairwise_continuous_alpha_z=0.918016; n=9460
  - claude-sonnet-5: rho=0.930652; pairwise_continuous_alpha_z=0.924329; n=11600
  - gemini-3.6-flash: rho=0.911012; pairwise_continuous_alpha_z=0.806364; n=11200
  - gpt-5.5: rho=0.925715; pairwise_continuous_alpha_z=0.919704; n=12230
  - gpt-5.6-sol: rho=0.885415; pairwise_continuous_alpha_z=0.856299; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.633011; pairwise_continuous_alpha_z=0.795152; n=11222; reason=None
  - L2: rho=0.167976; pairwise_continuous_alpha_z=0.129344; n=11222; reason=None
  - L3: rho=0.828711; pairwise_continuous_alpha_z=0.855395; n=11222; reason=None
  - L4: rho=0.692108; pairwise_continuous_alpha_z=0.685892; n=11222; reason=None
  - L5: rho=0.722682; pairwise_continuous_alpha_z=0.700668; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.953462; pairwise_continuous_alpha_z=0.905773; n=14685
  - news: rho=0.894723; pairwise_continuous_alpha_z=0.897606; n=14280
  - patent: rho=0.914990; pairwise_continuous_alpha_z=0.865890; n=13800
  - poetry: rho=0.933945; pairwise_continuous_alpha_z=0.890953; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.934770; pairwise_continuous_alpha_z=0.905596; n=9460
  - claude-sonnet-5: rho=0.930631; pairwise_continuous_alpha_z=0.911497; n=11600
  - gemini-3.6-flash: rho=0.910420; pairwise_continuous_alpha_z=0.800241; n=11200
  - gpt-5.5: rho=0.925808; pairwise_continuous_alpha_z=0.925893; n=12230
  - gpt-5.6-sol: rho=0.885373; pairwise_continuous_alpha_z=0.870053; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.919708; n=56110; reason=None
  - macro_within_level: 0.726099; n=11222; reason=None
  - item_centered: 0.930023; n=56110; reason=None
  - level:L1: 0.844361; n=11222; reason=None
  - level:L2: 0.395678; n=11222; reason=None
  - level:L3: 0.899462; n=11222; reason=None
  - level:L4: 0.775785; n=11222; reason=None
  - level:L5: 0.715210; n=11222; reason=None
  - by_domain:arxiv: 0.942917; n=14685; reason=None
  - by_domain:news: 0.916277; n=14280; reason=None
  - by_domain:patent: 0.910662; n=13800; reason=None
  - by_domain:poetry: 0.922389; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.940547; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.945088; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.865384; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.942318; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.898654; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.628913; pairwise_continuous_alpha_z=0.790518; n=11222; reason=None
  - L2: rho=0.218812; pairwise_continuous_alpha_z=0.170638; n=11222; reason=None
  - L3: rho=0.813558; pairwise_continuous_alpha_z=0.856357; n=11222; reason=None
  - L4: rho=0.686487; pairwise_continuous_alpha_z=0.692669; n=11222; reason=None
  - L5: rho=0.648157; pairwise_continuous_alpha_z=0.663047; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.951269; pairwise_continuous_alpha_z=0.926523; n=14685
  - news: rho=0.893340; pairwise_continuous_alpha_z=0.888345; n=14280
  - patent: rho=0.916427; pairwise_continuous_alpha_z=0.882952; n=13800
  - poetry: rho=0.932910; pairwise_continuous_alpha_z=0.892933; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.935062; pairwise_continuous_alpha_z=0.921627; n=9460
  - claude-sonnet-5: rho=0.929089; pairwise_continuous_alpha_z=0.929551; n=11600
  - gemini-3.6-flash: rho=0.914345; pairwise_continuous_alpha_z=0.822382; n=11200
  - gpt-5.5: rho=0.925964; pairwise_continuous_alpha_z=0.927168; n=12230
  - gpt-5.6-sol: rho=0.891939; pairwise_continuous_alpha_z=0.866480; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.633887; pairwise_continuous_alpha_z=0.767615; n=11222; reason=None
  - L2: rho=0.112742; pairwise_continuous_alpha_z=0.084964; n=11222; reason=None
  - L3: rho=0.829671; pairwise_continuous_alpha_z=0.871280; n=11222; reason=None
  - L4: rho=0.681480; pairwise_continuous_alpha_z=0.686165; n=11222; reason=None
  - L5: rho=0.692566; pairwise_continuous_alpha_z=0.700273; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.950288; pairwise_continuous_alpha_z=0.911241; n=14685
  - news: rho=0.891497; pairwise_continuous_alpha_z=0.868413; n=14280
  - patent: rho=0.908948; pairwise_continuous_alpha_z=0.859158; n=13800
  - poetry: rho=0.928426; pairwise_continuous_alpha_z=0.883934; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.928605; pairwise_continuous_alpha_z=0.909890; n=9460
  - claude-sonnet-5: rho=0.926017; pairwise_continuous_alpha_z=0.914769; n=11600
  - gemini-3.6-flash: rho=0.900851; pairwise_continuous_alpha_z=0.785223; n=11200
  - gpt-5.5: rho=0.920745; pairwise_continuous_alpha_z=0.908348; n=12230
  - gpt-5.6-sol: rho=0.872647; pairwise_continuous_alpha_z=0.841187; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.870769; pairwise_continuous_alpha_z=0.797504; n=14685
  - news: rho=0.917515; pairwise_continuous_alpha_z=0.920354; n=14280
  - patent: rho=0.872194; pairwise_continuous_alpha_z=0.827578; n=13800
  - poetry: rho=0.897176; pairwise_continuous_alpha_z=0.842020; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.911438; pairwise_continuous_alpha_z=0.893633; n=9460
  - claude-sonnet-5: rho=0.917834; pairwise_continuous_alpha_z=0.890228; n=11600
  - gemini-3.6-flash: rho=0.837164; pairwise_continuous_alpha_z=0.689769; n=11200
  - gpt-5.5: rho=0.925878; pairwise_continuous_alpha_z=0.912461; n=12230
  - gpt-5.6-sol: rho=0.904098; pairwise_continuous_alpha_z=0.885803; n=11620
- per-item ordinal: mean Spearman=0.926945; finite Spearman items=11222; mean Kendall tau-b=0.861231; finite tau-b items=11222; strict monotonic=4324/11222 (0.385315); nonstrict monotonic=4324/11222 (0.385315)

## prompt_words

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.241398; pairwise_continuous_alpha_z=0.233941; n=11222; reason=None
  - L2: rho=-0.097600; pairwise_continuous_alpha_z=-0.071643; n=11222; reason=None
  - L3: rho=0.059600; pairwise_continuous_alpha_z=0.028783; n=11222; reason=None
  - L4: rho=0.025071; pairwise_continuous_alpha_z=0.046858; n=11222; reason=None
  - L5: rho=0.314486; pairwise_continuous_alpha_z=0.272575; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.680987; pairwise_continuous_alpha_z=0.622225; n=14685
  - news: rho=0.861660; pairwise_continuous_alpha_z=0.816526; n=14280
  - patent: rho=0.831238; pairwise_continuous_alpha_z=0.798358; n=13800
  - poetry: rho=0.850039; pairwise_continuous_alpha_z=0.826558; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.867335; pairwise_continuous_alpha_z=0.680106; n=9460
  - claude-sonnet-5: rho=0.825607; pairwise_continuous_alpha_z=0.632292; n=11600
  - gemini-3.6-flash: rho=0.874049; pairwise_continuous_alpha_z=0.723387; n=11200
  - gpt-5.5: rho=0.867135; pairwise_continuous_alpha_z=0.661523; n=12230
  - gpt-5.6-sol: rho=0.803987; pairwise_continuous_alpha_z=0.584596; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.242021; pairwise_continuous_alpha_z=0.242124; n=11222; reason=None
  - L2: rho=-0.098077; pairwise_continuous_alpha_z=-0.075435; n=11222; reason=None
  - L3: rho=0.058436; pairwise_continuous_alpha_z=0.039850; n=11222; reason=None
  - L4: rho=0.024974; pairwise_continuous_alpha_z=0.044708; n=11222; reason=None
  - L5: rho=0.313389; pairwise_continuous_alpha_z=0.270308; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.681113; pairwise_continuous_alpha_z=0.654331; n=14685
  - news: rho=0.861619; pairwise_continuous_alpha_z=0.812119; n=14280
  - patent: rho=0.831490; pairwise_continuous_alpha_z=0.838478; n=13800
  - poetry: rho=0.850087; pairwise_continuous_alpha_z=0.856942; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.867494; pairwise_continuous_alpha_z=0.667665; n=9460
  - claude-sonnet-5: rho=0.825608; pairwise_continuous_alpha_z=0.645819; n=11600
  - gemini-3.6-flash: rho=0.873608; pairwise_continuous_alpha_z=0.698260; n=11200
  - gpt-5.5: rho=0.867265; pairwise_continuous_alpha_z=0.662206; n=12230
  - gpt-5.6-sol: rho=0.804064; pairwise_continuous_alpha_z=0.576642; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.742736; n=56110; reason=None
  - macro_within_level: 0.373265; n=11222; reason=None
  - item_centered: 0.799165; n=56110; reason=None
  - level:L1: 0.480124; n=11222; reason=None
  - level:L2: 0.263741; n=11222; reason=None
  - level:L3: 0.342517; n=11222; reason=None
  - level:L4: 0.346219; n=11222; reason=None
  - level:L5: 0.433726; n=11222; reason=None
  - by_domain:arxiv: 0.744178; n=14685; reason=None
  - by_domain:news: 0.873979; n=14280; reason=None
  - by_domain:patent: 0.860852; n=13800; reason=None
  - by_domain:poetry: 0.879851; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.782325; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.750819; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.810264; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.770553; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.718040; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.247271; pairwise_continuous_alpha_z=0.246720; n=11222; reason=None
  - L2: rho=-0.115180; pairwise_continuous_alpha_z=-0.061631; n=11222; reason=None
  - L3: rho=0.103337; pairwise_continuous_alpha_z=0.068282; n=11222; reason=None
  - L4: rho=0.053711; pairwise_continuous_alpha_z=0.073656; n=11222; reason=None
  - L5: rho=0.349189; pairwise_continuous_alpha_z=0.328759; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.681047; pairwise_continuous_alpha_z=0.624241; n=14685
  - news: rho=0.862431; pairwise_continuous_alpha_z=0.824005; n=14280
  - patent: rho=0.835020; pairwise_continuous_alpha_z=0.806904; n=13800
  - poetry: rho=0.850934; pairwise_continuous_alpha_z=0.830824; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.865535; pairwise_continuous_alpha_z=0.680581; n=9460
  - claude-sonnet-5: rho=0.821959; pairwise_continuous_alpha_z=0.640567; n=11600
  - gemini-3.6-flash: rho=0.873873; pairwise_continuous_alpha_z=0.735247; n=11200
  - gpt-5.5: rho=0.862026; pairwise_continuous_alpha_z=0.663559; n=12230
  - gpt-5.6-sol: rho=0.808949; pairwise_continuous_alpha_z=0.592692; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.231677; pairwise_continuous_alpha_z=0.218721; n=11222; reason=None
  - L2: rho=-0.077646; pairwise_continuous_alpha_z=-0.078573; n=11222; reason=None
  - L3: rho=0.013333; pairwise_continuous_alpha_z=-0.011455; n=11222; reason=None
  - L4: rho=-0.006571; pairwise_continuous_alpha_z=0.016499; n=11222; reason=None
  - L5: rho=0.254036; pairwise_continuous_alpha_z=0.190120; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.677162; pairwise_continuous_alpha_z=0.617312; n=14685
  - news: rho=0.857070; pairwise_continuous_alpha_z=0.805861; n=14280
  - patent: rho=0.822895; pairwise_continuous_alpha_z=0.785780; n=13800
  - poetry: rho=0.844997; pairwise_continuous_alpha_z=0.818428; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.864934; pairwise_continuous_alpha_z=0.676278; n=9460
  - claude-sonnet-5: rho=0.824277; pairwise_continuous_alpha_z=0.620955; n=11600
  - gemini-3.6-flash: rho=0.869041; pairwise_continuous_alpha_z=0.707001; n=11200
  - gpt-5.5: rho=0.867450; pairwise_continuous_alpha_z=0.656670; n=12230
  - gpt-5.6-sol: rho=0.796026; pairwise_continuous_alpha_z=0.573141; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.724664; pairwise_continuous_alpha_z=0.699857; n=14685
  - news: rho=0.932170; pairwise_continuous_alpha_z=0.895690; n=14280
  - patent: rho=0.917744; pairwise_continuous_alpha_z=0.929728; n=13800
  - poetry: rho=0.925669; pairwise_continuous_alpha_z=0.933743; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.863219; pairwise_continuous_alpha_z=0.656944; n=9460
  - claude-sonnet-5: rho=0.851989; pairwise_continuous_alpha_z=0.654649; n=11600
  - gemini-3.6-flash: rho=0.877677; pairwise_continuous_alpha_z=0.657990; n=11200
  - gpt-5.5: rho=0.886618; pairwise_continuous_alpha_z=0.660676; n=12230
  - gpt-5.6-sol: rho=0.890085; pairwise_continuous_alpha_z=0.663428; n=11620
- per-item ordinal: mean Spearman=0.870188; finite Spearman items=11222; mean Kendall tau-b=0.767193; finite tau-b items=11222; strict monotonic=0/11222 (0.000000); nonstrict monotonic=0/11222 (0.000000)

## rouge_l_recall

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.908786; pairwise_continuous_alpha_z=0.939670; n=11222; reason=None
  - L2: rho=0.646991; pairwise_continuous_alpha_z=0.665574; n=11222; reason=None
  - L3: rho=0.891487; pairwise_continuous_alpha_z=0.912932; n=11222; reason=None
  - L4: rho=0.863605; pairwise_continuous_alpha_z=0.850708; n=11222; reason=None
  - L5: rho=0.739258; pairwise_continuous_alpha_z=0.693508; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.974451; pairwise_continuous_alpha_z=0.965347; n=14685
  - news: rho=0.979963; pairwise_continuous_alpha_z=0.984177; n=14280
  - patent: rho=0.979637; pairwise_continuous_alpha_z=0.971911; n=13800
  - poetry: rho=0.970924; pairwise_continuous_alpha_z=0.949049; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.974945; pairwise_continuous_alpha_z=0.962022; n=9460
  - claude-sonnet-5: rho=0.976138; pairwise_continuous_alpha_z=0.960321; n=11600
  - gemini-3.6-flash: rho=0.939294; pairwise_continuous_alpha_z=0.931155; n=11200
  - gpt-5.5: rho=0.976490; pairwise_continuous_alpha_z=0.977125; n=12230
  - gpt-5.6-sol: rho=0.962984; pairwise_continuous_alpha_z=0.967308; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.908227; pairwise_continuous_alpha_z=0.928364; n=11222; reason=None
  - L2: rho=0.648197; pairwise_continuous_alpha_z=0.664157; n=11222; reason=None
  - L3: rho=0.891482; pairwise_continuous_alpha_z=0.899248; n=11222; reason=None
  - L4: rho=0.863389; pairwise_continuous_alpha_z=0.828451; n=11222; reason=None
  - L5: rho=0.741809; pairwise_continuous_alpha_z=0.676248; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.974569; pairwise_continuous_alpha_z=0.930492; n=14685
  - news: rho=0.979990; pairwise_continuous_alpha_z=0.957156; n=14280
  - patent: rho=0.979671; pairwise_continuous_alpha_z=0.931175; n=13800
  - poetry: rho=0.970844; pairwise_continuous_alpha_z=0.896713; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.974959; pairwise_continuous_alpha_z=0.923385; n=9460
  - claude-sonnet-5: rho=0.976126; pairwise_continuous_alpha_z=0.925967; n=11600
  - gemini-3.6-flash: rho=0.939007; pairwise_continuous_alpha_z=0.912677; n=11200
  - gpt-5.5: rho=0.976526; pairwise_continuous_alpha_z=0.947341; n=12230
  - gpt-5.6-sol: rho=0.963012; pairwise_continuous_alpha_z=0.936087; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.971751; n=56110; reason=None
  - macro_within_level: 0.838979; n=11222; reason=None
  - item_centered: 0.977400; n=56110; reason=None
  - level:L1: 0.947611; n=11222; reason=None
  - level:L2: 0.747465; n=11222; reason=None
  - level:L3: 0.927746; n=11222; reason=None
  - level:L4: 0.875764; n=11222; reason=None
  - level:L5: 0.696307; n=11222; reason=None
  - by_domain:arxiv: 0.972470; n=14685; reason=None
  - by_domain:news: 0.985507; n=14280; reason=None
  - by_domain:patent: 0.976257; n=13800; reason=None
  - by_domain:poetry: 0.961290; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.969806; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.969078; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.948478; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.980503; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.972420; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.911879; pairwise_continuous_alpha_z=0.943593; n=11222; reason=None
  - L2: rho=0.684453; pairwise_continuous_alpha_z=0.694154; n=11222; reason=None
  - L3: rho=0.879676; pairwise_continuous_alpha_z=0.903573; n=11222; reason=None
  - L4: rho=0.858038; pairwise_continuous_alpha_z=0.847311; n=11222; reason=None
  - L5: rho=0.666911; pairwise_continuous_alpha_z=0.606841; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.971174; pairwise_continuous_alpha_z=0.960318; n=14685
  - news: rho=0.976055; pairwise_continuous_alpha_z=0.981006; n=14280
  - patent: rho=0.976293; pairwise_continuous_alpha_z=0.966866; n=13800
  - poetry: rho=0.968693; pairwise_continuous_alpha_z=0.949882; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.973988; pairwise_continuous_alpha_z=0.959708; n=9460
  - claude-sonnet-5: rho=0.973731; pairwise_continuous_alpha_z=0.958153; n=11600
  - gemini-3.6-flash: rho=0.937517; pairwise_continuous_alpha_z=0.931906; n=11200
  - gpt-5.5: rho=0.975360; pairwise_continuous_alpha_z=0.976042; n=12230
  - gpt-5.6-sol: rho=0.963939; pairwise_continuous_alpha_z=0.966422; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.896023; pairwise_continuous_alpha_z=0.924288; n=11222; reason=None
  - L2: rho=0.592189; pairwise_continuous_alpha_z=0.616792; n=11222; reason=None
  - L3: rho=0.888376; pairwise_continuous_alpha_z=0.908914; n=11222; reason=None
  - L4: rho=0.847668; pairwise_continuous_alpha_z=0.831455; n=11222; reason=None
  - L5: rho=0.708806; pairwise_continuous_alpha_z=0.699769; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.972664; pairwise_continuous_alpha_z=0.966102; n=14685
  - news: rho=0.978881; pairwise_continuous_alpha_z=0.983439; n=14280
  - patent: rho=0.978192; pairwise_continuous_alpha_z=0.972028; n=13800
  - poetry: rho=0.966231; pairwise_continuous_alpha_z=0.943683; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.970304; pairwise_continuous_alpha_z=0.959582; n=9460
  - claude-sonnet-5: rho=0.972392; pairwise_continuous_alpha_z=0.958136; n=11600
  - gemini-3.6-flash: rho=0.934851; pairwise_continuous_alpha_z=0.924975; n=11200
  - gpt-5.5: rho=0.972335; pairwise_continuous_alpha_z=0.974027; n=12230
  - gpt-5.6-sol: rho=0.955518; pairwise_continuous_alpha_z=0.962539; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.908564; pairwise_continuous_alpha_z=0.843749; n=14685
  - news: rho=0.945748; pairwise_continuous_alpha_z=0.920846; n=14280
  - patent: rho=0.914420; pairwise_continuous_alpha_z=0.859879; n=13800
  - poetry: rho=0.923065; pairwise_continuous_alpha_z=0.823555; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.938771; pairwise_continuous_alpha_z=0.906511; n=9460
  - claude-sonnet-5: rho=0.959574; pairwise_continuous_alpha_z=0.900112; n=11600
  - gemini-3.6-flash: rho=0.877202; pairwise_continuous_alpha_z=0.815346; n=11200
  - gpt-5.5: rho=0.966852; pairwise_continuous_alpha_z=0.935243; n=12230
  - gpt-5.6-sol: rho=0.928473; pairwise_continuous_alpha_z=0.918558; n=11620
- per-item ordinal: mean Spearman=0.965022; finite Spearman items=11222; mean Kendall tau-b=0.937761; finite tau-b items=11222; strict monotonic=8327/11222 (0.742025); nonstrict monotonic=8328/11222 (0.742114)

## word_bigram_coverage

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.895084; pairwise_continuous_alpha_z=0.901959; n=11222; reason=None
  - L2: rho=0.526135; pairwise_continuous_alpha_z=0.548170; n=11222; reason=None
  - L3: rho=0.850057; pairwise_continuous_alpha_z=0.885654; n=11222; reason=None
  - L4: rho=0.814804; pairwise_continuous_alpha_z=0.811118; n=11222; reason=None
  - L5: rho=0.236123; pairwise_continuous_alpha_z=0.387067; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.941352; pairwise_continuous_alpha_z=0.915797; n=14685
  - news: rho=0.965147; pairwise_continuous_alpha_z=0.965195; n=14280
  - patent: rho=0.954915; pairwise_continuous_alpha_z=0.932358; n=13800
  - poetry: rho=0.908190; pairwise_continuous_alpha_z=0.852891; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.934826; pairwise_continuous_alpha_z=0.903924; n=9460
  - claude-sonnet-5: rho=0.943093; pairwise_continuous_alpha_z=0.890060; n=11600
  - gemini-3.6-flash: rho=0.848578; pairwise_continuous_alpha_z=0.831189; n=11200
  - gpt-5.5: rho=0.955244; pairwise_continuous_alpha_z=0.939617; n=12230
  - gpt-5.6-sol: rho=0.931428; pairwise_continuous_alpha_z=0.923481; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.894560; pairwise_continuous_alpha_z=0.874047; n=11222; reason=None
  - L2: rho=0.527581; pairwise_continuous_alpha_z=0.545530; n=11222; reason=None
  - L3: rho=0.849959; pairwise_continuous_alpha_z=0.870214; n=11222; reason=None
  - L4: rho=0.814576; pairwise_continuous_alpha_z=0.787999; n=11222; reason=None
  - L5: rho=0.233799; pairwise_continuous_alpha_z=0.374901; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.941462; pairwise_continuous_alpha_z=0.872196; n=14685
  - news: rho=0.965215; pairwise_continuous_alpha_z=0.923322; n=14280
  - patent: rho=0.955090; pairwise_continuous_alpha_z=0.877990; n=13800
  - poetry: rho=0.908148; pairwise_continuous_alpha_z=0.776204; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.934855; pairwise_continuous_alpha_z=0.854750; n=9460
  - claude-sonnet-5: rho=0.943091; pairwise_continuous_alpha_z=0.845573; n=11600
  - gemini-3.6-flash: rho=0.848594; pairwise_continuous_alpha_z=0.813073; n=11200
  - gpt-5.5: rho=0.955272; pairwise_continuous_alpha_z=0.894009; n=12230
  - gpt-5.6-sol: rho=0.931580; pairwise_continuous_alpha_z=0.874656; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.936351; n=56110; reason=None
  - macro_within_level: 0.771140; n=11222; reason=None
  - item_centered: 0.942811; n=56110; reason=None
  - level:L1: 0.922606; n=11222; reason=None
  - level:L2: 0.670615; n=11222; reason=None
  - level:L3: 0.909687; n=11222; reason=None
  - level:L4: 0.849752; n=11222; reason=None
  - level:L5: 0.503041; n=11222; reason=None
  - by_domain:arxiv: 0.939551; n=14685; reason=None
  - by_domain:news: 0.972870; n=14280; reason=None
  - by_domain:patent: 0.949952; n=13800; reason=None
  - by_domain:poetry: 0.897336; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.931166; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.922359; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.882085; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.955545; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.943281; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.899000; pairwise_continuous_alpha_z=0.904248; n=11222; reason=None
  - L2: rho=0.572784; pairwise_continuous_alpha_z=0.581770; n=11222; reason=None
  - L3: rho=0.840258; pairwise_continuous_alpha_z=0.879087; n=11222; reason=None
  - L4: rho=0.808343; pairwise_continuous_alpha_z=0.806792; n=11222; reason=None
  - L5: rho=0.178845; pairwise_continuous_alpha_z=0.297409; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.936982; pairwise_continuous_alpha_z=0.906353; n=14685
  - news: rho=0.961145; pairwise_continuous_alpha_z=0.958486; n=14280
  - patent: rho=0.949210; pairwise_continuous_alpha_z=0.920901; n=13800
  - poetry: rho=0.902964; pairwise_continuous_alpha_z=0.853603; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.935385; pairwise_continuous_alpha_z=0.900222; n=9460
  - claude-sonnet-5: rho=0.941489; pairwise_continuous_alpha_z=0.885574; n=11600
  - gemini-3.6-flash: rho=0.841999; pairwise_continuous_alpha_z=0.825517; n=11200
  - gpt-5.5: rho=0.952984; pairwise_continuous_alpha_z=0.935384; n=12230
  - gpt-5.6-sol: rho=0.931290; pairwise_continuous_alpha_z=0.919902; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.881725; pairwise_continuous_alpha_z=0.888620; n=11222; reason=None
  - L2: rho=0.466968; pairwise_continuous_alpha_z=0.498629; n=11222; reason=None
  - L3: rho=0.845922; pairwise_continuous_alpha_z=0.879223; n=11222; reason=None
  - L4: rho=0.800737; pairwise_continuous_alpha_z=0.793941; n=11222; reason=None
  - L5: rho=0.252395; pairwise_continuous_alpha_z=0.429412; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.941557; pairwise_continuous_alpha_z=0.921312; n=14685
  - news: rho=0.964977; pairwise_continuous_alpha_z=0.968049; n=14280
  - patent: rho=0.956065; pairwise_continuous_alpha_z=0.939078; n=13800
  - poetry: rho=0.907650; pairwise_continuous_alpha_z=0.848106; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.929731; pairwise_continuous_alpha_z=0.903153; n=9460
  - claude-sonnet-5: rho=0.939324; pairwise_continuous_alpha_z=0.890562; n=11600
  - gemini-3.6-flash: rho=0.852354; pairwise_continuous_alpha_z=0.832188; n=11200
  - gpt-5.5: rho=0.952955; pairwise_continuous_alpha_z=0.939813; n=12230
  - gpt-5.6-sol: rho=0.926466; pairwise_continuous_alpha_z=0.921643; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.909873; pairwise_continuous_alpha_z=0.813544; n=14685
  - news: rho=0.931355; pairwise_continuous_alpha_z=0.876752; n=14280
  - patent: rho=0.903203; pairwise_continuous_alpha_z=0.814944; n=13800
  - poetry: rho=0.879584; pairwise_continuous_alpha_z=0.713872; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.904819; pairwise_continuous_alpha_z=0.847627; n=9460
  - claude-sonnet-5: rho=0.927453; pairwise_continuous_alpha_z=0.827052; n=11600
  - gemini-3.6-flash: rho=0.873409; pairwise_continuous_alpha_z=0.771422; n=11200
  - gpt-5.5: rho=0.950588; pairwise_continuous_alpha_z=0.885185; n=12230
  - gpt-5.6-sol: rho=0.903174; pairwise_continuous_alpha_z=0.854847; n=11620
- per-item ordinal: mean Spearman=0.951330; finite Spearman items=11222; mean Kendall tau-b=0.913127; finite tau-b items=11222; strict monotonic=7071/11222 (0.630102); nonstrict monotonic=7080/11222 (0.630904)

## word_token_coverage

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.885525; pairwise_continuous_alpha_z=0.919992; n=11222; reason=None
  - L2: rho=0.460153; pairwise_continuous_alpha_z=0.498360; n=11222; reason=None
  - L3: rho=0.863600; pairwise_continuous_alpha_z=0.897348; n=11222; reason=None
  - L4: rho=0.825496; pairwise_continuous_alpha_z=0.819604; n=11222; reason=None
  - L5: rho=0.758485; pairwise_continuous_alpha_z=0.740416; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.972530; pairwise_continuous_alpha_z=0.974799; n=14685
  - news: rho=0.972776; pairwise_continuous_alpha_z=0.969707; n=14280
  - patent: rho=0.975900; pairwise_continuous_alpha_z=0.973717; n=13800
  - poetry: rho=0.966520; pairwise_continuous_alpha_z=0.968486; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.973699; pairwise_continuous_alpha_z=0.970478; n=9460
  - claude-sonnet-5: rho=0.970256; pairwise_continuous_alpha_z=0.968397; n=11600
  - gemini-3.6-flash: rho=0.934503; pairwise_continuous_alpha_z=0.921507; n=11200
  - gpt-5.5: rho=0.974444; pairwise_continuous_alpha_z=0.978221; n=12230
  - gpt-5.6-sol: rho=0.958381; pairwise_continuous_alpha_z=0.968347; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.884981; pairwise_continuous_alpha_z=0.917186; n=11222; reason=None
  - L2: rho=0.461395; pairwise_continuous_alpha_z=0.497184; n=11222; reason=None
  - L3: rho=0.863606; pairwise_continuous_alpha_z=0.885095; n=11222; reason=None
  - L4: rho=0.825240; pairwise_continuous_alpha_z=0.805959; n=11222; reason=None
  - L5: rho=0.760779; pairwise_continuous_alpha_z=0.717683; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.972642; pairwise_continuous_alpha_z=0.953582; n=14685
  - news: rho=0.972766; pairwise_continuous_alpha_z=0.965977; n=14280
  - patent: rho=0.975918; pairwise_continuous_alpha_z=0.948408; n=13800
  - poetry: rho=0.966441; pairwise_continuous_alpha_z=0.935555; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.973729; pairwise_continuous_alpha_z=0.945091; n=9460
  - claude-sonnet-5: rho=0.970246; pairwise_continuous_alpha_z=0.947635; n=11600
  - gemini-3.6-flash: rho=0.934113; pairwise_continuous_alpha_z=0.914721; n=11200
  - gpt-5.5: rho=0.974488; pairwise_continuous_alpha_z=0.963288; n=12230
  - gpt-5.6-sol: rho=0.958375; pairwise_continuous_alpha_z=0.955241; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.972448; n=56110; reason=None
  - macro_within_level: 0.814257; n=11222; reason=None
  - item_centered: 0.980785; n=56110; reason=None
  - level:L1: 0.934600; n=11222; reason=None
  - level:L2: 0.638093; n=11222; reason=None
  - level:L3: 0.917433; n=11222; reason=None
  - level:L4: 0.855320; n=11222; reason=None
  - level:L5: 0.725838; n=11222; reason=None
  - by_domain:arxiv: 0.978732; n=14685; reason=None
  - by_domain:news: 0.975889; n=14280; reason=None
  - by_domain:patent: 0.977459; n=13800; reason=None
  - by_domain:poetry: 0.974218; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.975432; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.974429; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.942026; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.981236; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.973118; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.888415; pairwise_continuous_alpha_z=0.926156; n=11222; reason=None
  - L2: rho=0.503099; pairwise_continuous_alpha_z=0.537680; n=11222; reason=None
  - L3: rho=0.853064; pairwise_continuous_alpha_z=0.888017; n=11222; reason=None
  - L4: rho=0.820316; pairwise_continuous_alpha_z=0.815744; n=11222; reason=None
  - L5: rho=0.685503; pairwise_continuous_alpha_z=0.651519; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.969347; pairwise_continuous_alpha_z=0.972502; n=14685
  - news: rho=0.969708; pairwise_continuous_alpha_z=0.971938; n=14280
  - patent: rho=0.972985; pairwise_continuous_alpha_z=0.971571; n=13800
  - poetry: rho=0.964463; pairwise_continuous_alpha_z=0.969536; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.972752; pairwise_continuous_alpha_z=0.970473; n=9460
  - claude-sonnet-5: rho=0.968366; pairwise_continuous_alpha_z=0.969378; n=11600
  - gemini-3.6-flash: rho=0.934447; pairwise_continuous_alpha_z=0.926386; n=11200
  - gpt-5.5: rho=0.973313; pairwise_continuous_alpha_z=0.979648; n=12230
  - gpt-5.6-sol: rho=0.961011; pairwise_continuous_alpha_z=0.970918; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.873248; pairwise_continuous_alpha_z=0.902691; n=11222; reason=None
  - L2: rho=0.406556; pairwise_continuous_alpha_z=0.445157; n=11222; reason=None
  - L3: rho=0.859714; pairwise_continuous_alpha_z=0.893531; n=11222; reason=None
  - L4: rho=0.810037; pairwise_continuous_alpha_z=0.801692; n=11222; reason=None
  - L5: rho=0.725911; pairwise_continuous_alpha_z=0.743683; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.970671; pairwise_continuous_alpha_z=0.972703; n=14685
  - news: rho=0.970873; pairwise_continuous_alpha_z=0.963654; n=14280
  - patent: rho=0.973979; pairwise_continuous_alpha_z=0.970929; n=13800
  - poetry: rho=0.961848; pairwise_continuous_alpha_z=0.962815; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.969032; pairwise_continuous_alpha_z=0.965697; n=9460
  - claude-sonnet-5: rho=0.965963; pairwise_continuous_alpha_z=0.962964; n=11600
  - gemini-3.6-flash: rho=0.928237; pairwise_continuous_alpha_z=0.911140; n=11200
  - gpt-5.5: rho=0.970308; pairwise_continuous_alpha_z=0.972621; n=12230
  - gpt-5.6-sol: rho=0.949425; pairwise_continuous_alpha_z=0.960138; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.912135; pairwise_continuous_alpha_z=0.871529; n=14685
  - news: rho=0.960254; pairwise_continuous_alpha_z=0.957378; n=14280
  - patent: rho=0.924348; pairwise_continuous_alpha_z=0.894451; n=13800
  - poetry: rho=0.931940; pairwise_continuous_alpha_z=0.874338; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.944397; pairwise_continuous_alpha_z=0.930104; n=9460
  - claude-sonnet-5: rho=0.957658; pairwise_continuous_alpha_z=0.927230; n=11600
  - gemini-3.6-flash: rho=0.875678; pairwise_continuous_alpha_z=0.826487; n=11200
  - gpt-5.5: rho=0.967529; pairwise_continuous_alpha_z=0.951195; n=12230
  - gpt-5.6-sol: rho=0.944112; pairwise_continuous_alpha_z=0.945128; n=11620
- per-item ordinal: mean Spearman=0.971186; finite Spearman items=11222; mean Kendall tau-b=0.947843; finite tau-b items=11222; strict monotonic=8692/11222 (0.774550); nonstrict monotonic=8694/11222 (0.774728)

## word_type_coverage

### Reference: consensus_global_z
- per_level:
  - L1: rho=0.904094; pairwise_continuous_alpha_z=0.935792; n=11222; reason=None
  - L2: rho=0.495349; pairwise_continuous_alpha_z=0.525968; n=11222; reason=None
  - L3: rho=0.867507; pairwise_continuous_alpha_z=0.896136; n=11222; reason=None
  - L4: rho=0.867301; pairwise_continuous_alpha_z=0.858728; n=11222; reason=None
  - L5: rho=0.777653; pairwise_continuous_alpha_z=0.757686; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.965680; pairwise_continuous_alpha_z=0.962392; n=14685
  - news: rho=0.973651; pairwise_continuous_alpha_z=0.974352; n=14280
  - patent: rho=0.972322; pairwise_continuous_alpha_z=0.969467; n=13800
  - poetry: rho=0.952525; pairwise_continuous_alpha_z=0.944674; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.960776; pairwise_continuous_alpha_z=0.959220; n=9460
  - claude-sonnet-5: rho=0.968663; pairwise_continuous_alpha_z=0.957582; n=11600
  - gemini-3.6-flash: rho=0.916991; pairwise_continuous_alpha_z=0.919662; n=11200
  - gpt-5.5: rho=0.969996; pairwise_continuous_alpha_z=0.970043; n=12230
  - gpt-5.6-sol: rho=0.953331; pairwise_continuous_alpha_z=0.961880; n=11620

### Reference: consensus_midrank_percentile
- per_level:
  - L1: rho=0.903304; pairwise_continuous_alpha_z=0.921312; n=11222; reason=None
  - L2: rho=0.496348; pairwise_continuous_alpha_z=0.523497; n=11222; reason=None
  - L3: rho=0.867412; pairwise_continuous_alpha_z=0.886818; n=11222; reason=None
  - L4: rho=0.867009; pairwise_continuous_alpha_z=0.852904; n=11222; reason=None
  - L5: rho=0.779134; pairwise_continuous_alpha_z=0.741429; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.965789; pairwise_continuous_alpha_z=0.951253; n=14685
  - news: rho=0.973668; pairwise_continuous_alpha_z=0.971210; n=14280
  - patent: rho=0.972415; pairwise_continuous_alpha_z=0.946825; n=13800
  - poetry: rho=0.952472; pairwise_continuous_alpha_z=0.909302; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.960752; pairwise_continuous_alpha_z=0.941252; n=9460
  - claude-sonnet-5: rho=0.968642; pairwise_continuous_alpha_z=0.943909; n=11600
  - gemini-3.6-flash: rho=0.916815; pairwise_continuous_alpha_z=0.923382; n=11200
  - gpt-5.5: rho=0.970032; pairwise_continuous_alpha_z=0.956364; n=12230
  - gpt-5.6-sol: rho=0.953373; pairwise_continuous_alpha_z=0.946140; n=11620

- `joint_reference_continuous_alpha_z`:
  - pooled: 0.967100; n=56110; reason=None
  - macro_within_level: 0.827093; n=11222; reason=None
  - item_centered: 0.975309; n=56110; reason=None
  - level:L1: 0.945025; n=11222; reason=None
  - level:L2: 0.656032; n=11222; reason=None
  - level:L3: 0.916625; n=11222; reason=None
  - level:L4: 0.881127; n=11222; reason=None
  - level:L5: 0.736658; n=11222; reason=None
  - by_domain:arxiv: 0.970507; n=14685; reason=None
  - by_domain:news: 0.978975; n=14280; reason=None
  - by_domain:patent: 0.974631; n=13800; reason=None
  - by_domain:poetry: 0.958372; n=13345; reason=None
  - by_generation_model:claude-opus-4-8: 0.967943; n=9460; reason=None
  - by_generation_model:claude-sonnet-5: 0.967250; n=11600; reason=None
  - by_generation_model:gemini-3.6-flash: 0.940862; n=11200; reason=None
  - by_generation_model:gpt-5.5: 0.975792; n=12230; reason=None
  - by_generation_model:gpt-5.6-sol: 0.968813; n=11620; reason=None
### Reference: phi_actual_llama
- per_level:
  - L1: rho=0.903947; pairwise_continuous_alpha_z=0.938225; n=11222; reason=None
  - L2: rho=0.533230; pairwise_continuous_alpha_z=0.558337; n=11222; reason=None
  - L3: rho=0.857153; pairwise_continuous_alpha_z=0.889173; n=11222; reason=None
  - L4: rho=0.860346; pairwise_continuous_alpha_z=0.852234; n=11222; reason=None
  - L5: rho=0.701297; pairwise_continuous_alpha_z=0.665349; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.961491; pairwise_continuous_alpha_z=0.957032; n=14685
  - news: rho=0.969692; pairwise_continuous_alpha_z=0.973762; n=14280
  - patent: rho=0.966992; pairwise_continuous_alpha_z=0.961825; n=13800
  - poetry: rho=0.949432; pairwise_continuous_alpha_z=0.944494; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.959917; pairwise_continuous_alpha_z=0.957527; n=9460
  - claude-sonnet-5: rho=0.966771; pairwise_continuous_alpha_z=0.956429; n=11600
  - gemini-3.6-flash: rho=0.913705; pairwise_continuous_alpha_z=0.917722; n=11200
  - gpt-5.5: rho=0.969272; pairwise_continuous_alpha_z=0.969272; n=12230
  - gpt-5.6-sol: rho=0.954038; pairwise_continuous_alpha_z=0.961747; n=11620

### Reference: phi_actual_mixtral
- per_level:
  - L1: rho=0.894141; pairwise_continuous_alpha_z=0.921897; n=11222; reason=None
  - L2: rho=0.444645; pairwise_continuous_alpha_z=0.478313; n=11222; reason=None
  - L3: rho=0.863325; pairwise_continuous_alpha_z=0.889950; n=11222; reason=None
  - L4: rho=0.852626; pairwise_continuous_alpha_z=0.842622; n=11222; reason=None
  - L5: rho=0.746829; pairwise_continuous_alpha_z=0.762315; n=11222; reason=None
- by_domain:
  - arxiv: rho=0.964973; pairwise_continuous_alpha_z=0.963500; n=14685
  - news: rho=0.972680; pairwise_continuous_alpha_z=0.971085; n=14280
  - patent: rho=0.972924; pairwise_continuous_alpha_z=0.972190; n=13800
  - poetry: rho=0.949051; pairwise_continuous_alpha_z=0.940320; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.956221; pairwise_continuous_alpha_z=0.956176; n=9460
  - claude-sonnet-5: rho=0.964385; pairwise_continuous_alpha_z=0.954376; n=11600
  - gemini-3.6-flash: rho=0.915031; pairwise_continuous_alpha_z=0.916313; n=11200
  - gpt-5.5: rho=0.965523; pairwise_continuous_alpha_z=0.966664; n=12230
  - gpt-5.6-sol: rho=0.946540; pairwise_continuous_alpha_z=0.956395; n=11620

### Reference: treatment_ordinal
- per_level:
  - L1: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L2: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L3: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L4: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
  - L5: rho=NA; pairwise_continuous_alpha_z=NA; n=11222; reason=reference_constant_within_level
- by_domain:
  - arxiv: rho=0.918710; pairwise_continuous_alpha_z=0.898409; n=14685
  - news: rho=0.938571; pairwise_continuous_alpha_z=0.937831; n=14280
  - patent: rho=0.896661; pairwise_continuous_alpha_z=0.866345; n=13800
  - poetry: rho=0.922670; pairwise_continuous_alpha_z=0.856595; n=13345
- by_generation_model:
  - claude-opus-4-8: rho=0.925915; pairwise_continuous_alpha_z=0.916921; n=9460
  - claude-sonnet-5: rho=0.948935; pairwise_continuous_alpha_z=0.922335; n=11600
  - gemini-3.6-flash: rho=0.891729; pairwise_continuous_alpha_z=0.872094; n=11200
  - gpt-5.5: rho=0.957507; pairwise_continuous_alpha_z=0.948885; n=12230
  - gpt-5.6-sol: rho=0.921191; pairwise_continuous_alpha_z=0.921328; n=11620
- per-item ordinal: mean Spearman=0.968226; finite Spearman items=11222; mean Kendall tau-b=0.941361; finite tau-b items=11222; strict monotonic=8299/11222 (0.739529); nonstrict monotonic=8304/11222 (0.739975)

## Compact word-length residualization sensitivity

### word_L_out
- G_raw_bits: classification=stable_positive; relative_to_unadjusted=persists
  - `length_delta|word_L_out|phi_actual_llama|R_actual-minus-G_raw_bits|macro_within_level|rho`: point=0.369831; CI=[0.361347, 0.378121]
  - `length_delta|word_L_out|phi_actual_llama|R_actual-minus-G_raw_bits|macro_within_level|pairwise_continuous_alpha_z`: point=0.370940; CI=[0.361945, 0.380212]
  - `length_delta|word_L_out|phi_actual_llama|R_actual-minus-G_raw_bits|item_centered|rho`: point=0.055215; CI=[0.052735, 0.057999]
  - `length_delta|word_L_out|phi_actual_llama|R_actual-minus-G_raw_bits|item_centered|pairwise_continuous_alpha_z`: point=0.087470; CI=[0.084524, 0.090463]
  - `length_delta|word_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits|macro_within_level|rho`: point=0.368722; CI=[0.360181, 0.377338]
  - `length_delta|word_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits|macro_within_level|pairwise_continuous_alpha_z`: point=0.367925; CI=[0.358714, 0.377104]
  - `length_delta|word_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits|item_centered|rho`: point=0.057357; CI=[0.055000, 0.059880]
  - `length_delta|word_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits|item_centered|pairwise_continuous_alpha_z`: point=0.090864; CI=[0.087783, 0.093835]
- G_raw_bits_per_output_byte: classification=stable_positive; relative_to_unadjusted=persists
  - `length_delta|word_L_out|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|rho`: point=0.072220; CI=[0.067230, 0.077104]
  - `length_delta|word_L_out|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|pairwise_continuous_alpha_z`: point=0.086813; CI=[0.081330, 0.092476]
  - `length_delta|word_L_out|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|item_centered|rho`: point=0.001602; CI=[0.001053, 0.002163]
  - `length_delta|word_L_out|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|item_centered|pairwise_continuous_alpha_z`: point=0.008077; CI=[0.007381, 0.008811]
  - `length_delta|word_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|rho`: point=0.072706; CI=[0.067367, 0.078165]
  - `length_delta|word_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|pairwise_continuous_alpha_z`: point=0.100501; CI=[0.094458, 0.106395]
  - `length_delta|word_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|item_centered|rho`: point=0.003510; CI=[0.002920, 0.004089]
  - `length_delta|word_L_out|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|item_centered|pairwise_continuous_alpha_z`: point=0.010667; CI=[0.009872, 0.011469]

### word_L_full
- G_raw_bits: classification=stable_positive; relative_to_unadjusted=persists
  - `length_delta|word_L_full|phi_actual_llama|R_actual-minus-G_raw_bits|macro_within_level|rho`: point=0.233798; CI=[0.225995, 0.241213]
  - `length_delta|word_L_full|phi_actual_llama|R_actual-minus-G_raw_bits|macro_within_level|pairwise_continuous_alpha_z`: point=0.219902; CI=[0.211996, 0.227851]
  - `length_delta|word_L_full|phi_actual_llama|R_actual-minus-G_raw_bits|item_centered|rho`: point=0.131320; CI=[0.126626, 0.135865]
  - `length_delta|word_L_full|phi_actual_llama|R_actual-minus-G_raw_bits|item_centered|pairwise_continuous_alpha_z`: point=0.130891; CI=[0.125571, 0.135827]
  - `length_delta|word_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits|macro_within_level|rho`: point=0.261387; CI=[0.252766, 0.269530]
  - `length_delta|word_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits|macro_within_level|pairwise_continuous_alpha_z`: point=0.246609; CI=[0.237704, 0.254929]
  - `length_delta|word_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits|item_centered|rho`: point=0.147282; CI=[0.141869, 0.152548]
  - `length_delta|word_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits|item_centered|pairwise_continuous_alpha_z`: point=0.139408; CI=[0.132844, 0.145145]
- G_raw_bits_per_output_byte: classification=stable_positive; relative_to_unadjusted=persists
  - `length_delta|word_L_full|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|rho`: point=0.143447; CI=[0.135789, 0.151109]
  - `length_delta|word_L_full|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|pairwise_continuous_alpha_z`: point=0.141388; CI=[0.133180, 0.149633]
  - `length_delta|word_L_full|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|item_centered|rho`: point=0.035928; CI=[0.032761, 0.039353]
  - `length_delta|word_L_full|phi_actual_llama|R_actual-minus-G_raw_bits_per_output_byte|item_centered|pairwise_continuous_alpha_z`: point=0.035684; CI=[0.032436, 0.039188]
  - `length_delta|word_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|rho`: point=0.158988; CI=[0.150334, 0.168086]
  - `length_delta|word_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|macro_within_level|pairwise_continuous_alpha_z`: point=0.155538; CI=[0.147159, 0.164535]
  - `length_delta|word_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|item_centered|rho`: point=0.043358; CI=[0.039671, 0.047231]
  - `length_delta|word_L_full|phi_actual_mixtral|R_actual-minus-G_raw_bits_per_output_byte|item_centered|pairwise_continuous_alpha_z`: point=0.042686; CI=[0.039007, 0.046809]

## Common-support coverage cells

```json
{
  "adjacent_byte_calipers": {
    "1.10": {
      "L1-L2": {
        "domain_items": {
          "arxiv": 1355,
          "news": 2250,
          "patent": 1306,
          "poetry": 562
        },
        "generation_model_items": {
          "claude-opus-4-8": 1015,
          "claude-sonnet-5": 1045,
          "gemini-3.6-flash": 209,
          "gpt-5.5": 1705,
          "gpt-5.6-sol": 1499
        },
        "methods": {
          "G": {
            "expected": 5446,
            "expected_rate": 0.9950666910286863,
            "mean_higher_minus_lower": 1774.176259211889,
            "median_higher_minus_lower": 1336.000000000001,
            "n": 5473,
            "reverse": 26,
            "reverse_rate": 0.004750593824228029,
            "tie": 1,
            "tie_rate": 0.0001827151470856934
          },
          "Llama": {
            "expected": 5422,
            "expected_rate": 0.9906815274986296,
            "mean_higher_minus_lower": 0.20347375276725257,
            "median_higher_minus_lower": 0.2029970674933187,
            "n": 5473,
            "reverse": 51,
            "reverse_rate": 0.009318472501370363,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 5428,
            "expected_rate": 0.9917778183811438,
            "mean_higher_minus_lower": 0.23090708027014825,
            "median_higher_minus_lower": 0.22782536937981818,
            "n": 5473,
            "reverse": 45,
            "reverse_rate": 0.008222181618856203,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 5449,
            "expected_rate": 0.9956148364699433,
            "mean_higher_minus_lower": 0.24089366430516984,
            "median_higher_minus_lower": 0.23720979353535288,
            "n": 5473,
            "reverse": 24,
            "reverse_rate": 0.004385163530056642,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 5473,
        "source_clusters": 2219
      },
      "L2-L3": {
        "domain_items": {
          "arxiv": 67,
          "news": 174,
          "patent": 192,
          "poetry": 208
        },
        "generation_model_items": {
          "claude-opus-4-8": 26,
          "claude-sonnet-5": 112,
          "gemini-3.6-flash": 100,
          "gpt-5.5": 36,
          "gpt-5.6-sol": 367
        },
        "methods": {
          "G": {
            "expected": 313,
            "expected_rate": 0.48829953198127923,
            "mean_higher_minus_lower": 358.1029641185648,
            "median_higher_minus_lower": -29.333333333333485,
            "n": 641,
            "reverse": 328,
            "reverse_rate": 0.5117004680187207,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Llama": {
            "expected": 525,
            "expected_rate": 0.8190327613104524,
            "mean_higher_minus_lower": 0.11343960184395749,
            "median_higher_minus_lower": 0.1218006887288845,
            "n": 641,
            "reverse": 116,
            "reverse_rate": 0.1809672386895476,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 471,
            "expected_rate": 0.734789391575663,
            "mean_higher_minus_lower": 0.07860225023403442,
            "median_higher_minus_lower": 0.08958344044379463,
            "n": 641,
            "reverse": 170,
            "reverse_rate": 0.26521060842433697,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 297,
            "expected_rate": 0.46333853354134164,
            "mean_higher_minus_lower": 0.002890079687928301,
            "median_higher_minus_lower": -0.007912302075985922,
            "n": 641,
            "reverse": 344,
            "reverse_rate": 0.5366614664586583,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 641,
        "source_clusters": 601
      },
      "L3-L4": {
        "domain_items": {
          "arxiv": 234,
          "news": 391,
          "patent": 143,
          "poetry": 354
        },
        "generation_model_items": {
          "claude-opus-4-8": 223,
          "claude-sonnet-5": 348,
          "gemini-3.6-flash": 66,
          "gpt-5.5": 389,
          "gpt-5.6-sol": 96
        },
        "methods": {
          "G": {
            "expected": 1096,
            "expected_rate": 0.9768270944741533,
            "mean_higher_minus_lower": 608.0617944147356,
            "median_higher_minus_lower": 573.3333333333331,
            "n": 1122,
            "reverse": 26,
            "reverse_rate": 0.023172905525846704,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Llama": {
            "expected": 1105,
            "expected_rate": 0.9848484848484849,
            "mean_higher_minus_lower": 0.12239135016123587,
            "median_higher_minus_lower": 0.11584891211088814,
            "n": 1122,
            "reverse": 17,
            "reverse_rate": 0.015151515151515152,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 1105,
            "expected_rate": 0.9848484848484849,
            "mean_higher_minus_lower": 0.11940040281741487,
            "median_higher_minus_lower": 0.10968554091349231,
            "n": 1122,
            "reverse": 17,
            "reverse_rate": 0.015151515151515152,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 1092,
            "expected_rate": 0.9732620320855615,
            "mean_higher_minus_lower": 0.06905545209700555,
            "median_higher_minus_lower": 0.06081761960234247,
            "n": 1122,
            "reverse": 30,
            "reverse_rate": 0.026737967914438502,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 1122,
        "source_clusters": 936
      },
      "L4-L5": {
        "domain_items": {
          "arxiv": 73,
          "news": 185,
          "patent": 26,
          "poetry": 87
        },
        "generation_model_items": {
          "claude-opus-4-8": 137,
          "claude-sonnet-5": 107,
          "gemini-3.6-flash": 44,
          "gpt-5.5": 43,
          "gpt-5.6-sol": 40
        },
        "methods": {
          "G": {
            "expected": 371,
            "expected_rate": 1.0,
            "mean_higher_minus_lower": 1203.3782569631626,
            "median_higher_minus_lower": 1253.333333333333,
            "n": 371,
            "reverse": 0,
            "reverse_rate": 0.0,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Llama": {
            "expected": 367,
            "expected_rate": 0.9892183288409704,
            "mean_higher_minus_lower": 0.14156914168856982,
            "median_higher_minus_lower": 0.14491846867159708,
            "n": 371,
            "reverse": 4,
            "reverse_rate": 0.01078167115902965,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 365,
            "expected_rate": 0.9838274932614556,
            "mean_higher_minus_lower": 0.13195190610364718,
            "median_higher_minus_lower": 0.13199505713514065,
            "n": 371,
            "reverse": 6,
            "reverse_rate": 0.016172506738544475,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 371,
            "expected_rate": 1.0,
            "mean_higher_minus_lower": 0.13612540388978178,
            "median_higher_minus_lower": 0.13958155975135933,
            "n": 371,
            "reverse": 0,
            "reverse_rate": 0.0,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 371,
        "source_clusters": 326
      }
    },
    "1.20": {
      "L1-L2": {
        "domain_items": {
          "arxiv": 1822,
          "news": 2599,
          "patent": 1804,
          "poetry": 1455
        },
        "generation_model_items": {
          "claude-opus-4-8": 1365,
          "claude-sonnet-5": 1615,
          "gemini-3.6-flash": 404,
          "gpt-5.5": 2237,
          "gpt-5.6-sol": 2059
        },
        "methods": {
          "G": {
            "expected": 7636,
            "expected_rate": 0.9942708333333333,
            "mean_higher_minus_lower": 1692.7868055555557,
            "median_higher_minus_lower": 1324.0,
            "n": 7680,
            "reverse": 43,
            "reverse_rate": 0.005598958333333333,
            "tie": 1,
            "tie_rate": 0.00013020833333333333
          },
          "Llama": {
            "expected": 7570,
            "expected_rate": 0.9856770833333334,
            "mean_higher_minus_lower": 0.2055082136006223,
            "median_higher_minus_lower": 0.20544112161119582,
            "n": 7680,
            "reverse": 110,
            "reverse_rate": 0.014322916666666666,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 7585,
            "expected_rate": 0.9876302083333334,
            "mean_higher_minus_lower": 0.2308823767559837,
            "median_higher_minus_lower": 0.2312609102578006,
            "n": 7680,
            "reverse": 95,
            "reverse_rate": 0.012369791666666666,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 7639,
            "expected_rate": 0.9946614583333333,
            "mean_higher_minus_lower": 0.2504249949544196,
            "median_higher_minus_lower": 0.2439770663351616,
            "n": 7680,
            "reverse": 41,
            "reverse_rate": 0.005338541666666667,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 7680,
        "source_clusters": 2493
      },
      "L2-L3": {
        "domain_items": {
          "arxiv": 123,
          "news": 346,
          "patent": 363,
          "poetry": 415
        },
        "generation_model_items": {
          "claude-opus-4-8": 59,
          "claude-sonnet-5": 227,
          "gemini-3.6-flash": 206,
          "gpt-5.5": 75,
          "gpt-5.6-sol": 680
        },
        "methods": {
          "G": {
            "expected": 601,
            "expected_rate": 0.48195669607056935,
            "mean_higher_minus_lower": 392.8896017107725,
            "median_higher_minus_lower": -37.33333333333326,
            "n": 1247,
            "reverse": 646,
            "reverse_rate": 0.5180433039294307,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Llama": {
            "expected": 1032,
            "expected_rate": 0.8275862068965517,
            "mean_higher_minus_lower": 0.11842433480558161,
            "median_higher_minus_lower": 0.1323135132571911,
            "n": 1247,
            "reverse": 215,
            "reverse_rate": 0.1724137931034483,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 931,
            "expected_rate": 0.7465918203688853,
            "mean_higher_minus_lower": 0.08511536510599808,
            "median_higher_minus_lower": 0.09821683350934957,
            "n": 1247,
            "reverse": 316,
            "reverse_rate": 0.25340817963111467,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 599,
            "expected_rate": 0.48035284683239776,
            "mean_higher_minus_lower": 0.00563743726073706,
            "median_higher_minus_lower": -0.006377764966633864,
            "n": 1247,
            "reverse": 648,
            "reverse_rate": 0.5196471531676022,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 1247,
        "source_clusters": 1073
      },
      "L3-L4": {
        "domain_items": {
          "arxiv": 446,
          "news": 730,
          "patent": 296,
          "poetry": 671
        },
        "generation_model_items": {
          "claude-opus-4-8": 461,
          "claude-sonnet-5": 622,
          "gemini-3.6-flash": 129,
          "gpt-5.5": 749,
          "gpt-5.6-sol": 182
        },
        "methods": {
          "G": {
            "expected": 2077,
            "expected_rate": 0.9692020531964536,
            "mean_higher_minus_lower": 592.2812256960648,
            "median_higher_minus_lower": 554.666666666667,
            "n": 2143,
            "reverse": 64,
            "reverse_rate": 0.029864675688287448,
            "tie": 2,
            "tie_rate": 0.0009332711152589828
          },
          "Llama": {
            "expected": 2107,
            "expected_rate": 0.9832011199253383,
            "mean_higher_minus_lower": 0.12514693748350936,
            "median_higher_minus_lower": 0.11810954375662586,
            "n": 2143,
            "reverse": 36,
            "reverse_rate": 0.01679888007466169,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 2108,
            "expected_rate": 0.9836677554829678,
            "mean_higher_minus_lower": 0.12186019766687496,
            "median_higher_minus_lower": 0.11301503369096422,
            "n": 2143,
            "reverse": 35,
            "reverse_rate": 0.016332244517032198,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 2081,
            "expected_rate": 0.9710685954269715,
            "mean_higher_minus_lower": 0.07243518916987769,
            "median_higher_minus_lower": 0.06406132783500432,
            "n": 2143,
            "reverse": 62,
            "reverse_rate": 0.028931404573028466,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 2143,
        "source_clusters": 1523
      },
      "L4-L5": {
        "domain_items": {
          "arxiv": 157,
          "news": 379,
          "patent": 54,
          "poetry": 189
        },
        "generation_model_items": {
          "claude-opus-4-8": 276,
          "claude-sonnet-5": 214,
          "gemini-3.6-flash": 117,
          "gpt-5.5": 100,
          "gpt-5.6-sol": 72
        },
        "methods": {
          "G": {
            "expected": 779,
            "expected_rate": 1.0,
            "mean_higher_minus_lower": 1210.7727856225931,
            "median_higher_minus_lower": 1245.333333333333,
            "n": 779,
            "reverse": 0,
            "reverse_rate": 0.0,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Llama": {
            "expected": 770,
            "expected_rate": 0.9884467265725289,
            "mean_higher_minus_lower": 0.13750252463031248,
            "median_higher_minus_lower": 0.1391290460535165,
            "n": 779,
            "reverse": 9,
            "reverse_rate": 0.011553273427471117,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 765,
            "expected_rate": 0.982028241335045,
            "mean_higher_minus_lower": 0.12856883264779623,
            "median_higher_minus_lower": 0.1275824787714174,
            "n": 779,
            "reverse": 14,
            "reverse_rate": 0.01797175866495507,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 779,
            "expected_rate": 1.0,
            "mean_higher_minus_lower": 0.13288628844188938,
            "median_higher_minus_lower": 0.13597425261652407,
            "n": 779,
            "reverse": 0,
            "reverse_rate": 0.0,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 779,
        "source_clusters": 589
      }
    },
    "1.30": {
      "L1-L2": {
        "domain_items": {
          "arxiv": 1975,
          "news": 2736,
          "patent": 1972,
          "poetry": 1930
        },
        "generation_model_items": {
          "claude-opus-4-8": 1489,
          "claude-sonnet-5": 1897,
          "gemini-3.6-flash": 566,
          "gpt-5.5": 2413,
          "gpt-5.6-sol": 2248
        },
        "methods": {
          "G": {
            "expected": 8558,
            "expected_rate": 0.9936143039591315,
            "mean_higher_minus_lower": 1682.4313634428577,
            "median_higher_minus_lower": 1344.0000000000036,
            "n": 8613,
            "reverse": 54,
            "reverse_rate": 0.006269592476489028,
            "tie": 1,
            "tie_rate": 0.00011610356437942645
          },
          "Llama": {
            "expected": 8445,
            "expected_rate": 0.9804946011842564,
            "mean_higher_minus_lower": 0.2051275536077314,
            "median_higher_minus_lower": 0.20672715556855492,
            "n": 8613,
            "reverse": 168,
            "reverse_rate": 0.019505398815743643,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 8458,
            "expected_rate": 0.9820039475211889,
            "mean_higher_minus_lower": 0.22938408970694416,
            "median_higher_minus_lower": 0.23190832554648816,
            "n": 8613,
            "reverse": 155,
            "reverse_rate": 0.0179960524788111,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 8548,
            "expected_rate": 0.9924532683153373,
            "mean_higher_minus_lower": 0.2528587429360701,
            "median_higher_minus_lower": 0.2447432720467188,
            "n": 8613,
            "reverse": 65,
            "reverse_rate": 0.007546731684662719,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 8613,
        "source_clusters": 2539
      },
      "L2-L3": {
        "domain_items": {
          "arxiv": 208,
          "news": 520,
          "patent": 486,
          "poetry": 644
        },
        "generation_model_items": {
          "claude-opus-4-8": 117,
          "claude-sonnet-5": 324,
          "gemini-3.6-flash": 356,
          "gpt-5.5": 149,
          "gpt-5.6-sol": 912
        },
        "methods": {
          "G": {
            "expected": 905,
            "expected_rate": 0.48708288482238965,
            "mean_higher_minus_lower": 415.7875852170793,
            "median_higher_minus_lower": -18.666666666666856,
            "n": 1858,
            "reverse": 953,
            "reverse_rate": 0.5129171151776103,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Llama": {
            "expected": 1586,
            "expected_rate": 0.8536060279870828,
            "mean_higher_minus_lower": 0.12667494097250123,
            "median_higher_minus_lower": 0.1367899024291941,
            "n": 1858,
            "reverse": 272,
            "reverse_rate": 0.14639397201291712,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 1444,
            "expected_rate": 0.7771797631862217,
            "mean_higher_minus_lower": 0.09496277509731184,
            "median_higher_minus_lower": 0.10530052610096585,
            "n": 1858,
            "reverse": 414,
            "reverse_rate": 0.22282023681377824,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 961,
            "expected_rate": 0.5172228202368138,
            "mean_higher_minus_lower": 0.011576647838557858,
            "median_higher_minus_lower": 0.00480720377177371,
            "n": 1858,
            "reverse": 897,
            "reverse_rate": 0.48277717976318624,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 1858,
        "source_clusters": 1425
      },
      "L3-L4": {
        "domain_items": {
          "arxiv": 630,
          "news": 1041,
          "patent": 485,
          "poetry": 989
        },
        "generation_model_items": {
          "claude-opus-4-8": 698,
          "claude-sonnet-5": 863,
          "gemini-3.6-flash": 229,
          "gpt-5.5": 1052,
          "gpt-5.6-sol": 303
        },
        "methods": {
          "G": {
            "expected": 3035,
            "expected_rate": 0.9650238473767886,
            "mean_higher_minus_lower": 584.4968733439322,
            "median_higher_minus_lower": 554.666666666667,
            "n": 3145,
            "reverse": 108,
            "reverse_rate": 0.03434022257551669,
            "tie": 2,
            "tie_rate": 0.0006359300476947536
          },
          "Llama": {
            "expected": 3091,
            "expected_rate": 0.9828298887122416,
            "mean_higher_minus_lower": 0.1314311356336413,
            "median_higher_minus_lower": 0.12324442004154455,
            "n": 3145,
            "reverse": 54,
            "reverse_rate": 0.017170111287758347,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 3095,
            "expected_rate": 0.9841017488076311,
            "mean_higher_minus_lower": 0.1277794993430598,
            "median_higher_minus_lower": 0.1181541447254236,
            "n": 3145,
            "reverse": 50,
            "reverse_rate": 0.01589825119236884,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 3045,
            "expected_rate": 0.9682034976152624,
            "mean_higher_minus_lower": 0.0781102523798439,
            "median_higher_minus_lower": 0.06905250153378101,
            "n": 3145,
            "reverse": 100,
            "reverse_rate": 0.03179650238473768,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 3145,
        "source_clusters": 1885
      },
      "L4-L5": {
        "domain_items": {
          "arxiv": 222,
          "news": 541,
          "patent": 88,
          "poetry": 274
        },
        "generation_model_items": {
          "claude-opus-4-8": 385,
          "claude-sonnet-5": 309,
          "gemini-3.6-flash": 183,
          "gpt-5.5": 145,
          "gpt-5.6-sol": 103
        },
        "methods": {
          "G": {
            "expected": 1125,
            "expected_rate": 1.0,
            "mean_higher_minus_lower": 1213.0346666666667,
            "median_higher_minus_lower": 1250.666666666666,
            "n": 1125,
            "reverse": 0,
            "reverse_rate": 0.0,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Llama": {
            "expected": 1109,
            "expected_rate": 0.9857777777777778,
            "mean_higher_minus_lower": 0.13409771169079726,
            "median_higher_minus_lower": 0.1316840110887197,
            "n": 1125,
            "reverse": 16,
            "reverse_rate": 0.014222222222222223,
            "tie": 0,
            "tie_rate": 0.0
          },
          "Mixtral": {
            "expected": 1106,
            "expected_rate": 0.9831111111111112,
            "mean_higher_minus_lower": 0.12473893405540287,
            "median_higher_minus_lower": 0.12035117256555827,
            "n": 1125,
            "reverse": 19,
            "reverse_rate": 0.016888888888888887,
            "tie": 0,
            "tie_rate": 0.0
          },
          "R": {
            "expected": 1125,
            "expected_rate": 1.0,
            "mean_higher_minus_lower": 0.13012417148729927,
            "median_higher_minus_lower": 0.13116761253829798,
            "n": 1125,
            "reverse": 0,
            "reverse_rate": 0.0,
            "tie": 0,
            "tie_rate": 0.0
          }
        },
        "retained_model_item_pairs": 1125,
        "source_clusters": 760
      }
    }
  },
  "adjacent_treatment_concordance": {
    "1.10": {
      "G": {
        "adjacent_pair_centered": {
          "n": 15214,
          "pairwise_continuous_alpha_z": 0.7572620572969823,
          "rho": 0.8479856422932487,
          "undefined_reason": null
        },
        "pooled": {
          "n": 15214,
          "pairwise_continuous_alpha_z": 0.4839011190067156,
          "rho": 0.5324778557493113,
          "undefined_reason": null
        }
      },
      "Llama": {
        "adjacent_pair_centered": {
          "n": 15214,
          "pairwise_continuous_alpha_z": 0.8872958640416606,
          "rho": 0.8524084418824242,
          "undefined_reason": null
        },
        "pooled": {
          "n": 15214,
          "pairwise_continuous_alpha_z": 0.911525020518298,
          "rho": 0.8896406147363153,
          "undefined_reason": null
        }
      },
      "Mixtral": {
        "adjacent_pair_centered": {
          "n": 15214,
          "pairwise_continuous_alpha_z": 0.8793368509395142,
          "rho": 0.8474538799272818,
          "undefined_reason": null
        },
        "pooled": {
          "n": 15214,
          "pairwise_continuous_alpha_z": 0.8979335437794889,
          "rho": 0.8845458593534129,
          "undefined_reason": null
        }
      },
      "R": {
        "adjacent_pair_centered": {
          "n": 15214,
          "pairwise_continuous_alpha_z": 0.8508223643410064,
          "rho": 0.8409103549208692,
          "undefined_reason": null
        },
        "pooled": {
          "n": 15214,
          "pairwise_continuous_alpha_z": 0.8429428161464457,
          "rho": 0.8636318790409135,
          "undefined_reason": null
        }
      }
    },
    "1.20": {
      "G": {
        "adjacent_pair_centered": {
          "n": 23698,
          "pairwise_continuous_alpha_z": 0.7498865606869042,
          "rho": 0.8395494003866999,
          "undefined_reason": null
        },
        "pooled": {
          "n": 23698,
          "pairwise_continuous_alpha_z": 0.49169812358271514,
          "rho": 0.5497638123738552,
          "undefined_reason": null
        }
      },
      "Llama": {
        "adjacent_pair_centered": {
          "n": 23698,
          "pairwise_continuous_alpha_z": 0.8718510473113528,
          "rho": 0.8476625730648893,
          "undefined_reason": null
        },
        "pooled": {
          "n": 23698,
          "pairwise_continuous_alpha_z": 0.9105693552705114,
          "rho": 0.8971149505398787,
          "undefined_reason": null
        }
      },
      "Mixtral": {
        "adjacent_pair_centered": {
          "n": 23698,
          "pairwise_continuous_alpha_z": 0.861896641524931,
          "rho": 0.839940817361016,
          "undefined_reason": null
        },
        "pooled": {
          "n": 23698,
          "pairwise_continuous_alpha_z": 0.8975126184841158,
          "rho": 0.8909436557321434,
          "undefined_reason": null
        }
      },
      "R": {
        "adjacent_pair_centered": {
          "n": 23698,
          "pairwise_continuous_alpha_z": 0.8212637184895311,
          "rho": 0.8300440733265892,
          "undefined_reason": null
        },
        "pooled": {
          "n": 23698,
          "pairwise_continuous_alpha_z": 0.8367410340318292,
          "rho": 0.8625205045938076,
          "undefined_reason": null
        }
      }
    },
    "1.30": {
      "G": {
        "adjacent_pair_centered": {
          "n": 29482,
          "pairwise_continuous_alpha_z": 0.7398910506118244,
          "rho": 0.8301375236579848,
          "undefined_reason": null
        },
        "pooled": {
          "n": 29482,
          "pairwise_continuous_alpha_z": 0.5058969300916523,
          "rho": 0.55542991799567,
          "undefined_reason": null
        }
      },
      "Llama": {
        "adjacent_pair_centered": {
          "n": 29482,
          "pairwise_continuous_alpha_z": 0.8617283322178632,
          "rho": 0.8447980035284277,
          "undefined_reason": null
        },
        "pooled": {
          "n": 29482,
          "pairwise_continuous_alpha_z": 0.9073926063402399,
          "rho": 0.9002289309409864,
          "undefined_reason": null
        }
      },
      "Mixtral": {
        "adjacent_pair_centered": {
          "n": 29482,
          "pairwise_continuous_alpha_z": 0.8493503885359809,
          "rho": 0.8359750907917656,
          "undefined_reason": null
        },
        "pooled": {
          "n": 29482,
          "pairwise_continuous_alpha_z": 0.8949820139366669,
          "rho": 0.8934383949567847,
          "undefined_reason": null
        }
      },
      "R": {
        "adjacent_pair_centered": {
          "n": 29482,
          "pairwise_continuous_alpha_z": 0.798596644051787,
          "rho": 0.8218250100717159,
          "undefined_reason": null
        },
        "pooled": {
          "n": 29482,
          "pairwise_continuous_alpha_z": 0.8316618261649444,
          "rho": 0.8571722814368068,
          "undefined_reason": null
        }
      }
    }
  },
  "all_five_byte_1.25": {
    "clusters": 14,
    "domain_items": {
      "news": 14
    },
    "generation_model_items": {
      "claude-sonnet-5": 12,
      "gemini-3.6-flash": 2
    },
    "inference": null,
    "inference_policy": "coverage_only",
    "items": 14,
    "low_support": true,
    "low_support_reasons": [
      "items_below_1123",
      "clusters_below_256",
      "domain_absent",
      "generation_model_absent"
    ]
  },
  "nesting_asserted": true
}
```
