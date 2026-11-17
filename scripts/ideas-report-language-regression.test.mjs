import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

test('content-ideas report labels follow the creator language, including Traditional Chinese and uncataloged languages', () => {
  execFileSync('python3', ['-B', 'scripts/ideas-report-language-regression.py', '-v'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), encoding: 'utf8', stdio: 'pipe',
  });
});
