/* Inanna P0 client */
const $ = (id) => document.getElementById(id);

const TRAIT_PRESETS = ["밝음", "다정함", "장난기", "직설", "애교"];
let TEMPLATES = [];
let EDGE_VOICES = [];
let CFG = {};
let editingId = null;      // 빌더가 편집 중인 기존 컴패니언 id
let chatId = null;         // 채팅 중인 컴패니언 id
let chatCompanion = null;  // 채팅 중인 컴패니언 전체 객체 (voice 정보용)
let previewMessages = [];  // 미리보기 대화 (클라이언트에만 존재)
let busy = false;
let _voiceRefPath = "";    // 편집 중 컴패니언의 기존 참조 오디오 경로 유지

/* ---------- authed fetch (INANNA_AUTH_TOKEN 설정 시) ---------- */
const TOKEN_KEY = "inanna_token";
async function api(url, opts = {}) {
  opts.headers = { ...(opts.headers || {}) };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) opts.headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch(url, opts);
  if (r.status === 401) showAuth();
  return r;
}

/* ---------- 인증 (계정 로그인/가입 · 셀프호스팅 토큰) ---------- */
let authMode = "login";

async function showAuth() {
  if (!$("view-auth").hidden) return;
  $("view-auth").hidden = false;
  try {
    const cfg = await (await fetch("/api/auth/config")).json();
    $("auth-invite-row").dataset.off = cfg.invite_required ? "0" : "1";
  } catch {}
  authTab(authMode);
}

function authTab(mode) {
  authMode = mode;
  for (const m of ["login", "register", "token"])
    $(`auth-tab-${m}`).classList.toggle("active", m === mode);
  $("auth-form-account").hidden = mode === "token";
  $("auth-form-token").hidden = mode !== "token";
  $("auth-invite-row").hidden = mode !== "register" || $("auth-invite-row").dataset.off === "1";
  $("auth-submit").textContent = { login: "로그인", register: "가입하기", token: "연결" }[mode];
  $("auth-error").textContent = "";
}

