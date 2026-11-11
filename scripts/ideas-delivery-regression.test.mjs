import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

test('选题最终交付只接受校验产物并保留编号', () => {
  execFileSync('python3', ['-B', 'scripts/ideas-delivery-regression.py', '-v'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), encoding: 'utf8', stdio: 'pipe',
  });
});
