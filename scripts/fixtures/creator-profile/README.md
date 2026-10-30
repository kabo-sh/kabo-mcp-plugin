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
