import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

test('a batch of long scripts is checked against the requested spoken length before it is called complete', () => {
  execFileSync('python3', ['-B', 'scripts/script-batch-duration-regression.py', '-v'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), encoding: 'utf8', stdio: 'pipe',
  });
});
