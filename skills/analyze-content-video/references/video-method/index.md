# Video method library

Choose `--focus` from this list. The base card for the mode is always loaded: `diagnosis-default`
for a diagnosis or a content read, `craft-shot-description` for a craft teardown. Add at most two
topic cards, and only when the creator's own words ask about that aspect. With no specific ask,
pass no `--focus`: the base card alone gives a complete, general diagnosis. Never add a card to
look thorough. "Needs" lists evidence that must be present or the card is skipped; "best with" is
evidence that makes it stronger.

| id | Use when the creator asks about | Signal words | Evidence |
|---|---|---|---|
| `diagnosis-default` | base: any diagnosis or content read | — | needs none; best with frames, transcript, measure, viewer observations |
| `craft-shot-description` | base: how a video was made | how was this made / shot / edited; 怎么拍的, 怎么剪的, 拆解镜头 | needs frames; best with measure |
| `opening` | the hook, the first seconds, scroll-past, new openings | hook, opening, first seconds, intro; 开头, 钩子, 黄金三秒, 划走 | needs none; best with opening frames, first cues, loudness lead-in |
| `narrative-structure` | story, script, flow, a dragging middle, the ending or payoff | story, structure, script, ending; 结构, 叙事, 脚本, 结尾, 反转 | needs none; best with the whole transcript and body frames |
| `editing-pacing` | the edit, rhythm, cuts, transitions, what to trim | pacing, rhythm, edit, too slow, transitions; 节奏, 剪辑, 太拖, 转场 | needs measure; best with transcript |
| `sound` | music, voice, mix, sound effects, whether the sound fits | music, sound, audio, voice, BGM; 音乐, 配乐, 声音, 音效 | needs none (with no heard or measured sound the card says so); best with viewer observations and measure |
| `captions-type` | captions, burned-in subtitles, headline text, fonts, readability | captions, subtitles, text, font; 字幕, 花字, 字体, 看不清 | needs frames; best with transcript |
| `visual-color` | the look, framing, lighting, colour, grade | look, framing, lighting, color, grade; 画面, 构图, 打光, 调色, 质感 | needs frames; best with measure |
| `packaging` | title, caption, cover, hashtags, why nobody clicked | title, caption, cover, thumbnail, hashtags; 标题, 文案, 封面, 话题, 没人点 | needs metadata; best with opening frames |
| `emotion` | mood, feeling, tension, why it is moving or funny, work with this video's emotion | emotion, mood, vibe, same emotion; 情绪, 氛围, 感染力, 共鸣 | needs none; best with frames, transcript, viewer observations |
| `audience-response` | why it performed as it did, how viewers reacted, controversy, what to make next from the comments | comments, reaction, controversial, what next; 评论, 观众反应, 争议, 为什么火 | needs none (without a comment summary it says the comments were not read); choosing it fetches the comment summary |

## Choosing

- Pick by what the creator asked, not by what looks weak in the video. A bare link is the base card
  alone; "why did this flop?" or "what are people saying?" adds `audience-response`; "is my hook too
  slow?" adds `opening`; "give me openings with this video's emotion" adds `emotion` and `opening`.
- A question about one aspect inside a craft teardown ("how was the colour done?") adds that topic
  card to `craft-shot-description`.
- "What song is this?" is a find-the-song request, not the `sound` card: no card, and
  `--ask identify_track` instead (one song recognition call, never a whole-video viewing).
- Transcript export loads no card.
- A skipped card is recorded; answer that aspect from the base card and say which evidence was
  missing.
