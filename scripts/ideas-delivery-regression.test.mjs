import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

test('final content-ideas delivery accepts only validated artifacts and keeps numbering', () => {
  execFileSync('python3', ['-B', 'scripts/ideas-delivery-regression.py', '-v'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), encoding: 'utf8', stdio: 'pipe',
  });
});
