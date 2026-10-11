import {AccountSetAsfFlags, Wallet, type Client} from 'xrpl';
import {CURRENCY, centsToToken, connect, makeCondition, parseNetwork, probe, requireTokenEscrow, sendPayoutBatch, submit, type Network, type TxRecord} from './core.js';
import {encryptSecret, decryptSecret} from './vault.js';

export type PrivateWallet = {address: string; encrypted_seed: string};
export type Request = {
  operation: 'probe'|'setup'|'wallet-create'|'escrow-create'|'escrow-finish'|'escrow-cancel'|'batch-payout';
  network: string;
  encrypted_seed?: string;
  issuer?: PrivateWallet;
  issuer_address?: string;
  destination?: string;
  amount_cents?: number;
  cancel_after?: number;
  owner?: string;
  offer_sequence?: number;
  condition?: string;
  encrypted_fulfillment?: string;
  payouts?: {address: string; cents: number}[];
};

function requireValue<T>(value: T|undefined, label: string): T {
  if (value === undefined || value === null || value === '') throw new Error(`Missing XRPL ${label}.`);
  return value;
}
function loadWallet(encrypted: string): Wallet { return Wallet.fromSeed(decryptSecret(encrypted)); }
export function privateWallet(wallet: Wallet): PrivateWallet {
  return {address: wallet.address, encrypted_seed: encryptSecret(requireValue(wallet.seed, 'wallet seed'))};
}
async function fund(client: Client) {
  // Verify encryption configuration before creating a funded wallet.
  encryptSecret('configuration-check');
  const result = await client.fundWallet();
  return result.wallet;
}
async function addTrust(client: Client, wallet: Wallet, issuer: string, network: Network, records: TxRecord[]) {
  await submit(client, wallet, {TransactionType: 'TrustSet', Account: wallet.address, LimitAmount: {currency: CURRENCY, issuer, value: '1000000'}}, network, 'Create SPC trust line', records);
}

export async function execute(request: Request, records: TxRecord[] = []) {
  const network = parseNetwork(request.network);
  const client = await connect(network);
  try {
    const status = await probe(client, network);
    if (request.operation === 'probe') return {status};
    if (request.operation === 'setup') {
      requireTokenEscrow(status);
      const issuer = await fund(client);
      const settlement = await fund(client);
      await submit(client, issuer, {TransactionType: 'AccountSet', Account: issuer.address, SetFlag: AccountSetAsfFlags.asfDefaultRipple}, network, 'Enable issuer rippling', records);
      await submit(client, issuer, {TransactionType: 'AccountSet', Account: issuer.address, SetFlag: AccountSetAsfFlags.asfAllowTrustLineLocking}, network, 'Enable issuer token escrow', records);
      await addTrust(client, settlement, issuer.address, network, records);
      return {status, currency: CURRENCY, token_label: 'Custom SPC test token; not RLUSD or redeemable USD', issuer: privateWallet(issuer), settlement: privateWallet(settlement)};
    }
    if (request.operation === 'wallet-create') {
      const wallet = await fund(client);
      if (request.issuer) {
        const issuer = loadWallet(request.issuer.encrypted_seed);
        if (issuer.address !== request.issuer.address) throw new Error('Issuer address does not match encrypted issuer wallet.');
        await addTrust(client, wallet, issuer.address, network, records);
        await submit(client, issuer, {TransactionType: 'Payment', Account: issuer.address, Destination: wallet.address, Amount: {currency: CURRENCY, issuer: issuer.address, value: '100'}}, network, 'Fund member with 100 SPC test tokens', records);
      }
      return {status, wallet: privateWallet(wallet), currency: request.issuer ? CURRENCY : null};
    }
    const signer = loadWallet(requireValue(request.encrypted_seed, 'encrypted_seed'));
    if (request.operation === 'escrow-create') {
      requireTokenEscrow(status);
      const cancelAfter = requireValue(request.cancel_after, 'cancel_after');
      if (!Number.isSafeInteger(cancelAfter) || cancelAfter <= status.ledger_close_time + 20) throw new Error('CancelAfter must be at least 20 seconds after the validated ledger close time, in Ripple epoch seconds.');
      const crypto = makeCondition();
      const result = await submit(client, signer, {TransactionType: 'EscrowCreate', Account: signer.address,
        Destination: requireValue(request.destination, 'destination'),
        Amount: {currency: CURRENCY, issuer: requireValue(request.issuer_address, 'issuer_address'), value: centsToToken(requireValue(request.amount_cents, 'amount_cents'))},
        Condition: crypto.condition, CancelAfter: cancelAfter,
      }, network, 'Lock member collateral', records);
      return {status, owner: signer.address, offer_sequence: result.sequence, condition: crypto.condition, encrypted_fulfillment: encryptSecret(crypto.fulfillment), cancel_after: cancelAfter, hash: result.hash, explorer_url: result.explorer_url};
    }
    if (request.operation === 'escrow-finish') {
      requireTokenEscrow(status);
      const result = await submit(client, signer, {TransactionType: 'EscrowFinish', Account: signer.address,
        Owner: requireValue(request.owner, 'owner'), OfferSequence: requireValue(request.offer_sequence, 'offer_sequence'),
        Condition: requireValue(request.condition, 'condition'), Fulfillment: decryptSecret(requireValue(request.encrypted_fulfillment, 'encrypted_fulfillment')),
      }, network, 'Release member collateral', records);
      return {status, hash: result.hash, explorer_url: result.explorer_url};
    }
    if (request.operation === 'escrow-cancel') {
      requireTokenEscrow(status);
      const owner = requireValue(request.owner, 'owner');
      const sequence = requireValue(request.offer_sequence, 'offer_sequence');
      const escrow = await client.request({command: 'ledger_entry', escrow: {owner, seq: sequence}, ledger_index: 'validated'});
      const node = escrow.result.node as {CancelAfter?: number};
      if (!node.CancelAfter || status.ledger_close_time <= node.CancelAfter) throw new Error('Escrow cancellation deadline has not passed in validated ledger time; collateral remains locked.');
      const result = await submit(client, signer, {TransactionType: 'EscrowCancel', Account: signer.address,
        Owner: owner, OfferSequence: sequence,
      }, network, 'Refund expired member collateral', records);
      return {status, hash: result.hash, explorer_url: result.explorer_url};
    }
    if (request.operation === 'batch-payout') {
      const payouts = requireValue(request.payouts, 'payouts');
      if (new Set(payouts.map(item => item.address)).size !== payouts.length || payouts.some(item => item.address === signer.address)) throw new Error('Payout recipients must be distinct from each other and the settlement sender.');
      return {status, ...await sendPayoutBatch(client, signer, requireValue(request.issuer_address, 'issuer_address'), payouts, network, records)};
    }
    throw new Error('Unsupported XRPL operation.');
  } finally {
    await client.disconnect();
  }
}

export function safeError(error: unknown): string {
  const message = error instanceof Error ? error.message : 'XRPL operation failed.';
  return message.replace(/s[1-9A-HJ-NP-Za-km-z]{20,}/g, '[redacted private seed]').slice(0, 400);
}
