import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

test('a plan built from account results follows the observed cadence and flags already-published topics', () => {
  execFileSync('python3', ['-B', 'scripts/calendar-cadence-regression.py', '-v'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), encoding: 'utf8', stdio: 'pipe',
  });
});
