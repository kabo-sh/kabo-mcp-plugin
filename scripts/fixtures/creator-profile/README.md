# 账号画像合成夹具

三份 `*.json` 是手写的合成数据，取自 creator-skills #918 的
`creator-skill-tests/trend-competitor-v3/fixtures/creator-profile/`，只补了 `review: null`：
钉住的 `get_creator_profile` outputSchema 要求顶层有 `account`、`review`、`diagnosis` 三格。
形状是 `/mcp-pub` 的 `get_creator_profile`（带 `include: ["content_profile"]`）的 `structuredContent`，
`scripts/trends-profile.test.mjs` 先用 `contracts/directory-mcp/tools-list.json` 里钉住的 outputSchema 校验它们，
所以重新钉制品后契约若变了，这里会先红，按新口径改夹具。

- 账号、内容 id、标题全部虚构，不对应任何真实账号。
- TikTok 那份故意让 `signatureContent` 的列表顺序和权重顺序相反，用来钉住「按 weight 降序、同权按 id」的排序。
- YouTube 那份主打内容的种子词是中文，用来钉住无空格文字的子串匹配。

## 有效画像夹具（`*-effective*.json`）

形状同上，多一格 `effectiveContentProfile`（`get_creator_profile` 带 `effective: true` 时的出参），
同样先过钉住的 outputSchema。

- `tiktok-effective.json`、`tiktok-effective-main.json`、`tiktok-effective-no-base.json`：取自 kabo
  `docs/contracts/effective-content-profile-v1.golden.json`（kabo-sh/kabo#1875 分支 43cb78325）的三个向量
  `excluded_topics_language_and_market`、`primary_is_lifted_to_the_front`、`no_base_profile_keeps_settings_and_reports_edits`：
  向量输入的后台画像放进 `contentProfile`（没有后台画像时为 null），期望的合成结果原样放进
  `effectiveContentProfile`；`account` 沿用 `tiktok.json` 的。合成规则只在 kabo 领域包里有一份，这里不重算。
- `instagram-effective.json`、`youtube-effective.json`：在 `instagram.json`、`youtube.json` 上手写的镜像，
  主打内容原样搬过来，加了本人设的排除话题与市场（BR、GB），用来测 Instagram 不用市场、YouTube collect 的缺省地区。
- golden 改了或重新钉制品后，按新的向量重新生成，不手改合成结果。
