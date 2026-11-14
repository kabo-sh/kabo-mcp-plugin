import { execFileSync } from 'node:child_process';
import { test } from 'node:test';
// Production bad cases I024/I031/I035 (account review in the conversation), I032/I033 (delegated niche choice) and
// Pre case 3 (three ideas, then a script for the strongest, across a platform question).
test('ideas follow through on reviews in the conversation and delegated niche choices', () => {
  execFileSync('python3', ['-B', 'scripts/ideas-followthrough-regression.py'], { stdio: 'pipe' });
});
