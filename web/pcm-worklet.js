/* 마이크 Float32(ctx 샘플레이트) → 16kHz PCM16 다운샘플 워크릿.
   100ms(1600샘플) 청크 단위로 메인 스레드에 post — WS 프로토콜의 클라→서버 포맷. */
class PCM16kWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000; // iOS Safari는 보통 48000 → 3.0
    this.inBuf = new Float32Array(0);
    this.phase = 0;
    this.out = new Int16Array(1600);
    this.outPos = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    // 이어붙이기
    const merged = new Float32Array(this.inBuf.length + ch.length);
    merged.set(this.inBuf); merged.set(ch, this.inBuf.length);
    // 선형 보간 리샘플 (블록 경계 연속성: phase 유지)
    let p = this.phase;
    while (p + 1 < merged.length) {
      const i = Math.floor(p), frac = p - i;
      const s = merged[i] * (1 - frac) + merged[i + 1] * frac;
      this.out[this.outPos++] = Math.max(-32768, Math.min(32767, s * 32767)) | 0;
      if (this.outPos === 1600) {
        this.port.postMessage(this.out.buffer.slice(0));
        this.outPos = 0;
      }
      p += this.ratio;
    }
    const consumed = Math.floor(p);
    this.inBuf = merged.slice(consumed);
    this.phase = p - consumed;
    return true;
  }
}
registerProcessor("pcm16k", PCM16kWorklet);
