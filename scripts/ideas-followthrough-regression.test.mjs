import { execFileSync } from 'node:child_process';
import { test } from 'node:test';
// Production bad cases I024/I031/I035 (account review in the conversation) and I032/I033 (delegated niche choice).
test('ideas follow through on reviews in the conversation and delegated niche choices', () => {
  execFileSync('python3', ['-B', 'scripts/ideas-followthrough-regression.py'], { stdio: 'pipe' });
});
