import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

test('选题分片幂等收集、完整合并及一次聚合修订', () => {
  execFileSync('python3', ['-B', 'scripts/ideas-batches-regression.py', '-v'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), encoding: 'utf8', stdio: 'pipe',
  });
});
