import { randomBytes } from 'node:crypto';
import { PreimageSha256 } from 'five-bells-condition';
import { Client, BatchFlags, GlobalFlags, type Batch, type LedgerEntryRequest, type Payment, type SubmittableTransaction, type Wallet, hashes } from 'xrpl';

export const NETWORKS = {
  testnet: {name: 'testnet', id: 1, url: 'wss://s.altnet.rippletest.net:51233', explorer: 'https://testnet.xrpl.org/transactions/'},
  devnet: {name: 'devnet', id: 2, url: 'wss://s.devnet.rippletest.net:51233', explorer: 'https://devnet.xrpl.org/transactions/'},
} as const;
export type TestNetwork = keyof typeof NETWORKS;
export type Network = typeof NETWORKS[TestNetwork];
export const CURRENCY = 'SPC'; // Custom test token. Not RLUSD; not redeemable USD.
export const AMENDMENTS = {
  TokenEscrow: '138B968F25822EFBF54C00F97031221C47B1EAB8321D93C7C2AEAF85F04EC5DF',
  Batch: '894646DD5284E97DECFE6674A6D6152686791C4A95F8C132CCA9BAF9E5812FB6',
  BatchV1_1: '9F287AED3CDB50A7BD1ACEC24296A30C9B5230CCD136219317AC790E3B884377',
} as const;

export function parseNetwork(value: string): Network {
  if (value !== 'testnet' && value !== 'devnet') throw new Error('XRPL network must be testnet or devnet. Mainnet is disabled.');
  return NETWORKS[value];
}

export async function connect(network: Network): Promise<Client> {
  const client = new Client(network.url, {connectionTimeout: 15_000, timeout: 20_000});
  try {
    await client.connect();
    const info = await client.request({command: 'server_info'});
    if (info.result.info.network_id !== network.id) throw new Error('XRPL server network ID does not match the required test network.');
    return client;
  } catch (error) {
    await client.disconnect();
    throw error;
  }
}

export async function probe(client: Client, network: Network) {
  // The public server supports the documented amendments selector; the SDK type
  // has not yet added it, hence the structural cast rather than an invented field.
  const response = await client.request({command: 'ledger_entry', amendments: true, ledger_index: 'validated'} as LedgerEntryRequest);
  const result = response.result as typeof response.result & {ledger_index: number; node: {Amendments: string[]}};
  if (result.validated !== true || !Array.isArray(result.node.Amendments)) throw new Error('Could not verify amendments in a validated ledger.');
  const enabled = Object.fromEntries(Object.entries(AMENDMENTS).map(([name, hash]) => [name, result.node.Amendments.includes(hash)]));
  const ledger = await client.request({command: 'ledger', ledger_index: result.ledger_index});
  return {network: network.name, network_id: network.id, endpoint: network.url, ledger_index: result.ledger_index, ledger_hash: ledger.result.ledger_hash, ledger_close_time: ledger.result.ledger.close_time, amendments: enabled, checked_at: new Date().toISOString()};
}

export function requireTokenEscrow(status: Awaited<ReturnType<typeof probe>>) {
  if (!status.amendments.TokenEscrow) throw new Error('TokenEscrow is unavailable on this test network; no XRP or mock fallback was used.');
}
export function requireBatch(status: Awaited<ReturnType<typeof probe>>) {
  // Current rippled disabled the vulnerable original Batch. Require replacement.
  if (!status.amendments.BatchV1_1) throw new Error('Safe BatchV1_1 is unavailable on this test network; no sequential-payment fallback was used.');
}

export function makeCondition() {
  const fulfillment = new PreimageSha256();
  fulfillment.setPreimage(randomBytes(32));
  return {condition: fulfillment.getConditionBinary().toString('hex').toUpperCase(), fulfillment: fulfillment.serializeBinary().toString('hex').toUpperCase()};
}

export function centsToToken(cents: number): string {
  if (!Number.isSafeInteger(cents) || cents <= 0) throw new Error('Token amount must be positive integer cents.');
  return `${BigInt(cents) / 100n}.${(BigInt(cents) % 100n).toString().padStart(2, '0')}`;
}

export function calculatePayouts(totalStakeCents: number, lost: boolean[]) {
  const n = lost.length;
  if (n < 2 || n > 8) throw new Error('A squad must contain 2 to 8 members.');
  if (!Number.isSafeInteger(totalStakeCents) || totalStakeCents <= 0) throw new Error('Total stake must be positive integer cents.');
  if (totalStakeCents % n !== 0) throw new Error('Total stake cents must be divisible by member count.');
  const share = totalStakeCents / n;
  const collateral = totalStakeCents - share;
  const loserCount = lost.filter(Boolean).length;
  const totalTransfer = (n - loserCount) * share;
  let loserIndex = 0;
  return lost.map(isLost => {
    const delta = loserCount === 0 || loserCount === n ? 0 : isLost
      ? -(Math.floor(totalTransfer / loserCount) + (loserIndex++ < totalTransfer % loserCount ? 1 : 0))
      : share;
    return {collateralCents: collateral, deltaCents: delta, payoutCents: collateral + delta};
  });
}

