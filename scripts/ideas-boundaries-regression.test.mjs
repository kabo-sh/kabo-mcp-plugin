import { execFileSync } from 'node:child_process';
import { test } from 'node:test';
// Run only the modified idea boundaries, without calling the model or external services.
test('ideas request and locale boundaries', () => {
  execFileSync('python3', ['-B', 'scripts/ideas-boundaries-regression.py'], { stdio: 'pipe' });
});
