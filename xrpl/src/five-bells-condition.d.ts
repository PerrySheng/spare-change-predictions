declare module 'five-bells-condition' {
  export class PreimageSha256 {
    setPreimage(value: Buffer): void;
    getConditionBinary(): Buffer;
    serializeBinary(): Buffer;
  }
}
