/* 실시간 음성 통화 클라이언트 — 프로토콜: docs/voice-protocol.md
   barge-in: 마이크는 항상 송신, 서버가 재생 중 지속 발화만 끼어들기로 판정한다. */

const call = {
  ws: null, ctx: null, node: null, stream: null,
  state: "idle", pendingMeta: null, queue: [], playing: new Set(),
  nextTime: 0, keepAlive: null,
  turnEnded: false, wakeLock: null, active: false,
};

const STATE_LABEL = {
  idle: "듣고 있어요", listening: "듣는 중…",
  thinking: "생각 중…", speaking: "말하는 중 — 말하거나 탭하면 끼어들 수 있어요",
};

async function startCall() {
  if (!chatId || call.active) return;
  try {
    call.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (e) {
    alert("마이크를 열 수 없어요. HTTPS(tailscale serve 주소)로 접속했는지 확인해주세요.\n" + e.message);
    return;
  }
  call.active = true;
  $("view-call").hidden = false;
  setCallState("idle");
  $("call-name").textContent = chatCompanion ? chatCompanion.name : "";
  $("call-user-caption").textContent = "";
  $("call-char-caption").textContent = "";

  // 오디오 컨텍스트 (버튼 제스처 안이므로 iOS 언락 OK)
  call.ctx = new (window.AudioContext || window.webkitAudioContext)();
  await call.ctx.resume();
  await call.ctx.audioWorklet.addModule("/static/pcm-worklet.js?v=2");
  const source = call.ctx.createMediaStreamSource(call.stream);
  call.node = new AudioWorkletNode(call.ctx, "pcm16k");
  source.connect(call.node);
  call.node.port.onmessage = (e) => {
    // barge-in: 재생 중에도 계속 송신 — 서버가 보수적 감지기로 에코를 걸러
    // 지속 발화만 끼어들기로 승격한다 (1차 방어는 echoCancellation)
    if (call.ws && call.ws.readyState === 1) {
      call.ws.send(e.data);
    }
  };

  try { call.wakeLock = await navigator.wakeLock.request("screen"); } catch {}

  // 출력 라우트 킵얼라이브 — iOS가 무음 구간 후 재생 시작부(첫 음절)를
  // 삼키는 것 방지. 들리지 않는 미세 노이즈를 통화 내내 루프 재생한다.
  {
    const sec = call.ctx.sampleRate;
    const buf = call.ctx.createBuffer(1, sec, sec);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < sec; i++) ch[i] = (Math.random() * 2 - 1) * 1e-4;
    const src = call.ctx.createBufferSource();
    src.buffer = buf; src.loop = true;
    src.connect(call.ctx.destination);
    src.start();
    call.keepAlive = src;
  }

  // WebSocket
  const proto = location.protocol === "https:" ? "wss" : "ws";
  call.ws = new WebSocket(`${proto}://${location.host}/api/ws/voice/${chatId}`);
  call.ws.binaryType = "arraybuffer";
  call.ws.onopen = () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) call.ws.send(JSON.stringify({ type: "auth", token }));
  };
  // 메시지 처리 순서 보장 — decodeAudioData가 비동기라 문장 순서가 뒤바뀌는 것 방지
  let chain = Promise.resolve();
  call.ws.onmessage = (e) => {
    chain = chain.then(() => onCallMessage(e)).catch((err) => clientLog("handler: " + err));
  };
  call.ws.onclose = (e) => {
    if (call.active) {
      if (e.code === 4401) { localStorage.removeItem(TOKEN_KEY); alert("인증이 필요해요. 다시 시도해주세요."); }
      endCall();
    }
  };
}

function clientLog(message) {
  // 폰 콘솔은 볼 수 없으니 서버 로그로 원격 진단
  try {
    if (call.ws && call.ws.readyState === 1)
      call.ws.send(JSON.stringify({ type: "client_log", message: String(message).slice(0, 300) }));
  } catch {}
}

function wavToAudioBuffer(buf) {
  /* 서버 WAV(PCM16)를 디코더 없이 직접 파싱 — iOS decodeAudioData의
     간헐적 WAV 실패("뒤의 말만 재생" 원인)를 원천 차단 */
  try {
    const dv = new DataView(buf);
    if (dv.getUint32(0) !== 0x52494646) return null; // "RIFF"
    let off = 12, rate = 32000, channels = 1, bits = 16, dataOff = -1, dataLen = 0;
    while (off + 8 <= dv.byteLength) {
      const id = String.fromCharCode(dv.getUint8(off), dv.getUint8(off + 1),
                                     dv.getUint8(off + 2), dv.getUint8(off + 3));
      const size = dv.getUint32(off + 4, true);
      if (id === "fmt ") {
        channels = dv.getUint16(off + 10, true);
        rate = dv.getUint32(off + 12, true);
        bits = dv.getUint16(off + 22, true);
      } else if (id === "data") { dataOff = off + 8; dataLen = size; break; }
      off += 8 + size + (size % 2);
    }
    if (dataOff < 0 || bits !== 16 || channels < 1) return null;
    const n = Math.floor(Math.min(dataLen, buf.byteLength - dataOff) / 2 / channels);
    if (n < 1) return null;
    const ab = call.ctx.createBuffer(1, n, rate);
    const ch = ab.getChannelData(0);
    for (let i = 0; i < n; i++) ch[i] = dv.getInt16(dataOff + i * 2 * channels, true) / 32768;
    return ab;
  } catch { return null; }
}

