# Step parameters (generated -- do not edit)

Generated from the Web host's own schema (`contracts/web-remake-tool.v1.json`, kabo-agent-service
`scripts/remake-skill-schema.ts` at 0c3ef9f915a600d5407efe37a09651325c8f0d85) by `scripts/remake-params-gen.mjs`.
These are the exact shapes the host accepts; where any other file in this Skill reads
differently, this file is right. A field not listed under a step is refused on that step.
`?` / (optional) = may be left out; `a | b` = one of; `[x, ...] (2-8 items)` = a list;
`{<name>: x}` = an object keyed by name (never a list).

## Storyboard (`plan`)

- `form`: text (<= 20000) | {<name>: any}
- `total_s`: number 0..600
- `shots`: a list (at most 120), each entry below
- `characters` (optional): a list (at most 12), each entry below
- `skeleton` (optional): [{name: text (<= 80); role?: text (<= 40); share?: number 0..1; seconds?: number 0..600; shots: [integer >= 1, ...] (1-n items)}, ...] (1-20 items)
- `audio_plan` (optional): {voice?: {gain_db?: number -40..6}; music?: {gain_db?: number -40..6; duck_db?: number 0..30; attack_s?: number 0..1; release_s?: number 0.05..2}; sfx?: {gain_db?: number -40..6; duck_db?: number 0..30; attack_s?: number 0..1; release_s?: number 0.05..2}; ambience?: {gain_db?: number -40..6; duck_db?: number 0..30; attack_s?: number 0..1; release_s?: number 0.05..2}; voice_over_music_db?: number 3..20}
- `environments` (optional): a list (at most 12), each entry below
- `props` (optional): a list (at most 12), each entry below
- `series` (optional): [{n: integer 0..999 | text (<= 20); brief: text (<= 2000); job_id?: text (<= 64)}, ...] (1-30 items)

Each row of `shots`:

- `shot`: integer >= 1
- `t0`: number >= 0
- `t1`: number >= 0
- `words`: text (<= 4000)
- `picture`: text (<= 4000)
- `sources`: [text (<= 300), ...] (0-12 items)
- `keep_change`: text (<= 2000)
- `motion`: text (<= 2000)
- `on_screen_text`: text (<= 2000)
- `speaker` (optional): text (<= 200)
- `on_screen_cast` (optional): [text (<= 80), ...] (0-8 items)
- `location` (optional): text (<= 80)
- `props` (optional): [text (<= 80), ...] (0-4 items)
- `camera` (optional): text (<= 30)
- `positions` (optional): {<name>: "left" | "center" | "right"}
- `how` (optional): text (<= 4000)
- `prompt` (optional): text (<= 8000) | {<name>: text (<= 8000)}
- `captions` (optional): text (<= 1000)
- `sound` (optional): text (<= 2000)
- `transition` (optional): text (<= 500)

Each entry of `characters`:

- `name`: text (<= 80)
- `look`: text (<= 3000)
- `sheet` (optional): text (<= 200)
- `voice` (optional): {id?: text (<= 80); language?: text (<= 20); gender?: "male" | "female"; age?: text (<= 20)}

Each entry of `environments`:

- `name`: text (<= 80)
- `look`: text (<= 3000)
- `sheet` (optional): text (<= 200)
- `voice` (optional): {id?: text (<= 80); language?: text (<= 20); gender?: "male" | "female"; age?: text (<= 20)}

Each entry of `props`:

- `name`: text (<= 80)
- `look`: text (<= 3000)
- `sheet` (optional): text (<= 200)
- `voice` (optional): {id?: text (<= 80); language?: text (<= 20); gender?: "male" | "female"; age?: text (<= 20)}

## Steps (`atom`)

### `refvideo`

- inputs: `images`: [handle, ...] (1-10 items); `ref_video` (optional): handle; `first_frame` (optional): handle; `last_frame` (optional): handle
- params: `prompt`: text (<= 2000); `duration` (optional): number 3..30; `sound` (optional): true | false; `model` (optional): "alibaba/wan-3.0/reference-to-video" | "kling/v4/reference-to-video"

### `motion`

- inputs: `image`: handle; `video`: handle
- params: `prompt` (optional): text (<= 2000); `model` (optional): "alibaba/wan-3.0/reference-to-video" | "fal-ai/kling-video/v3/pro/motion-control" | "fal-ai/wan/v2.2-14b/animate/move"

### `replace`

- inputs: `video`: handle; `image`: handle
- params: `prompt` (optional): text (<= 2000); `model` (optional): "minimax/h3-max/recast" | "fal-ai/wan/v2.2-14b/animate/replace"

### `lipsync`