async function authSubmit() {
  $("auth-error").textContent = "";
  try {
    let token;
    if (authMode === "token") {
      token = $("auth-token").value.trim();
      if (!token) return;
      const check = await fetch("/api/companions",
                                { headers: { Authorization: `Bearer ${token}` } });
      if (!check.ok) throw new Error("토큰이 올바르지 않아요");
    } else {
      const r = await fetch(`/api/auth/${authMode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: $("auth-email").value.trim(),
          password: $("auth-password").value,
          invite: $("auth-invite").value.trim(),
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || "실패했어요");
      token = body.token;
    }
    localStorage.setItem(TOKEN_KEY, token);
    $("view-auth").hidden = true;
    location.reload();
  } catch (e) {
    $("auth-error").textContent = e.message;
  }
}

/* ---------- 첫 만남 온보딩 ---------- */
const ob = { proto: null, messages: [], userTurns: 0, extracted: null, voiceId: "" };

function openOnboard() {
  ob.proto = null; ob.messages = []; ob.userTurns = 0; ob.extracted = null; ob.voiceId = "";
  $("ob-name").value = ""; $("ob-calls-me").value = "";
  $("ob-log").innerHTML = ""; $("ob-done-row").hidden = true;
  $("ob-step-rel").hidden = false;
  $("ob-step-chat").hidden = true;
  $("ob-step-confirm").hidden = true;
  const el = $("ob-templates");
  el.innerHTML = "";
  for (const tpl of TEMPLATES) {
    const div = document.createElement("div");
    div.className = "card ob-tpl";
    div.dataset.tid = tpl.id;
    div.innerHTML = `<div class="meta"><div class="name">${escapeHtml(tpl.name)}</div>
      <div class="rel">${escapeHtml(tpl.description || "")}</div></div>`;
    div.onclick = () => {
      for (const c of el.children) c.classList.remove("active");
      div.classList.add("active");
    };
    el.appendChild(div);
  }
  showView("onboard");
}

function obProto() {
  const tplEl = document.querySelector("#ob-templates .active");
  const name = $("ob-name").value.trim();
  if (!tplEl) { alert("어떤 사이가 될지 골라주세요."); return null; }
  if (!name) { alert("이름을 지어주세요."); return null; }
  return {
    id: slugify(name), name,
    relationship: {
      template: tplEl.dataset.tid,
      calls_me: $("ob-calls-me").value.trim(),
      i_call: "", speech_level: "banmal", intimacy: 0.5, backstory: "",
    },
    persona: { traits: {}, speech_quirks: [], description: "",
               example_dialogue: "", first_message: "", lorebook: [] },
    voice: { engine: "", voice_id: "", ref_text: "", speed: 1.0 },
    model: { provider: "", name: "" },
  };
}

async function obStart() {
  const proto = obProto();
  if (!proto) return;
  ob.proto = proto;
  $("ob-title").textContent = `${proto.name}와의 첫 만남`;
  $("ob-step-rel").hidden = true;
  $("ob-step-chat").hidden = false;
  await obTurn();  // 컴패니언이 먼저 인사
}

async function obTurn() {
  const text = await runStream($("ob-log"), "/api/onboard/chat",
                               { companion: ob.proto, messages: ob.messages });
  if (text) ob.messages.push({ role: "assistant", content: text });
}

async function obSend() {
  const input = $("ob-input");
  const text = input.value.trim();
  if (!text || $("ob-send").disabled) return;
  input.value = "";
  addMsg($("ob-log"), "user", text);
  ob.messages.push({ role: "user", content: text });
  ob.userTurns += 1;
  $("ob-send").disabled = true;
  await obTurn();
  $("ob-send").disabled = false;
  if (ob.userTurns >= 3) $("ob-done-row").hidden = false;
}

async function obFinish() {
  $("ob-done-row").hidden = true;
  const log = $("ob-log");
  const wait = addMsg(log, "assistant", "(잠시, 지금까지의 너를 정리하는 중…)");
  wait.className = "msg typing";
  try {
    const r = await api("/api/onboard/extract", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ companion: ob.proto, messages: ob.messages }),
    });
    if (!r.ok) throw new Error((await r.json()).detail || "추출 실패");
    ob.extracted = await r.json();
  } catch (e) {
    wait.remove();
    $("ob-done-row").hidden = false;
    addMsg(log, "error", e.message);
    return;
  }
  wait.remove();
  // 추출 반영
  const x = ob.extracted;
  ob.proto.persona.traits = x.traits;
  ob.proto.persona.speech_quirks = x.speech_quirks;
  ob.proto.persona.description = x.description;
  ob.proto.relationship.speech_level = x.speech_level;
  if (!ob.proto.relationship.calls_me && x.calls_me)
    ob.proto.relationship.calls_me = x.calls_me;
  // 확인 화면
  $("ob-step-chat").hidden = true;
  $("ob-step-confirm").hidden = false;
  $("ob-confirm-avatar").textContent = ob.proto.name[0] || "?";
  $("ob-confirm-name").textContent = ob.proto.name;
  $("ob-confirm-line").textContent = x.confirm || "나 이런 느낌인 것 같아. 맞지?";
  const traits = Object.entries(x.traits || {})
    .filter(([, v]) => v >= 0.6).map(([k]) => k).join(" · ");
  obLoadVoices();
  $("ob-confirm-summary").textContent =
    (traits ? `성격: ${traits}` : "") + (x.description ? ` — ${x.description}` : "");
}

async function obLoadVoices() {
  // 무료 프리셋 3종 — 확인 대사를 그 목소리로 미리 들어보고 고른다
  const el = $("ob-voices");
  el.innerHTML = "";
  let voices = [];
  try { voices = await (await api("/api/voices?engine=edge")).json(); } catch {}
  for (const v of voices.filter(v => v.lang === "ko").slice(0, 3)) {
    const btn = document.createElement("button");
    btn.className = "ghost ob-voice";
    btn.textContent = `▶ ${v.name}`;
    btn.onclick = async () => {
      for (const b of el.children) b.classList.remove("active");
      btn.classList.add("active");
      ob.voiceId = v.id;
      try {
        const r = await api("/api/tts-preview", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            voice: { engine: "edge", voice_id: v.id, ref_text: "", speed: 1.0 },
            text: ($("ob-confirm-line").textContent || "").slice(0, 80),
          }),
        });
        if (r.ok) playAudioBlob(await r.blob());
      } catch {}
    };
    el.appendChild(btn);
  }
}

async function obComplete() {
  if (ob.voiceId) {
    ob.proto.voice = { engine: "edge", voice_id: ob.voiceId, ref_text: "", speed: 1.0 };
  }
  const r = await api("/api/onboard/complete", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ companion: ob.proto, messages: ob.messages,
                           first_memory: ob.extracted.first_memory || "" }),
  });
  if (!r.ok) { alert("저장에 실패했어요"); return; }
  await loadList();
  openChat(ob.proto.id, ob.proto.name);
}

function obTune() {
  // 형성된 값이 채워진 채로 세부 설정(빌더) — 저장은 빌더에서
  openBuilder(ob.proto);
}

/* ---------- view switching ---------- */
// 데스크톱 투페인 — 넓은 화면에서는 목록이 사이드바로 상주한다
const DESKTOP = window.matchMedia("(min-width: 1024px)");

function showView(name) {
  for (const v of ["list", "builder", "chat", "memories", "onboard"]) $(`view-${v}`).hidden = v !== name;
  if (DESKTOP.matches && name !== "list") $("view-list").hidden = false;
  if (name === "list") loadList();
  markActiveCard();
}

DESKTOP.addEventListener("change", () => {
  const mainOpen = ["builder", "chat", "memories"].some(v => !$(`view-${v}`).hidden);
  $("view-list").hidden = mainOpen && !DESKTOP.matches;
});

function markActiveCard() {
  const current = !$("view-chat").hidden || !$("view-memories").hidden ? chatId : null;
  for (const card of document.querySelectorAll("#companion-list .card"))
    card.classList.toggle("active", !!current && card.dataset.cid === current);
}

/* ---------- 기억 열람·정정 ---------- */
async function openMemories() {
  if (!chatId) return;
  $("memories-title").textContent = `${chatCompanion ? chatCompanion.name : ""}의 기억`;
  showView("memories");
  await loadMemories();
}

async function loadMemories() {
  const el = $("memories-list");
  el.innerHTML = `<div class="empty">불러오는 중…</div>`;
  const rows = await (await api(`/api/companions/${chatId}/memories`)).json();
  el.innerHTML = "";
  if (!rows.length) {
    el.innerHTML = `<div class="empty">아직 기억이 없어요.<br>대화가 쌓이면 여기서 볼 수 있어요.</div>`;
    return;
  }
  for (const m of [...rows].reverse()) {  // 최신이 위로
    const d = new Date(m.created_at * 1000);
    const date = `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`;
    const div = document.createElement("div");
    div.className = "card memory-card";
    div.innerHTML = `
      <div class="meta" style="flex:1">
        <div class="hint">${date}</div>
        <div class="memory-content"></div>
      </div>
      <div class="memory-actions">
        <button class="ghost small" title="정정">✎</button>
        <button class="ghost small" title="삭제">🗑</button>
      </div>`;
    div.querySelector(".memory-content").textContent = m.content;
    const [editBtn, delBtn] = div.querySelectorAll("button");
    editBtn.onclick = () => editMemory(div, m);
    delBtn.onclick = async () => {
      if (!confirm("이 기억을 지울까요? 되돌릴 수 없어요.")) return;
      await api(`/api/memories/${m.id}`, { method: "DELETE" });
      div.remove();
    };
    el.appendChild(div);
  }
}

function editMemory(card, m) {
  const content = card.querySelector(".memory-content");
  const ta = document.createElement("textarea");
  ta.value = content.textContent;
  ta.rows = 3;
  ta.style.width = "100%";
  content.replaceWith(ta);
  const actions = card.querySelector(".memory-actions");
  actions.innerHTML = "";
  const save = document.createElement("button");
  save.className = "primary small";
  save.textContent = "저장";
  save.onclick = async () => {
    const text = ta.value.trim();
    if (!text) return;
    const r = await api(`/api/memories/${m.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text }),
    });
    if (r.ok) { m.content = text; loadMemories(); }
  };
  const cancel = document.createElement("button");
  cancel.className = "ghost small";
  cancel.textContent = "취소";
  cancel.onclick = () => loadMemories();
  actions.append(save, cancel);
  ta.focus();
}

