import { execFileSync } from 'node:child_process';
import { test } from 'node:test';
// Production bad cases S072/S085/S094/S149 (changed or invented facts), I023 (multi-part request),
// S004 (unreadable link) and the save-failure wording (S055/S087/S099/S106/S126/S128).
test('script drafts keep creator facts and deliver every requested part', () => {
  execFileSync('python3', ['-B', 'scripts/script-followthrough-regression.py'], { stdio: 'pipe' });
});
