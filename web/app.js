(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const streets = {preflop: '翻牌前', flop: '翻牌', turn: '转牌', river: '河牌', showdown: '摊牌'};
  const styleNames = {tight: '耐心等好牌', tag: '耐心等好牌', tight_aggressive: '耐心等好牌', calling: '爱跟着看看', calling_station: '爱跟着看看', loose_passive: '爱跟着看看', bold: '喜欢施加压力', overconfident: '喜欢施加压力', loose_bold: '喜欢施加压力', aggressive: '喜欢施加压力'};
  let state = null, busy = false, timer = null, amount = null, amountVersion = null, replay = null, replayIndex = 0, failed = false;
  const bb = (units) => Number((Number(units || 0) / 2).toFixed(1)).toLocaleString('en-US', {maximumFractionDigits: 1});
  const signed = (units) => `${units > 0 ? '+' : units < 0 ? '−' : ''}${bb(Math.abs(units || 0))}`;
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const card = (code, empty = false) => {
    if (!code) return `<span class="card ${empty ? 'empty' : 'back'}" aria-label="${empty ? '尚未发出' : '未公开的底牌'}"></span>`;
    const rank = code.slice(0, -1).replace('T', '10'), suit = code.slice(-1).toLowerCase();
    const symbol = {s:'♠', h:'♥', d:'♦', c:'♣'}[suit] || suit;
    return `<span class="card ${suit === 'h' || suit === 'd' ? 'red' : ''}" aria-label="${esc(code)}"><span class="rank">${esc(rank)}</span><span class="suit">${symbol}</span><span class="corner-suit">${symbol}</span></span>`;
  };
  const cards = (values = [], count = 2, empty = false) => Array.from({length: Math.max(count, values.length)}, (_, i) => card(values[i], empty)).join('');
  async function api(path, body) {
    const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', headers: {'Content-Type': 'application/json'}, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body)});
    let data;
    try { data = await response.json(); } catch { throw new Error('牌桌暂时没有回应，请重新连接。'); }
    if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : typeof data.detail === 'string' ? data.detail : '这次行动未能完成，请重新连接。');
    return data;
  }
  function showError(error) { failed = true; clearTimeout(timer); $('error-message').textContent = error.message || '连接中断，请重试。'; $('error-banner').hidden = false; }
  function clearError() { failed = false; $('error-banner').hidden = true; }
  function isPaused() { return $('history-dialog').open || $('reset-dialog').open; }
  function scheduleBot() {
    clearTimeout(timer);
    if (!state || busy || failed || document.hidden || isPaused() || state.complete || state.current_actor === 0 || state.current_actor == null) return;
    timer = setTimeout(() => transition('/api/step', {version: state.version}), 850);
  }
  async function transition(path, body = {}) {
    if (busy) return;
    clearTimeout(timer); busy = true; renderActions();
    try { const next = await api(path, body); state = next.state || next; clearError(); render(); }
    catch (error) { showError(error); }
    finally { busy = false; renderActions(); scheduleBot(); }
  }
  function render() {
    if (!state) return;
    $('street-label').textContent = state.complete ? '这一手结束' : streets[state.street] || state.street;
    $('pot').innerHTML = `<span>${state.complete ? '本手底池' : '底池'}</span> <strong>${bb(state.pot)}</strong> <small>BB</small>`;
    $('board').innerHTML = cards(state.board, 5, true);
    const actor = state.players.find((p) => p.id === state.current_actor);
    $('table-message').textContent = state.complete ? state.summary || '这一手已经结束' : state.current_actor === 0 ? '轮到你了，慢慢来。' : actor ? `${actor.name} 正在想一想…` : '正在发牌…';
    $('hand-marker').textContent = `第 ${state.hand_id} 手`;
    $('activity-hand').textContent = `HAND ${String(state.hand_id).padStart(3, '0')}`;
    $('session-hands').innerHTML = `${Math.max(0, state.hand_id - (state.complete ? 0 : 1))} <small>手</small>`;
    $('session-net').innerHTML = `${signed(state.session_net)} <small>BB</small>`;
    $('session-net').className = state.session_net > 0 ? 'positive' : state.session_net < 0 ? 'negative' : '';
    $('seats').innerHTML = state.players.map((p) => {
      const active = !state.complete && state.current_actor === p.id;
      const style = p.id === 0 ? '你的座位' : styleNames[p.style] || p.style || '今晚的牌友';
      const avatarColor = /^#[0-9a-f]{3,8}$/i.test(p.color || '') ? p.color : ['#677b61','#a18b6c','#778b88','#b79175','#84936d','#9c827a'][p.id];
      return `<div class="seat seat-${p.id} ${!p.in_hand ? 'folded' : ''} ${active ? 'active' : ''} ${p.all_in ? 'all-in' : ''}"><div class="seat-person"><span class="avatar" style="--avatar-color:${avatarColor}">${esc(p.avatar || p.name.slice(0, 1))}</span><div class="seat-details"><div class="seat-name">${esc(p.name)}${p.id === 0 && p.name !== '你' ? ' <span style="font-size:8px;color:#939c87">你</span>' : ''}</div><div class="seat-stack">${bb(p.stack)}<small>BB</small></div></div><span class="seat-position">${state.dealer === p.id ? 'D' : esc(p.position || '')}</span></div><div class="seat-style">${esc(style)}</div><div class="seat-cards">${cards(p.cards)}</div><div class="seat-action">${p.all_in ? 'ALL IN' : active ? '思考中…' : esc(p.last_action || '已入座')}</div></div>${p.bet > 0 && !state.complete ? `<div class="bet-chip bet-${p.id}">${bb(p.bet)}</div>` : ''}`;
    }).join('');
    const list = $('activity-list'); const wasBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
    let previousStreet = '';
    list.innerHTML = (state.actions || []).map((action) => {
      const divider = previousStreet !== action.street ? `<li class="street-divider">${esc(streets[action.street] || action.street || '')}</li>` : '';
      previousStreet = action.street;
      return `${divider}<li>${esc(action.text)}</li>`;
    }).join('') || '<li class="empty-activity">朋友们已经入座，准备发牌。</li>';
    if (wasBottom) list.scrollTop = list.scrollHeight;
    renderActions();
  }
  function renderActions() {
    if (!state) return;
    const panel = $('action-panel');
    if (state.complete) {
      panel.innerHTML = `<div class="hand-end"><div class="hand-end-copy"><p class="eyebrow">ONE MORE HAND?</p><h3>${esc(state.summary || '这一手结束了。')}</h3><p>筹码留在桌上，庄家向前一位。</p></div><div class="hand-end-actions"><button class="secondary-button" id="review-hand" ${busy ? 'disabled' : ''}>复盘这手</button><button class="primary-button" id="next-hand" ${busy ? 'disabled' : ''}>下一手 <span aria-hidden="true">→</span></button></div></div>`;
      $('review-hand').onclick = () => openHistory(state.hand_id);
      $('next-hand').onclick = () => transition('/api/next', {version: state.version});
      return;
    }
    if (state.current_actor !== 0) {
      const actor = state.players.find((p) => p.id === state.current_actor);
      panel.innerHTML = `<div class="waiting-state"><span class="loading-dot"></span>${esc(actor ? `等 ${actor.name} 行动` : '正在发牌')}<span style="color:#a2aa97;font-size:10px;margin-left:8px">看看朋友们怎么打</span></div>`;
      return;
    }
    const legal = state.legal || {}, min = Number(legal.min_raise_to || 0), max = Number(legal.max_raise_to || 0);
    if (amountVersion !== state.version) { amount = min; amountVersion = state.version; }
    amount = Math.max(min, Math.min(max, Number(amount) || min));
    const hero = state.players.find((p) => p.id === 0), canRaise = legal.can_raise && max > 0;
    panel.innerHTML = `<div class="action-heading"><strong>轮到你了</strong><small>${hero && hero.position ? esc(hero.position) + ' · ' : ''}${legal.can_check ? '可以免费看下一步' : `跟注需 ${bb(legal.call_amount)} BB`}</small></div>${canRaise ? `<div class="sizing"><label for="raise-slider">加注到</label><input id="raise-slider" aria-label="加注到多少筹码" type="range" min="${min}" max="${max}" value="${amount}" step="1" ${busy ? 'disabled' : ''}><div class="amount-input"><input id="raise-amount" type="number" aria-label="加注到多少 BB" min="${min / 2}" max="${max / 2}" step="0.5" value="${amount / 2}" ${busy ? 'disabled' : ''}><span>BB</span></div><div class="sizing-presets"><button type="button" data-size="half" ${busy ? 'disabled' : ''}>½ 底池</button><button type="button" data-size="pot" ${busy ? 'disabled' : ''}>底池</button><button type="button" data-size="all" ${busy ? 'disabled' : ''}>ALL IN</button></div></div>` : ''}<div class="action-buttons"><button class="action-button" id="fold-action" ${busy || !legal.can_fold ? 'disabled' : ''}>弃牌</button><button class="action-button call" id="call-action" ${busy || (!legal.can_check && !legal.call_amount) ? 'disabled' : ''}>${legal.can_check ? '过牌' : '跟注'}${!legal.can_check ? `<span>${bb(legal.call_amount)} BB</span>` : ''}</button><button class="action-button raise" id="raise-action" ${busy || !canRaise ? 'disabled' : ''}>${amount === max && canRaise ? '全下' : '加注到'}<span id="raise-label">${canRaise ? bb(amount) + ' BB' : '暂不可加注'}</span></button></div>`;
    $('fold-action').onclick = () => transition('/api/action', {version: state.version, action: 'fold'});
    $('call-action').onclick = () => transition('/api/action', {version: state.version, action: 'check_call'});
    $('raise-action').onclick = () => transition('/api/action', {version: state.version, action: 'raise', amount: Math.round(amount)});
    if (canRaise) {
      const setAmount = (value) => { amount = Math.max(min, Math.min(max, Math.round(Number(value) || min))); $('raise-slider').value = amount; $('raise-amount').value = amount / 2; $('raise-action').innerHTML = `${amount === max ? '全下' : '加注到'}<span>${bb(amount)} BB</span>`; };
      $('raise-slider').oninput = (event) => setAmount(event.target.value);
      $('raise-amount').onchange = (event) => setAmount(Number(event.target.value) * 2);
      panel.querySelectorAll('[data-size]').forEach((button) => { button.onclick = () => {
        const base = (hero?.bet || 0) + Number(legal.call_amount || 0), potAfterCall = Number(state.pot) + Number(legal.call_amount || 0);
        setAmount(button.dataset.size === 'all' ? max : base + potAfterCall * (button.dataset.size === 'half' ? .5 : 1));
      }; });
    }
  }
  async function openHistory(handId) {
    clearTimeout(timer);
    if (!$('history-dialog').open) $('history-dialog').showModal();
    $('history-content').innerHTML = '<div class="waiting-state"><span class="loading-dot"></span>翻开牌局记录…</div>';
    try {
      if (handId) { replay = await api(`/api/hand/${handId}`); replayIndex = 0; renderReplay(); }
      else {
        const data = await api('/api/history'); replay = null;
        const hands = data.hands || [];
        $('history-content').innerHTML = hands.length ? hands.map((hand) => `<button class="history-hand" data-hand="${hand.hand_id}"><span class="hand-number">${String(hand.hand_id).padStart(2, '0')}</span><span class="hand-copy"><strong>${esc(hand.summary || '完整手牌记录')}</strong><small>${(hand.board || []).map(esc).join(' · ') || '翻牌前结束'} · 点击逐步回看</small></span><span class="hand-net ${hand.net > 0 ? 'positive' : hand.net < 0 ? 'negative' : ''}">${signed(hand.net)} <small style="font:9px var(--sans)">BB</small></span></button>`).join('') : '<div class="history-empty">还没有打完的手牌。<br>打完第一手，再来看看每一步。</div>';
        $('history-content').querySelectorAll('[data-hand]').forEach((button) => { button.onclick = () => openHistory(Number(button.dataset.hand)); });
      }
    } catch (error) { $('history-content').innerHTML = `<div class="history-empty">${esc(error.message)}<br><button id="retry-history" class="secondary-button">重试</button></div>`; $('retry-history').onclick = () => openHistory(handId); }
  }
  function renderReplay() {
    const frames = replay.frames || [], frame = frames[replayIndex];
    if (!frame) { $('history-content').innerHTML = '<div class="history-empty">这手暂时没有可用的回放。</div>'; return; }
    const lastAction = frame.actions?.at(-1), last = replayIndex === frames.length - 1;
    $('history-content').innerHTML = `<button class="replay-back" id="back-history">← 所有手牌</button><div class="replay-heading"><h3>第 ${replay.hand_id} 手</h3><span>第 ${replayIndex + 1} / ${frames.length} 步</span></div><div class="replay-board"><div class="replay-board-label">${esc(streets[frame.street] || '发牌')} ${frame.complete ? '· 已结束' : ''}</div><div class="board">${cards(frame.board, 5, true)}</div><div class="replay-pot">${bb(frame.pot)} <small style="font:9px var(--sans)">BB 底池</small></div></div><div class="replay-controls"><button id="replay-prev" aria-label="上一步" ${replayIndex === 0 ? 'disabled' : ''}>←</button><input type="range" id="replay-slider" min="0" max="${frames.length - 1}" value="${replayIndex}" step="1" aria-label="回放进度"><button id="replay-next" aria-label="下一步" ${last ? 'disabled' : ''}>→</button></div><div class="replay-event">${esc(frame.complete ? frame.summary || replay.summary : lastAction?.text || '六位朋友入座，盲注就位。')}</div><div class="replay-players">${(frame.players || []).map((p) => `<div class="replay-player ${!p.in_hand ? 'folded' : ''}"><div><div class="replay-player-name">${esc(p.name)}${p.id === 0 && p.name !== '你' ? ' · 你' : ''}</div><div class="replay-player-stack">${bb(p.stack)} BB ${p.all_in ? '· ALL IN' : ''}</div></div><div class="replay-cards">${cards(p.cards)}</div></div>`).join('')}</div><div class="review-notes"><h4>这一手的观察</h4>${(replay.notes || []).map((note) => `<p>${esc(typeof note === 'string' ? note : note.text || '')}</p>`).join('') || '<p>回到当时的公共牌和下注过程，想想你给对手的范围。结果只是这一手的结尾。</p>'}</div><p class="replay-disclaimer">回放保留每一步当时可见的信息；未公开的底牌仍然盖着。这里的观察用于复盘，不是最优策略评分。</p>`;
    $('back-history').onclick = () => openHistory();
    $('replay-prev').onclick = () => { replayIndex = Math.max(0, replayIndex - 1); renderReplay(); };
    $('replay-next').onclick = () => { replayIndex = Math.min(frames.length - 1, replayIndex + 1); renderReplay(); };
    $('replay-slider').onchange = (event) => { replayIndex = Number(event.target.value); renderReplay(); $('replay-slider').focus(); };
  }
  $('history-button').onclick = () => openHistory();
  $('close-history').onclick = () => $('history-dialog').close();
  $('history-dialog').addEventListener('close', scheduleBot);
  $('reset-button').onclick = () => { clearTimeout(timer); $('reset-dialog').showModal(); };
  $('cancel-reset').onclick = () => $('reset-dialog').close();
  $('reset-dialog').addEventListener('close', scheduleBot);
  $('confirm-reset').onclick = () => { $('reset-dialog').close(); transition('/api/reset'); };
  $('retry-button').onclick = async () => {
    if (busy) return; busy = true;
    try { const next = await api('/api/session', {}); state = next.state || next; clearError(); render(); }
    catch (error) { showError(error); }
    finally { busy = false; renderActions(); scheduleBot(); }
  };
  document.addEventListener('visibilitychange', () => { if (document.hidden) clearTimeout(timer); else scheduleBot(); });
  transition('/api/session');
})();