- inputs: `video`: handle; `audio`: handle
- params: `model` (optional): "fal-ai/sync-lipsync/v2/pro" | "fal-ai/latentsync"; `sync_mode` (optional): "cut_off" | "loop" | "bounce" | "silence" | "remap"

### `talking`

- inputs: `image` (optional): handle; `audio` (optional): handle
- params: `model` (optional): "vivix/vivix-a1" | "fal-ai/kling-video/ai-avatar/v2/pro" | "fal-ai/kling-video/ai-avatar/v2/standard" | "minimax/h3-max/lip-sync/image-to-video" | "bytedance/seedance-2.0/reference-to-video" | "alibaba/wan-3.0/reference-to-video"; `prompt` (optional): text (<= 2000); `region` (optional): [number 0..1, number 0..1, number 0..1, number 0..1] (4-4 items); `solo` (optional): true | false; `speaker` (optional): text (<= 200); `shot` (optional): integer 0..9999; `storyboard_hash` (optional): text

### `tts`

- inputs: none
- params: `lines` (optional): [text (<= 400), ...] (1-40 items); `shot` (optional): integer 0..9999; `storyboard_hash` (optional): text; `voice` (optional): "creator" | text; `speed` (optional): number 0.5..2; `language` (optional): "zh" | "en" | "ja" | "ko" | "es" | "fr" | "de" | "pt" | "it" | "ru" | "ar" | "hi" | "id" | "th" | "vi" | "tr"; `gender` (optional): "male" | "female"; `style` (optional): text (<= 80); `speaker` (optional): text (<= 60)

### `still`

- inputs: `refs` (optional): [handle, ...] (0-4 items)
- params: `prompt` (optional): text (<= 2000); `prompts` (optional): [text (<= 2000), ...] (2-8 items); `aspect` (optional): "9:16" | "3:4" | "4:5" | "1:1" | "4:3" | "16:9"; `sheet_for` (optional): text (<= 60) | {kind?: "character" | "environment" | "prop"; name: text (<= 60); as?: "sheet" | "ref"; view?: text (<= 30)} | [text (<= 60) | {kind?: "character" | "environment" | "prop"; name: text (<= 60); as?: "sheet" | "ref"; view?: text (<= 30)} | null, ...] (2-8 items); `on_screen_cast` (optional): [] (empty) | [text (<= 60), ...] (1-4 items) | [[] (empty) | [text (<= 60), ...] (1-4 items) | null, ...] (2-8 items); `location` (optional): text (<= 60) | [text (<= 60) | null, ...] (2-8 items); `props` (optional): [] (empty) | [text (<= 60), ...] (1-4 items) | [[] (empty) | [text (<= 60), ...] (1-4 items) | null, ...] (2-8 items); `positions` (optional): {<name>: "left" | "center" | "right"} | [{<name>: "left" | "center" | "right"} | null, ...] (2-8 items); `camera` (optional): text (<= 30) | [text (<= 30) | null, ...] (2-8 items); `shot` (optional): integer 0..9999 | [integer 0..9999, ...] (2-8 items); `storyboard_hash` (optional): text

### `animate`

- inputs: `image` (optional): handle; `images` (optional): [handle, ...] (2-8 items)
- params: `prompt` (optional): text (<= 2000); `prompts` (optional): [text (<= 2000), ...] (2-8 items); `duration` (optional): 5 | 10; `on_screen_cast` (optional): [] (empty) | [text (<= 60), ...] (1-4 items) | [[] (empty) | [text (<= 60), ...] (1-4 items) | null, ...] (2-8 items); `location` (optional): text (<= 60) | [text (<= 60) | null, ...] (2-8 items); `props` (optional): [] (empty) | [text (<= 60), ...] (1-4 items) | [[] (empty) | [text (<= 60), ...] (1-4 items) | null, ...] (2-8 items); `positions` (optional): {<name>: "left" | "center" | "right"} | [{<name>: "left" | "center" | "right"} | null, ...] (2-8 items); `camera` (optional): text (<= 30) | [text (<= 30) | null, ...] (2-8 items); `shot` (optional): integer 0..9999 | [integer 0..9999, ...] (2-8 items); `storyboard_hash` (optional): text

### `bg`

- inputs: `video`: handle; `plate`: handle
- params: none

### `overlay`

- inputs: `base`: handle; `media`: handle
- params: `t0`: number 0..600; `t1`: number 0..600; `box` (optional): [number 0..1, number 0..1, number 0..1] (3-3 items)

### `splice`

- inputs: `base`: handle; `clip`: handle
- params: `t0`: number 0..600; `t1`: number 0..600; `audio`: "base" | "clip"

### `concat`