async function onCallMessage(e) {
  if (e.data instanceof ArrayBuffer) {
    const meta = call.pendingMeta; call.pendingMeta = null;
    let buf = null;
    if (meta && meta.mime === "audio/wav") buf = wavToAudioBuffer(e.data);
    if (!buf) {
      try { buf = await call.ctx.decodeAudioData(e.data); }
      catch (err) {
        clientLog(`decode 실패 seq=${meta && meta.seq}: ${err && err.message}`);
        return;
      }
    }
    call.queue.push(buf);
    playNext();
    return;
  }
  const ev = JSON.parse(e.data);
  switch (ev.type) {
    case "ready":
      // 유대감(0~1)에 따라 오브의 색·광량이 변한다
      if (typeof ev.bond === "number")
        $("call-orb").style.setProperty("--bond", ev.bond);
      break;
    case "state": setCallState(ev.value); break;
    case "stt":
      $("call-user-caption").textContent = ev.text;
      $("call-char-caption").textContent = "";
      call.caption = "";
      break;
    case "text":
      // 오디오 태그([laughs] 등)는 음성으로만 연기 — 자막에서 숨긴다.
      // 태그가 델타에 쪼개져 올 수 있어 원문 버퍼에 모은 뒤 걸러 렌더한다.
      call.caption = (call.caption || "") + ev.delta;
      $("call-char-caption").textContent =
        call.caption.replace(/\[[a-zA-Z][a-zA-Z ]{1,30}\]/g, " ").replace(/ {2,}/g, " ").slice(-120);
      break;
    case "audio": call.pendingMeta = ev; break;
    case "turn_end": call.turnEnded = true; maybePlaybackEnd(); break;
    case "interrupted": stopPlayback(); break;
    case "error":
      // 무음으로 죽지 않게 — 원인을 통화 화면에 표시
      $("call-char-caption").textContent = "⚠ " + ev.message;
      clientLog("server error: " + ev.message);
      break;
  }
}

function playNext() {
  /* 샘플 정확 스케줄링 — onended 후 start()로 잇던 방식은 청크 경계마다
     콜백 지연만큼 불규칙한 공백을 만든다. nextTime 시계로 이어 붙이고,
     새로 시작할 때만 80ms 리드를 줘 재생 시작부 클리핑을 피한다. */
  if (!call.ctx) return;
  while (call.queue.length) {
    const buf = call.queue.shift();
    const src = call.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(call.ctx.destination);
    src.onended = () => { call.playing.delete(src); maybePlaybackEnd(); };
    const t = Math.max(call.ctx.currentTime + 0.08, call.nextTime);
    call.playing.add(src);
    src.start(t);
    call.nextTime = t + buf.duration;
  }
}

function maybePlaybackEnd() {
  if (call.turnEnded && !call.playing.size && !call.queue.length &&
      call.ws && call.ws.readyState === 1) {
    call.turnEnded = false;
    call.ws.send(JSON.stringify({ type: "playback_end" }));
  }
}

function stopPlayback() {
  call.queue = [];
  call.turnEnded = false;
  call.nextTime = 0;
  for (const src of call.playing) { try { src.stop(); } catch {} }
  call.playing.clear();
}

function interruptCall() {
  // 유나가 말하거나 생각 중일 때만 의미 있음
  if (call.state === "speaking" || call.state === "thinking") {
    stopPlayback();
    if (call.ws && call.ws.readyState === 1) call.ws.send(JSON.stringify({ type: "interrupt" }));
  }
}

function setCallState(s) {
  call.state = s;
  const orb = $("call-orb");
  if (orb) orb.dataset.state = s;
  const label = $("call-state-label");
  if (label) label.textContent = STATE_LABEL[s] || s;
}

function endCall() {
  call.active = false;
  try { call.ws && call.ws.close(); } catch {}
  stopPlayback();
  try { call.keepAlive && call.keepAlive.stop(); } catch {}
  try { call.node && call.node.disconnect(); } catch {}
  try { call.ctx && call.ctx.close(); } catch {}
  if (call.stream) for (const t of call.stream.getTracks()) t.stop();
  try { call.wakeLock && call.wakeLock.release(); } catch {}
  call.ws = call.ctx = call.node = call.stream = call.wakeLock = call.keepAlive = null;
  $("view-call").hidden = true;
  // 통화 중 오간 대화를 채팅 로그에 반영
  if (chatId) openChat(chatId, chatCompanion ? chatCompanion.name : "");
}
