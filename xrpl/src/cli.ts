import {execute, safeError, type Request} from './operations.js';
import type {TxRecord} from './core.js';

// Private data enters only stdin, never command-line arguments or shell history.
let input = '';
for await (const chunk of process.stdin) {
  input += chunk;
  if (Buffer.byteLength(input) > 1024 * 1024) throw new Error('XRPL request exceeds size limit.');
}
const transactions: TxRecord[] = [];
try {
  const request = JSON.parse(input) as Request;
  const result = await execute(request, transactions);
  process.stdout.write(JSON.stringify({ok: true, ...result, transactions}) + '\n');
} catch (error) {
  process.stdout.write(JSON.stringify({ok: false, error: safeError(error), transactions}) + '\n');
  process.exitCode = 1;
}