function builderTab(name) {
  $("builder-form").hidden = name !== "form";
  $("builder-preview").hidden = name !== "preview";
  $("tab-form").classList.toggle("active", name === "form");
  $("tab-preview").classList.toggle("active", name === "preview");
}

/* ---------- list ---------- */
async function loadList() {
  const companions = await (await api("/api/companions")).json();
  const el = $("companion-list");
  el.innerHTML = "";
  if (!companions.length) {
    el.innerHTML = `<div class="empty">아직 컴패니언이 없어요.<br>아래에서 첫 컴패니언을 만들어보세요.</div>`;
    return;
  }
  for (const c of companions) {
    const tpl = TEMPLATES.find(t => t.id === c.relationship.template);
    const div = document.createElement("div");
    div.className = "card";
    div.dataset.cid = c.id;
    div.innerHTML = `
      <div class="avatar">${escapeHtml(c.name[0] || "?")}</div>
      <div class="meta">
        <div class="name">${escapeHtml(c.name)}</div>
        <div class="rel">${escapeHtml(tpl ? tpl.name : c.relationship.template)} · ${escapeHtml(c.relationship.calls_me || "")}</div>
      </div>
      <button class="ghost small" data-edit>✎</button>`;
    div.onclick = () => openChat(c.id, c.name);
    div.querySelector("[data-edit]").onclick = (e) => { e.stopPropagation(); openBuilder(c); };
    el.appendChild(div);
  }
  markActiveCard();  // 목록은 비동기로 다시 그려지므로 활성 표시 재적용
}

