import {randomBytes} from 'node:crypto';
import {mkdir, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {connect, parseNetwork, probe, calculatePayouts, waitUntilCancelable, requireTokenEscrow, requireBatch, type TxRecord} from './core.js';
import {execute, safeError, type PrivateWallet, type Request} from './operations.js';

export async function main() {
const reportPath = resolve(dirname(fileURLToPath(import.meta.url)), '../reports/spike-latest.json');
const requestedNetwork = process.argv[2] ?? 'testnet';
const network = parseNetwork(requestedNetwork);
// A spike is disposable: keys remain encrypted in memory and are never saved.
// The app CLI requires a persistent key supplied explicitly by its server.
process.env.XRPL_WALLET_KEY ||= randomBytes(32).toString('base64');
const transactions: TxRecord[] = [];
const report: Record<string, unknown> = {started_at: new Date().toISOString(), network: network.name, token: {currency: 'SPC', label: 'Custom test token, NOT RLUSD or redeemable USD'}, transactions, scenarios: []};
let printedTransactions = 0;
async function checkpoint() {
  await mkdir(dirname(reportPath), {recursive: true});
  await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
  for (const item of transactions.slice(printedTransactions)) console.log(`${item.label}: ${item.result} ${item.explorer_url}`);
  printedTransactions = transactions.length;
}
async function run(request: Omit<Request, 'network'>) {
  const result = await execute({...request, network: network.name}, transactions);
  await checkpoint();
  return result as any;
}

try {
  const networks = [];
  for (const candidate of ['testnet', 'devnet']) {
    const current = parseNetwork(candidate);
    const client = await connect(current);
    try {networks.push(await probe(client, current));} finally {await client.disconnect();}
  }
  report.network_probes = networks;
  console.log(JSON.stringify({network_probes: networks}, null, 2));
  const selected = networks.find(item => item.network === network.name)!;
  requireTokenEscrow(selected);
  requireBatch(selected); // Stop before any fallback or wallet setup.
  const setup = await run({operation: 'setup'});
  const issuer: PrivateWallet = setup.issuer;
  const settlement: PrivateWallet = setup.settlement;
  const members: PrivateWallet[] = [];
  for (let i = 0; i < 3; i++) members.push((await run({operation: 'wallet-create', issuer})).wallet);
  report.accounts = {issuer: issuer.address, settlement: settlement.address, members: members.map(item => item.address)};
  await checkpoint();

  // Condition is secret until finish; canceled escrow returns to its owner
  // only after an explicit EscrowCancel passes the validated-ledger deadline.
  let status = (await run({operation: 'probe'})).status;
  const refundEscrow = await run({operation: 'escrow-create', encrypted_seed: members[0].encrypted_seed, destination: settlement.address, issuer_address: issuer.address, amount_cents: 1000, cancel_after: status.ledger_close_time + 35});
  const cancelClient = await connect(network);
  try {await waitUntilCancelable(cancelClient, refundEscrow.cancel_after);} finally {await cancelClient.disconnect();}
  const refund = await run({operation: 'escrow-cancel', encrypted_seed: members[0].encrypted_seed, owner: refundEscrow.owner, offer_sequence: refundEscrow.offer_sequence});
  report.refund = {escrow_hash: refundEscrow.hash, cancel_hash: refund.hash, explorer_url: refund.explorer_url, cancel_after: refundEscrow.cancel_after};
  await checkpoint();

  const scenarios = report.scenarios as unknown[];
  for (const [name, losses] of [['one-loser', [true, false, false]], ['two-losers', [true, true, false]], ['all-win', [false, false, false]], ['all-lose', [true, true, true]]] as const) {
    const payouts = calculatePayouts(1500, [...losses]);
    const escrows = [];
    status = (await run({operation: 'probe'})).status;
    for (let i = 0; i < members.length; i++) {
      escrows.push(await run({operation: 'escrow-create', encrypted_seed: members[i].encrypted_seed, destination: settlement.address, issuer_address: issuer.address, amount_cents: payouts[i].collateralCents, cancel_after: status.ledger_close_time + 600}));
    }
    const finishes = [];
    for (const escrow of escrows) finishes.push(await run({operation: 'escrow-finish', encrypted_seed: settlement.encrypted_seed, owner: escrow.owner, offer_sequence: escrow.offer_sequence, condition: escrow.condition, encrypted_fulfillment: escrow.encrypted_fulfillment}));
    const payout = await run({operation: 'batch-payout', encrypted_seed: settlement.encrypted_seed, issuer_address: issuer.address, payouts: payouts.map((item, i) => ({address: members[i].address, cents: item.payoutCents}))});
    scenarios.push({name, total_stake_cents: 1500, losses, collateral_per_member_cents: 1000, payouts: payouts.map((item, i) => ({address: members[i].address, ...item})), escrow_hashes: escrows.map(item => item.hash), finish_hashes: finishes.map(item => item.hash), batch_hash: payout.hash, batch_explorer_url: payout.explorer_url, inner_transactions: payout.inner_transactions, balances: payout.balances});
    console.log(`Verified ${name}: ${payout.explorer_url}`);
    await checkpoint();
  }
  report.completed_at = new Date().toISOString();
  report.ok = true;
} catch (error) {
  report.ok = false;
  report.error = safeError(error);
  console.error(`Spike stopped: ${report.error}`);
  process.exitCode = 1;
} finally {
  await checkpoint();
  console.log(`Public transaction report: ${reportPath}`);
}

}
