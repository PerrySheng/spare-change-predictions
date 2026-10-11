import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {encryptSecret, decryptSecret} from '../src/vault.js';

test('seeds remain encrypted, randomized and authenticated', () => {
  process.env.XRPL_WALLET_KEY = randomBytes(32).toString('base64');
  const secret = 'private-test-value';
  const first = encryptSecret(secret);
  const second = encryptSecret(secret);
  assert.equal(decryptSecret(first), secret);
  assert.notEqual(first, second);
  assert.ok(!first.includes(secret));
  const tampered = Buffer.from(first, 'base64');
  tampered[13] ^= 0xff;
  assert.throws(() => decryptSecret(tampered.toString('base64')), /could not be decrypted/);
  process.env.XRPL_WALLET_KEY = randomBytes(32).toString('base64');
  assert.throws(() => decryptSecret(first), /could not be decrypted/);
  delete process.env.XRPL_WALLET_KEY;
  assert.throws(() => encryptSecret(secret), /32-byte/);
});