/* ---------- builder ---------- */
function renderTraits(values = {}) {
  const el = $("f-traits");
  el.innerHTML = "";
  for (const name of TRAIT_PRESETS) {
    const v = Math.round((values[name] ?? 0.5) * 10);
    const row = document.createElement("div");
    row.className = "trait";
    row.innerHTML = `<span>${name}</span>
      <input type="range" min="0" max="10" value="${v}" data-trait="${name}"
             oninput="this.nextElementSibling.textContent=this.value">
      <b>${v}</b>`;
    el.appendChild(row);
  }
}

function intimacyText(v) {
  if (v >= 80) return `${v} — 거리감 없음`;
  if (v >= 60) return `${v} — 가까움`;
  if (v >= 40) return `${v} — 보통`;
  return `${v} — 조심스러움`;
}
function updateIntimacyLabel() {
  $("f-intimacy-val").textContent = intimacyText(+$("f-intimacy").value);
}

function applyTemplate() {
  const tpl = TEMPLATES.find(t => t.id === $("f-template").value);
  if (!tpl) return;
  $("f-template-desc").textContent = tpl.description;
  $("f-backstory-hint").textContent = tpl.backstory_hint || "";
  // 템플릿은 출발점 — 파생값을 기본으로 채우되 언제든 덮어쓸 수 있다
  $("f-calls-me").value = tpl.defaults.calls_me || "";
  $("f-speech").value = tpl.defaults.speech_level || "banmal";
  $("f-intimacy").value = Math.round((tpl.defaults.intimacy ?? 0.7) * 100);
  updateIntimacyLabel();
}