- inputs: `clips` (optional): [handle, ...] (2-20 items)
- params: `transition` (optional): "cut" | "dissolve" | "fade_black" | "slide"; `transition_s` (optional): number 0.2..1.5; `shots` (optional): "all" | [integer 0..9999, ...] (2-60 items); `storyboard_hash` (optional): text

### `text_cards`

- inputs: `base`: handle
- params: `cards`: [{text: text (<= 600); t0: number 0..600; t1: number 0..600}, ...] (1-10 items); `style` (optional): "creator" | "plain"

### `music`

- inputs: `base`: handle
- params: `mood` (optional): "calm" | "upbeat" | "warm" | "none"; `prompt` (optional): text (<= 2000); `instrumental` (optional): true | false; `duck` (optional): true | false; `gain_db` (optional): number -30..0

### `captions`

- inputs: `video`: handle
- params: `color` (optional): text; `size` (optional): number 0.5..2; `max_words` (optional): integer 1..8; `upper` (optional): true | false; `font` (optional): "sans" | "serif_caps" | "impact" | "condensed" | "rounded" | "cjk_sans"; `position` (optional): "bottom" | "center" | "top" | number 0..1; `mode` (optional): "phrase" | "word" | "highlight"; `stroke` (optional): integer 0..20; `language` (optional): text; `terms` (optional): [text (<= 40), ...] (1-40 items)

### `frame`

- inputs: `video`: handle
- params: `t` (optional): number 0..600; `at` (optional): "first" | "last"; `grid` (optional): true | false; `shots` (optional): true | false

### `face_check`

- inputs: `media`: handle
- params: none

### `trim`

- inputs: `media` (optional): handle
- params: `t0`: number 0..600; `t1`: number 0..600; `shot` (optional): integer 0..9999; `storyboard_hash` (optional): text

### `mux`

- inputs: `video` (optional): handle; `audio` (optional): handle
- params: `mode`: "replace" | "mix"; `gain_db` (optional): number -30..6; `shot` (optional): integer 0..9999; `storyboard_hash` (optional): text

### `extract_audio`

- inputs: `video`: handle
- params: none

### `voice_change`

- inputs: `media`: handle
- params: `voice`: "creator" | "warm_female"

### `persona`

- inputs: `seed_images` (optional): [handle, ...] (0-4 items)
- params: `description`: text (<= 600); `count` (optional): 2 | 3 | 4

### `retime`

- inputs: `video` (optional): handle
- params: `shot` (optional): integer 0..9999; `storyboard_hash` (optional): text; `mode`: "speed" | "loop" | "bounce" | "hold"; `speed` (optional): number 0.25..4; `duration` (optional): number 0.04..600; `t0` (optional): number 0..600; `t1` (optional): number 0..600; `audio` (optional): "keep" | "none"

### `crop`

- inputs: `media`: handle
- params: `box`: [number 0..1, number 0..1, number 0..1, number 0..1] (4-4 items); `size` (optional): [integer 16..4096, integer 16..4096] (2-2 items); `sheet_for` (optional): text (<= 60) | {kind?: "character" | "environment" | "prop"; name: text (<= 60); as?: "sheet" | "ref"; view?: text (<= 30)}

### `inpaint_text`

- inputs: `media`: handle
- params: `boxes` (optional): [[number 0..1, number 0..1, number 0..1, number 0..1] (4-4 items), ...] (1-8 items); `fill` (optional): "strokes" | "box"; `t0` (optional): number 0..600; `t1` (optional): number 0..600; `words` (optional): [text (<= 40), ...] (1-8 items)

### `layout`

- inputs: `base` (optional): handle; `layers`: [handle, ...] (1-8 items)
- params: `layers`: [{box: [number 0..1, number 0..1, number 0..1, number 0..1] (4-4 items); src_box?: [number 0..1, number 0..1, number 0..1, number 0..1] (4-4 items); fit?: "contain" | "cover" | "stretch"; t0?: number 0..600; t1?: number 0..600; opacity?: number 0..1; key?: "none" | "light" | "dark"; grow?: number 0..0.05}, ...] (1-8 items); `canvas` (optional): {width?: integer 16..4096; height?: integer 16..4096; color?: text; duration?: number 0.04..600}; `audio` (optional): "base" | "none"

### `first_frame`

- inputs: `image`: handle; `refs` (optional): [handle, ...] (0-3 items)
- params: `prompt`: text (<= 2000); `model` (optional): "fal-ai/nano-banana-pro/edit" | "fal-ai/bytedance/seedream/v4.5/edit" | "fal-ai/nano-banana/edit"

### `still_video`

