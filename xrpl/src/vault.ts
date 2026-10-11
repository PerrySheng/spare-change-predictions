import {createCipheriv, createDecipheriv, randomBytes} from 'node:crypto';

const AAD = Buffer.from('spare-xrpl-v1');
function keyFromEnvironment(): Buffer {
  const text = process.env.XRPL_WALLET_KEY;
  const key = Buffer.from(text ?? '', 'base64');
  if (!text || key.length !== 32 || key.toString('base64') !== text) throw new Error('Configure XRPL_WALLET_KEY as a base64 encoded 32-byte encryption key.');
  return key;
}

export function encryptSecret(secret: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', keyFromEnvironment(), iv);
  cipher.setAAD(AAD);
  const encrypted = Buffer.concat([cipher.update(secret, 'utf8'), cipher.final()]);
  return Buffer.concat([iv, encrypted, cipher.getAuthTag()]).toString('base64');
}

export function decryptSecret(encoded: string): string {
  const packed = Buffer.from(encoded, 'base64');
  if (packed.length < 29 || packed.toString('base64') !== encoded) throw new Error('Invalid encrypted XRPL secret envelope.');
  try {
    const decipher = createDecipheriv('aes-256-gcm', keyFromEnvironment(), packed.subarray(0, 12));
    decipher.setAAD(AAD);
    decipher.setAuthTag(packed.subarray(-16));
    return Buffer.concat([decipher.update(packed.subarray(12, -16)), decipher.final()]).toString('utf8');
  } catch {
    throw new Error('XRPL secret could not be decrypted with the configured key.');
  }
}