function openBuilder(companion = null) {
  editingId = companion ? companion.id : null;
  $("builder-title").textContent = companion ? `${companion.name} 편집` : "새 컴패니언";
  const sel = $("f-template");
  sel.innerHTML = TEMPLATES.map(t => `<option value="${t.id}">${t.name}</option>`).join("");

  if (companion) {
    const c = companion;
    sel.value = c.relationship.template;
    const tpl = TEMPLATES.find(t => t.id === c.relationship.template);
    $("f-template-desc").textContent = tpl ? tpl.description : "";
    $("f-backstory-hint").textContent = tpl ? (tpl.backstory_hint || "") : "";
    $("f-name").value = c.name;
    $("f-calls-me").value = c.relationship.calls_me || "";
    $("f-speech").value = c.relationship.speech_level;
    $("f-intimacy").value = Math.round(c.relationship.intimacy * 100);
    $("f-backstory").value = c.relationship.backstory || "";
    renderTraits(c.persona.traits);
    $("f-description").value = c.persona.description || "";
    $("f-quirks").value = (c.persona.speech_quirks || []).join("\n");
    $("f-examples").value = c.persona.example_dialogue || "";
    $("f-first").value = c.persona.first_message || "";
  } else {
    $("f-name").value = "";
    $("f-backstory").value = ""; $("f-description").value = "";
    $("f-quirks").value = ""; $("f-examples").value = ""; $("f-first").value = "";
    renderTraits();
    applyTemplate();
  }
  // 모델 섹션
  const mo = (companion && companion.model) || { provider: "", name: "" };
  $("f-model-provider").value = mo.provider || "";
  $("f-model-name").value = mo.name || "";

  // 목소리 섹션
  const v = companion ? companion.voice : { engine: "", voice_id: "", ref_text: "", speed: 1.0 };
  _voiceRefPath = companion ? (companion.voice.reference_audio || "") : "";
  $("f-voice-engine").value = v.engine || "";
  renderVoiceOptions(EDGE_VOICES, v.voice_id);
  $("f-voice-model").value = v.model || "";
  $("f-ref-text").value = v.ref_text || "";
  $("f-voice-speed").value = Math.round((v.speed || 1.0) * 100);
  $("f-voice-speed-val").textContent = (v.speed || 1.0).toFixed(2);
  voiceEngineChanged(v.voice_id);

  updateIntimacyLabel();
  resetPreview();
  builderTab("form");
  showView("builder");
}

/* ---------- voice (P1) ---------- */
function renderVoiceOptions(list, selected) {
  // 저장된 voice_id가 목록에 없으면(직접 지정한 커스텀 보이스) 항목으로 보존
  if (selected && !list.some(v => v.id === selected)) {
    list = [{ id: selected, name: `직접 지정 (${selected.slice(0, 8)}…)` }, ...list];
  }
  $("f-voice-id").innerHTML = list.map(v =>
    `<option value="${v.id}" ${v.id === selected ? "selected" : ""}>${escapeHtml(v.name)}</option>`).join("");
}

async function voiceEngineChanged(selectedId) {
  const engine = $("f-voice-engine").value;
  const hasPresets = engine === "edge" || engine === "elevenlabs";
  $("voice-edge").hidden = !hasPresets;
  $("voice-sovits").hidden = engine !== "sovits";
  if (hasPresets) {
    let list = engine === "edge" ? EDGE_VOICES : [];
    if (engine === "elevenlabs") {
      try { list = await (await api("/api/voices?engine=elevenlabs")).json(); } catch {}
    }
    renderVoiceOptions(list, selectedId || $("f-voice-id").value);
    $("voice-model-row").hidden = engine !== "elevenlabs";
    $("voice-preset-hint").textContent =
      (engine === "elevenlabs" && !list.length)
        ? "⚠ ElevenLabs API 키가 없거나 보이스를 불러오지 못했어요 (INANNA_ELEVENLABS_API_KEY)."
        : "";
  }
  if (engine === "sovits") {
    $("voice-sovits-warn").textContent = CFG.sovits_available
      ? "" : "⚠ GPT-SoVITS 워커가 연결되지 않았습니다 (INANNA_SOVITS_URL). 설정은 저장되지만 합성은 안 돼요.";
    $("voice-ref-status").textContent = _voiceRefPath
      ? `등록된 참조 오디오: ${_voiceRefPath}` : "아직 참조 오디오가 없어요.";
  }
}

function collectVoice() {
  const engine = $("f-voice-engine").value;
  return {
    engine,
    voice_id: (engine === "edge" || engine === "elevenlabs") ? $("f-voice-id").value : "",
    model: engine === "elevenlabs" ? $("f-voice-model").value : "",
    reference_audio: _voiceRefPath,
    ref_text: $("f-ref-text").value.trim(),
    speed: (+$("f-voice-speed").value) / 100,
  };
}

let _audio = null;
function playAudioBlob(blob) {
  if (!_audio) _audio = new Audio();
  _audio.src = URL.createObjectURL(blob);
  _audio.play().catch(() => {});
}