- inputs: `images`: [handle, ...] (1-8 items)
- params: `duration`: number 0.04..600; `zoom` (optional): number 1..1.5; `fit` (optional): "cover" | "contain"

### `transcribe`

- inputs: `media`: handle
- params: `language` (optional): text

### `audio_edit`

- inputs: `media`: handle
- params: `gain_db` (optional): number -30..12; `normalize` (optional): true | false; `fade_in` (optional): number 0..10; `fade_out` (optional): number 0..10; `speed` (optional): number 0.5..2; `duration` (optional): number 0.04..600

### `motion_graphics`

- inputs: `base` (optional): handle; `refs` (optional): [handle, ...] (0-4 items)
- params: `spec`: text (<= 12000) | {<name>: any}; `duration`: number 0.5..120; `preset` (optional): "ui_walkthrough" | "street_grid_map" | "vector_diagram" | "data_chart"

### `sfx`

- inputs: `base`: handle
- params: `events`: [{t: number 0..600; prompt: text (<= 450); duration?: number 0.5..22; gain_db?: number -30..6}, ...] (1-40 items)

### `grade`

- inputs: `video`: handle; `match` (optional): handle
- params: `brightness` (optional): number -0.5..0.5; `contrast` (optional): number 0.5..2; `saturation` (optional): number 0..3; `temperature` (optional): number -1..1; `grain` (optional): number 0..1; `vignette` (optional): number 0..1; `bw` (optional): true | false

### `batch`

- inputs: none
- params: `steps`: [{op: "trim" | "retime" | "mux" | "crop" | "grade" | "still_video" | "concat" | "captions" | "overlay" | "splice" | "layout" | "text_cards" | "motion_graphics" | "talking" | "lipsync" | "tts" | "frame" | "extract_audio" | "sfx" | "music" | "audio_edit" | "voice_change" | "inpaint_text" | "first_frame" | "bg"; inputs?: {<name>: any}; params?: {<name>: any}}, ...] (2-8 items)

### `cast`

- inputs: none
- params: `cards` (optional): [{name: text (<= 60); sheet?: text (<= 80) | null; refs?: [text (<= 80), ...] (0-8 items) | null; views?: {<name>: text (<= 30)} | null; description?: text (<= 2000) | null; voice?: {id?, language?, age?, gender?} | null; style?: text (<= 60) | null; kind: "character"} | {kind: "environment"; name: text (<= 60); sheet?: text (<= 80) | null; refs?: [text (<= 80), ...] (0-8 items) | null; views?: {<name>: text (<= 30)} | null; description?: text (<= 2000) | null} | {kind: "prop"; name: text (<= 60); sheet?: text (<= 80) | null; refs?: [text (<= 80), ...] (0-8 items) | null; views?: {<name>: text (<= 30)} | null; description?: text (<= 2000) | null}, ...] (0-36 items); `characters` (optional): [{name: text (<= 60); sheet?: text (<= 80) | null; refs?: [text (<= 80), ...] (0-8 items) | null; views?: {<name>: text (<= 30)} | null; description?: text (<= 2000) | null; voice?: {id?, language?, age?, gender?} | null; style?: text (<= 60) | null}, ...] (0-12 items); `style` (optional): {description?: text (<= 2000) | null; keywords?: [text (<= 60), ...] (0-12 items) | null; avoid?: [text (<= 80), ...] (0-12 items) | null; palette?: [text | {hex, role?}, ...] (0-8 items) | null; fonts?: [text (<= 60), ...] (0-4 items) | null; motion?: text (<= 200) | null; refs?: [text (<= 80), ...] (0-4 items) | null}; `remove` (optional): [text (<= 60) | {kind: "character" | "environment" | "prop"; name: text (<= 60)}, ...] (0-36 items)

### `storyboard`

- inputs: none
- params: `storyboard` (optional): text (<= 400000) | {shots: [{<name>: any}, ...] (1-60 items)}; `clear` (optional): true | false; `cast` (optional): {cards?: [{name, sheet?, refs?, views?, description?, voice?, style?, kind} | {kind, name, sheet?, refs?, views?, description?}, ...] (0-36 items); characters?: [{name, sheet?, refs?, views?, description?, voice?, style?}, ...] (0-12 items); style?: {description?: text (<= 2000) | null; keywords?: [text (<= 60), ...] (0-12 items) | null; avoid?: [text (<= 80), ...] (0-12 items) | null; palette?: [text | {hex, role?}, ...] (0-8 items) | null; fonts?: [text (<= 60), ...] (0-4 items) | null; motion?: text (<= 200) | null; refs?: [text (<= 80), ...] (0-4 items) | null}; remove?: [text (<= 60) | {kind, name}, ...] (0-36 items)}