export type TxRecord = {label: string; type: string; hash: string; explorer_url: string; result: string; ledger_index?: number};

export async function submit(client: Client, wallet: Wallet, transaction: SubmittableTransaction, network: Network, label: string, records: TxRecord[]) {
  const prepared = await client.autofill(transaction);
  const signed = wallet.sign(prepared);
  // Record signed hash before broadcasting. An uncertain transport is never
  // safe to retry as a fresh transaction; callers journal this exact hash.
  const record: TxRecord = {label, type: transaction.TransactionType, hash: signed.hash, explorer_url: network.explorer + signed.hash, result: 'submitted_unconfirmed'};
  records.push(record);
  const response = await client.submitAndWait(signed.tx_blob);
  const meta = response.result.meta;
  if (!meta || typeof meta === 'string') throw new Error(`Missing metadata for ${label}; inspect the saved transaction hash before retrying.`);
  record.result = meta.TransactionResult;
  record.ledger_index = response.result.ledger_index;
  if (response.result.validated !== true || meta.TransactionResult !== 'tesSUCCESS') throw new Error(`${label} did not validate successfully: ${meta.TransactionResult}`);
  return {hash: signed.hash, explorer_url: record.explorer_url, sequence: prepared.Sequence!, response};
}

export function makePayoutBatch(sender: string, issuer: string, payouts: {address: string; cents: number}[]): Batch {
  const positive = payouts.filter(item => item.cents !== 0);
  if (payouts.some(item => !Number.isSafeInteger(item.cents) || item.cents < 0)) throw new Error('Payouts must contain nonnegative integer cents.');
  if (positive.length < 2 || positive.length > 8) throw new Error('An atomic payout Batch requires 2 to 8 positive payments.');
  return {TransactionType: 'Batch', Account: sender, Flags: BatchFlags.tfAllOrNothing, RawTransactions: positive.map(item => ({RawTransaction: {
    TransactionType: 'Payment', Account: sender, Destination: item.address,
    Amount: {currency: CURRENCY, issuer, value: centsToToken(item.cents)},
    Flags: GlobalFlags.tfInnerBatchTxn, Fee: '0', SigningPubKey: '',
  } as Payment}))};
}

export async function tokenBalance(client: Client, address: string, issuer: string): Promise<string> {
  const response = await client.request({command: 'account_lines', account: address, peer: issuer, ledger_index: 'validated'});
  const line = response.result.lines.find(item => item.currency === CURRENCY && item.account === issuer);
  if (!line) throw new Error('SPC test-token trust line is missing.');
  return line.balance;
}

export async function sendPayoutBatch(client: Client, wallet: Wallet, issuer: string, payouts: {address: string; cents: number}[], network: Network, records: TxRecord[]) {
  requireBatch(await probe(client, network));
  const batch = makePayoutBatch(wallet.address, issuer, payouts);
  const before = await Promise.all(payouts.map(item => tokenBalance(client, item.address, issuer)));
  const result = await submit(client, wallet, batch, network, 'Atomic squad payout', records);
  const inners = result.response.result.tx_json.RawTransactions as Batch['RawTransactions'];
  const verified = [];
  for (const {RawTransaction: inner} of inners) {
    const hash = hashes.hashSignedTx(inner);
    const response = await client.request({command: 'tx', transaction: hash});
    const meta = response.result.meta;
    if (response.result.validated !== true || !meta || typeof meta === 'string' || meta.TransactionResult !== 'tesSUCCESS') throw new Error(`Batch inner payment is not confirmed: ${hash}`);
    const record = {label: 'Verified inner payout', type: inner.TransactionType, hash, explorer_url: network.explorer + hash, result: meta.TransactionResult, ledger_index: response.result.ledger_index};
    records.push(record);
    verified.push(record);
  }
  const after = await Promise.all(payouts.map(item => tokenBalance(client, item.address, issuer)));
  for (let i = 0; i < payouts.length; i++) {
    // Test token issuance/payment uses cents only. Compare exact hundredths.
    const delta = Math.round(Number(after[i]) * 100) - Math.round(Number(before[i]) * 100);
    if (delta !== payouts[i].cents) throw new Error(`Recipient balance differs from the confirmed intended payout for ${payouts[i].address}.`);
  }
  return {hash: result.hash, explorer_url: result.explorer_url, inner_transactions: verified, balances: payouts.map((item, i) => ({address: item.address, before: before[i], after: after[i], payout_cents: item.cents}))};
}

export async function waitUntilCancelable(client: Client, cancelAfter: number, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ledger = await client.request({command: 'ledger', ledger_index: 'validated'});
    if (ledger.result.ledger.close_time > cancelAfter) return ledger.result.ledger.close_time;
    await new Promise(resolve => setTimeout(resolve, 3000));
  }
  throw new Error('Deadline has not passed in validated ledger time; escrow remains locked, no refund was fabricated.');
}