async function listenPreview() {
  const voice = collectVoice();
  if (!voice.engine) { alert("엔진을 먼저 선택해주세요."); return; }
  if (!validateVoice(voice)) return;
  const r = await api("/api/tts-preview", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ voice }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    alert(err.detail || "합성 실패");
    return;
  }
  playAudioBlob(await r.blob());
}

$("f-voice-ref").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  if (!editingId) {
    alert("참조 오디오는 컴패니언을 먼저 저장한 뒤 업로드할 수 있어요.");
    e.target.value = "";
    return;
  }
  const form = new FormData();
  form.append("file", file);
  const r = await api(`/api/companions/${editingId}/voice-ref`, { method: "POST", body: form });
  e.target.value = "";
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    alert(err.detail || "업로드 실패");
    return;
  }
  const d = await r.json();
  _voiceRefPath = d.reference_audio;
  let status = `등록된 참조 오디오: ${_voiceRefPath}`;
  if (d.duration) status += ` (${d.duration.toFixed(1)}초${d.trimmed ? " · 10초 초과분 자동 컷" : ""})`;
  $("voice-ref-status").textContent = status;
  if (d.ref_text && !$("f-ref-text").value.trim()) $("f-ref-text").value = d.ref_text;
});

function collectCompanion() {
  const name = $("f-name").value.trim();
  if (!name) { alert("이름을 입력해주세요."); return null; }
  const traits = {};
  for (const input of document.querySelectorAll("[data-trait]"))
    traits[input.dataset.trait] = (+input.value) / 10;
  const id = editingId || slugify(name);
  return {
    id, name,
    relationship: {
      template: $("f-template").value,
      calls_me: $("f-calls-me").value.trim(),
      i_call: "",
      speech_level: $("f-speech").value,
      intimacy: (+$("f-intimacy").value) / 100,
      backstory: $("f-backstory").value.trim(),
    },
    persona: {
      traits,
      speech_quirks: $("f-quirks").value.split("\n").map(s => s.trim()).filter(Boolean),
      description: $("f-description").value.trim(),
      example_dialogue: $("f-examples").value.trim(),
      first_message: $("f-first").value.trim(),
      lorebook: window._importedLorebook || [],
    },
    voice: collectVoice(),
    model: {
      provider: $("f-model-provider").value,
      name: $("f-model-name").value.trim(),
    },
  };
}

function slugify(name) {
  const ascii = name.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return ascii || `c-${Date.now().toString(36)}`;
}

function validateVoice(voice) {
  if ((voice.engine === "elevenlabs" || voice.engine === "edge") && !voice.voice_id) {
    alert("보이스를 선택해주세요. (목록이 비어 있으면 잠시 후 다시 시도하거나 API 키 설정을 확인하세요)");
    return false;
  }
  return true;
}

async function saveCompanion() {
  const c = collectCompanion();
  if (!c) return;
  if (!validateVoice(c.voice)) return;
  const r = await api("/api/companions", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(c),
  });
  if (!r.ok) { alert("저장 실패: " + await r.text()); return; }
  window._importedLorebook = null;
  showView("list");
}

/* ---------- card import ---------- */
$("card-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const r = await api("/api/import-card", { method: "POST", body: form });
  e.target.value = "";
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    alert(err.detail || "카드를 읽을 수 없습니다.");
    return;
  }
  const c = await r.json();
  window._importedLorebook = c.persona.lorebook;
  editingId = null;
  openBuilder(c);
  editingId = null; // openBuilder가 c.id를 잡지 않도록 새 컴패니언으로 취급
});

/* ---------- SSE helper (POST + fetch streaming) ---------- */
async function streamPost(url, body, onDelta) {
  const r = await api(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    // 서버의 사람 문구(detail)만 표시 — raw JSON이 관계에 난입하지 않게 (기획 #1)
    const body = await r.json().catch(() => null);
    const err = new Error((body && body.detail) || "요청이 잘 되지 않았어요. 잠시 후 다시 시도해주세요.");
    err.quota = r.status === 402;
    throw err;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      if (!frame.startsWith("data: ")) continue;
      const data = JSON.parse(frame.slice(6));
      if (data.error) {
        const err = new Error(data.error);
        err.quota = data.kind === "quota";
        throw err;
      }
      if (data.delta) onDelta(data.delta);
      if (data.done) return;
    }
  }
}

