import { execFileSync } from 'node:child_process';
import { test } from 'node:test';
// 只跑被修改的选题边界，不调用模型或外部服务。
test('ideas request and locale boundaries', () => {
  execFileSync('python3', ['-B', 'scripts/ideas-boundaries-regression.py'], { stdio: 'pipe' });
});
