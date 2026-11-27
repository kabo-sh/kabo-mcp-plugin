import { execFileSync } from 'node:child_process';
import { test } from 'node:test';
// Copy style taking many rounds (generic drafts, samples not followed, rejections answered in the same style).
test('script copy follows samples, handles rejections by dimension and never repeats rejected wording', () => {
  execFileSync('python3', ['-B', 'scripts/script-copy-style-regression.py'], { stdio: 'pipe' });
});