/* ---------- chat rendering ---------- */
function addMsg(logEl, role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
  return div;
}

async function runStream(logEl, url, body) {
  busy = true;
  const bubble = addMsg(logEl, "assistant typing", "…");
  let acc = "";
  try {
    await streamPost(url, body, (delta) => {
      acc += delta;
      bubble.textContent = acc;
      bubble.className = "msg assistant";
      logEl.scrollTop = logEl.scrollHeight;
    });
  } catch (err) {
    // 쿼터·오류는 컴패니언이 아니라 '시스템의 조용한 안내'로 (기획 #1)
    bubble.className = err.quota ? "msg system" : "msg error";
    bubble.textContent = err.message;
  } finally {
    busy = false;
  }
  return acc;
}

/* ---------- real chat ---------- */
function voicePrefKey(id) { return `inanna_voiceon_${id}`; }

function updateVoiceToggle() {
  const btn = $("chat-voice-toggle");
  const hasVoice = chatCompanion && chatCompanion.voice && chatCompanion.voice.engine;
  btn.hidden = !hasVoice;
  if (!hasVoice) return;
  const on = localStorage.getItem(voicePrefKey(chatId)) !== "off";
  btn.textContent = on ? "🔊" : "🔇";
}

async function openChat(id, name) {
  chatId = id;
  $("chat-title").textContent = name;
  chatCompanion = await (await api(`/api/companions/${id}`)).json();
  $("chat-edit").onclick = () => openBuilder(chatCompanion);
  $("chat-voice-toggle").onclick = () => {
    const on = localStorage.getItem(voicePrefKey(chatId)) !== "off";
    localStorage.setItem(voicePrefKey(chatId), on ? "off" : "on");
    updateVoiceToggle();
  };
  updateVoiceToggle();
  const log = $("chat-log");
  log.innerHTML = "";
  showView("chat");
  const h = await (await api(`/api/chat/${id}/history`)).json();
  for (const m of h.messages) addMsg(log, m.role, m.content);
}

async function speakReply(text) {
  if (!chatCompanion || !chatCompanion.voice.engine) return;
  if (localStorage.getItem(voicePrefKey(chatId)) === "off") return;
  try {
    const r = await api(`/api/tts/${chatId}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (r.ok) playAudioBlob(await r.blob());
  } catch { /* 음성 실패는 대화를 막지 않는다 */ }
}

async function sendChat() {
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text || busy || !chatId) return;
  input.value = "";
  addMsg($("chat-log"), "user", text);
  const reply = await runStream($("chat-log"), `/api/chat/${chatId}`, { message: text });
  if (reply) speakReply(reply);
}

/* ---------- preview chat (빌더 미리보기 — 저장/기억 없음) ---------- */
function resetPreview() {
  previewMessages = [];
  const log = $("preview-log");
  if (log) log.innerHTML =
    `<div class="msg error">미리보기 — 저장되지 않고 기억에도 남지 않아요. 설정을 바꾸고 ↺로 다시 시험해보세요.</div>`;
}

async function sendPreview() {
  const input = $("preview-input");
  const text = input.value.trim();
  if (!text || busy) return;
  const companion = collectCompanion();
  if (!companion) return;
  input.value = "";
  addMsg($("preview-log"), "user", text);
  previewMessages.push({ role: "user", content: text });
  const reply = await runStream($("preview-log"), "/api/preview",
    { companion, messages: previewMessages });
  if (reply) previewMessages.push({ role: "assistant", content: reply });
}

/* ---------- misc ---------- */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

for (const [inputId, btnId, fn] of [["chat-input", "chat-send", sendChat], ["preview-input", "preview-send", sendPreview]]) {
  $(inputId).addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); fn(); }
  });
}

(async function init() {
  TEMPLATES = await (await api("/api/templates")).json();
  try {
    CFG = await (await api("/api/config")).json();
    $("provider-badge").textContent = `${CFG.provider} · ${CFG.model}`;
  } catch { /* provider 미설정이어도 UI는 뜬다 */ }
  try {
    EDGE_VOICES = await (await api("/api/voices?engine=edge")).json();
  } catch { EDGE_VOICES = []; }
  loadList();
})();
