import test from 'node:test';
import assert from 'node:assert/strict';
import { Wallet, validate } from 'xrpl';
import { parseNetwork, makeCondition, calculatePayouts, makePayoutBatch, centsToToken } from '../src/core.js';

test('network is limited to the two known XRPL test networks', () => {
  assert.equal(parseNetwork('testnet').id, 1);
  assert.equal(parseNetwork('devnet').id, 2);
  for (const candidate of ['mainnet', 'wss://xrplcluster.com', '', 'TESTNET']) {
    assert.throws(() => parseNetwork(candidate), /testnet or devnet/);
  }
});

test('random crypto-condition is SHA-256 preimage condition with a separate fulfillment', () => {
  const first = makeCondition();
  const next = makeCondition();
  assert.match(first.condition, /^A0258020[0-9A-F]{64}810120$/);
  assert.match(first.fulfillment, /^A0228020[0-9A-F]{64}$/);
  assert.notEqual(first.condition, next.condition);
  assert.notEqual(first.condition, first.fulfillment);
});

test('collateral payout matches all requested three-member examples', () => {
  assert.deepEqual(calculatePayouts(1500, [true, false, false]).map(p => p.payoutCents), [0, 1500, 1500]);
  assert.deepEqual(calculatePayouts(1500, [true, true, false]).map(p => p.payoutCents), [750, 750, 1500]);
  assert.deepEqual(calculatePayouts(1500, [false, false, false]).map(p => p.payoutCents), [1000, 1000, 1000]);
  assert.deepEqual(calculatePayouts(1500, [true, true, true]).map(p => p.payoutCents), [1000, 1000, 1000]);
});

test('payouts conserve cents with fractional loser liabilities', () => {
  for (const losses of [[true, true, true, false, false], [true, true, true, true, false]]) {
    const payouts = calculatePayouts(2500, losses);
    assert.equal(payouts.reduce((sum, item) => sum + item.payoutCents, 0), 10000);
    assert.ok(payouts.every(item => Number.isInteger(item.payoutCents) && item.payoutCents >= 0));
  }
  assert.throws(() => calculatePayouts(1000, [false, false, false]), /divisible/);
  assert.throws(() => calculatePayouts(-1, [false, true]), /positive/);
  assert.throws(() => calculatePayouts(200, [false]), /2 to 8/);
});

test('every loss combination conserves collateral and never creates a negative payout', () => {
  for (let members = 2; members <= 8; members++) {
    for (let mask = 0; mask < 2 ** members; mask++) {
      const lost = Array.from({length: members}, (_, index) => !!(mask & (1 << index)));
      const stake = 137 * members;
      const payouts = calculatePayouts(stake, lost);
      assert.equal(payouts.reduce((sum, item) => sum + item.payoutCents, 0), (stake - 137) * members);
      assert.ok(payouts.every(item => Number.isInteger(item.payoutCents) && item.payoutCents >= 0));
    }
  }
});

test('token conversion retains integer cents without floating-point rounding', () => {
  assert.equal(centsToToken(1), '0.01');
  assert.equal(centsToToken(101), '1.01');
  assert.equal(centsToToken(Number.MAX_SAFE_INTEGER), '90071992547409.91');
  assert.throws(() => centsToToken(1.5), /integer cents/);
});

test('all-or-nothing batch never includes zero payments, unsigned inners have documented flags', () => {
  const sender = Wallet.generate().address;
  const issuer = Wallet.generate().address;
  const recipients = [Wallet.generate().address, Wallet.generate().address, Wallet.generate().address];
  const batch = makePayoutBatch(sender, issuer, recipients.map((address, i) => ({address, cents: [0, 1500, 1500][i]})));
  validate(batch);
  assert.equal(batch.Flags, 65536);
  assert.equal(batch.RawTransactions.length, 2);
  for (const {RawTransaction: transaction} of batch.RawTransactions) {
    assert.equal(transaction.Flags, 0x40000000);
    assert.equal(transaction.Fee, '0');
    assert.equal(transaction.SigningPubKey, '');
    assert.equal(transaction.TxnSignature, undefined);
  }
});
