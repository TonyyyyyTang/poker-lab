(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  // Every word the player reads, per language. The server sends codes and numbers only.
  const STRINGS = {
    zh: {
      title: 'Poker Lab · 朋友局', brandAria: 'Poker Lab 首页', langSwitch: 'EN', langAria: 'Switch to English',
      brandSub: '德州训练场', room: '朋友局', roomSize: '六人桌', invite: '邀请朋友', history: '牌局记录',
      tableAria: '德州扑克牌桌', eyebrowHome: '今晚的牌局', headline: '坐下来，打几手。',
      rulesGame: '无限注德州', rulesStakes: '100 BB 买入 · 无抽水', retry: '重新连接',
      feltCaption: '好友相聚 · 好牌相伴', seating: '正在入座', pot: '底池', boardAria: '公共牌',
      tableWaiting: '牌友们正在等你', actionsAria: '行动控制', preparing: '正在准备牌桌…',
      footerPlay: '模拟筹码 · 只为练习与乐趣', footerHint: '观察对手，慢慢找到自己的节奏。',
      eyebrowInvite: '邀请', inviteTitle: '朋友的牌桌',
      inviteCopy: '把链接发给朋友，输入名字就能入座。空位由对手补上，每步 30 秒。',
      copyLink: '复制链接', leaveTable: '离开牌桌', eyebrowSession: '本场', sessionTitle: '今晚的牌桌',
      handsDone: '已完成', sessionNet: '本场净变化', handsUnit: '手', activityTitle: '桌边动态', activityLive: '进行中',
      activityEmpty: '发牌后，行动会记录在这里。', activityReady: '朋友们已经入座，准备发牌。',
      noteTitle: '熟悉这几位牌友',
      noteBody: '有人耐心等牌，有人爱跟到底，也有人总想把底池打大。看他们怎么打，再决定你的下一步。',
      resetLink: '重新开一场', eyebrowAfter: '牌后', historyTitle: '牌后，再看一遍。', closeReview: '关闭复盘',
      nameAria: '你的名字', cancel: '取消', resetTitle: '换一壶茶，重新开场。',
      resetCopy: '所有人回到 100 BB，本场记录会清空。', resetKeep: '继续这场', resetConfirm: '重新开场',
      'street.preflop': '翻牌前', 'street.flop': '翻牌', 'street.turn': '转牌', 'street.river': '河牌', 'street.showdown': '摊牌',
      handOver: '这一手结束', finalPot: '本手底池', pendingMsg: '你已入座，下一手开始参与。',
      yourTurnMsg: '轮到你了，慢慢来。', thinkingMsg: '{name} 正在想一想…', dealing: '正在发牌…',
      handNo: '第 {n} 手',
      'style.you': '你的座位', 'style.friend': '朋友', 'style.tight': '耐心等好牌', 'style.calling': '爱跟着看看', 'style.bold': '喜欢施加压力',
      leaving: '离开中', away: '暂离', allIn: '全下', thinking: '思考中…', seated: '已入座',
      'act.fold': '弃牌', 'act.check': '过牌', 'act.call': '跟注 {a} BB', 'act.raise': '加注至 {a} BB',
      'act.small_blind': '小盲 {a} BB', 'act.big_blind': '大盲 {a} BB', allInSuffix: ' · 全下',
      splitPot: '平分底池', listSep: '，', rebuys: '{names} 已补充至 100 BB。',
      eyebrowMore: '再来一手？', handEndCopy: '筹码留在桌上，庄家向前一位。', autoDeal: '下一手{c}后自动开始。',
      reviewHand: '复盘这手', nextHand: '下一手',
      awayPanel: '你暂时离开了，轮到你时会自动过牌或弃牌。', back: '我回来了',
      waitPending: '下一手入座', waitActor: '等 {name} 行动', waitHint: '看看朋友们怎么打',
      raiseTo: '加注到', raiseAria: '加注到多少筹码', raiseAriaBB: '加注到多少 BB', halfPot: '½ 底池', potSize: '底池',
      yourTurn: '轮到你了', freeLook: '可以免费看下一步', toCall: '跟注需 {a} BB',
      fold: '弃牌', check: '过牌', call: '跟注', cantRaise: '暂不可加注',
      loadingHistory: '翻开牌局记录…', endedPreflop: '翻牌前结束', tapReplay: '点击逐步回看',
      historyEmpty: '还没有打完的手牌。', historyEmptyHint: '打完第一手，再来看看每一步。', retryShort: '重试',
      allHands: '← 所有手牌', replayStep: '第 {i} / {n} 步', finished: '· 已结束', potSuffix: 'BB 底池',
      prevStep: '上一步', nextStep: '下一步', replayProgress: '回放进度', replayStart: '六位朋友入座，盲注就位。',
      notesTitle: '这一手的观察',
      disclaimer: '回放保留每一步当时可见的信息；未公开的底牌仍然盖着。这里的观察用于复盘，不是最优策略评分。',
      'note.result': '本手你行动 {actions} 次，净变化 {net} BB。结果本身不代表决策质量。',
      'note.pot_odds': '{street}的一次决定：跟注 {call} BB，跟注后可争夺底池 {eligible} BB；若之后不再下注，需要约 {required}% 的胜率才能打平。这不是完整行动 EV。',
      'note.visibility': '逐步回看只显示当时可见的信息；对手在实际亮牌后才公开底牌，弃牌与盖牌仍然保密。',
      createTitle: '开一张朋友桌', createCopy: '朋友会看到这个名字。开桌后把链接发给他们。', createButton: '开桌',
      joinTitle: '加入朋友的牌桌', joinCopy: '输入一个名字就能入座；正在进行的一手结束后开始参与。', joinButton: '入座',
      copied: '链接已复制，发给朋友吧。', copyFailed: '请手动复制上面的链接。',
      noResponse: '牌桌暂时没有回应，请重新连接。', connectionLost: '连接中断，请重试。',
      cardHidden: '未公开的底牌', cardEmpty: '尚未发出',
      'error.expired': '牌桌已过期或服务已重启，请重新连接开始新的一场。', 'error.not_found': '找不到页面。',
      'error.hand_not_found': '这手牌尚未结束或已不在最近 20 手中。', 'error.invite_not_found': '找不到这张牌桌，邀请链接可能已过期。',
      'error.table_full': '这张桌已经坐满了。', 'error.bad_name': '名字须为 1–12 个字符，不能包含控制字符。',
      'error.bad_request': '请求格式错误。', 'error.stale': '牌局已更新，请按当前局面操作。',
      'error.not_your_turn': '现在还没轮到你。', 'error.illegal_action': '这个操作现在不可用。',
      'error.hand_in_progress': '这手牌还没结束。', 'error.not_seated': '你还没有入座。',
      'error.forbidden_origin': '仅接受当前站点牌桌的操作。', 'error.server_error': '牌局遇到错误，请刷新后重试。',
    },
    en: {
      title: 'Poker Lab · Home game', brandAria: 'Poker Lab home', langSwitch: '中', langAria: '切换到中文',
      brandSub: "Hold'em practice", room: 'Home game', roomSize: 'Six seats', invite: 'Invite friends', history: 'Hand history',
      tableAria: 'Poker table', eyebrowHome: 'THE HOME GAME', headline: 'Pull up a chair.',
      rulesGame: "No-limit hold'em", rulesStakes: '100 BB buy-in · no rake', retry: 'Reconnect',
      feltCaption: 'GOOD COMPANY. GOOD HANDS.', seating: 'Taking seats', pot: 'Pot', boardAria: 'Board',
      tableWaiting: 'The table is waiting for you', actionsAria: 'Actions', preparing: 'Setting up the table…',
      footerPlay: 'Play chips · for practice and fun', footerHint: 'Watch the table and find your rhythm.',
      eyebrowInvite: 'INVITE', inviteTitle: 'Your table',
      inviteCopy: 'Send this link to friends: they type a name and take a seat. Bots fill empty seats; 30 seconds per turn.',
      copyLink: 'Copy link', leaveTable: 'Leave table', eyebrowSession: 'THIS SESSION', sessionTitle: "Tonight's table",
      handsDone: 'Hands', sessionNet: 'Session net', handsUnit: 'hands', activityTitle: 'Table log', activityLive: 'LIVE',
      activityEmpty: 'Actions appear here once the cards are dealt.', activityReady: 'Everyone is seated. Dealing soon.',
      noteTitle: 'Get to know the regulars',
      noteBody: 'One waits for good cards, one calls almost everything, one keeps building the pot. Watch how they play before you decide.',
      resetLink: 'Start a new session', eyebrowAfter: 'AFTER THE HAND', historyTitle: 'Look back at the hand.', closeReview: 'Close review',
      nameAria: 'Your name', cancel: 'Cancel', resetTitle: 'Fresh pot of tea, fresh session.',
      resetCopy: "Everyone returns to 100 BB and this session's record is cleared.", resetKeep: 'Keep playing', resetConfirm: 'Start over',
      'street.preflop': 'Preflop', 'street.flop': 'Flop', 'street.turn': 'Turn', 'street.river': 'River', 'street.showdown': 'Showdown',
      handOver: 'Hand over', finalPot: 'Final pot', pendingMsg: "You're seated and play from the next hand.",
      yourTurnMsg: 'Your turn. Take your time.', thinkingMsg: '{name} is thinking…', dealing: 'Dealing…',
      handNo: 'Hand {n}',
      'style.you': 'Your seat', 'style.friend': 'Friend', 'style.tight': 'Patient', 'style.calling': 'Loves to call', 'style.bold': 'Pushes hard',
      leaving: 'Leaving', away: 'Away', allIn: 'ALL IN', thinking: 'Thinking…', seated: 'Seated',
      'act.fold': 'Fold', 'act.check': 'Check', 'act.call': 'Call {a} BB', 'act.raise': 'Raise to {a} BB',
      'act.small_blind': 'Small blind {a} BB', 'act.big_blind': 'Big blind {a} BB', allInSuffix: ' · all-in',
      splitPot: 'Split pot', listSep: ', ', rebuys: '{names} topped up to 100 BB.',
      eyebrowMore: 'ONE MORE HAND?', handEndCopy: 'Chips stay on the table; the button moves on.', autoDeal: ' Next hand in {c}.',
      reviewHand: 'Review hand', nextHand: 'Next hand',
      awayPanel: "You're away: your turns check or fold automatically.", back: "I'm back",
      waitPending: 'Joining next hand', waitActor: 'Waiting for {name}', waitHint: 'Watch how they play',
      raiseTo: 'Raise to', raiseAria: 'Raise amount in chips', raiseAriaBB: 'Raise amount in BB', halfPot: '½ pot', potSize: 'Pot',
      yourTurn: 'Your turn', freeLook: 'Free to check', toCall: '{a} BB to call',
      fold: 'Fold', check: 'Check', call: 'Call', cantRaise: 'No raise',
      loadingHistory: 'Opening hand history…', endedPreflop: 'Ended preflop', tapReplay: 'Tap to replay',
      historyEmpty: 'No finished hands yet.', historyEmptyHint: 'Finish a hand, then step through it here.', retryShort: 'Retry',
      allHands: '← All hands', replayStep: 'Step {i} of {n}', finished: '· finished', potSuffix: 'BB pot',
      prevStep: 'Previous step', nextStep: 'Next step', replayProgress: 'Replay progress', replayStart: 'Six players seated, blinds posted.',
      notesTitle: 'Notes on this hand',
      disclaimer: 'Each step shows only what was visible at the time; unrevealed cards stay hidden. These notes support review; they are not an optimal-strategy score.',
      'note.result': 'You acted {actions} times; net {net} BB. A result alone does not measure decision quality.',
      'note.pot_odds': '{street} decision: calling {call} BB to contest {eligible} BB needs about {required}% equity to break even if no more betting follows. This is not a full action EV.',
      'note.visibility': "Replay shows only what was visible at each step; opponents' cards appear only once shown, and folded or mucked hands stay private.",
      createTitle: "Start a friends' table", createCopy: 'Friends will see this name. Send them the link once the table is open.', createButton: 'Open table',
      joinTitle: "Join a friend's table", joinCopy: "Type a name to take a seat; you'll play from the next hand.", joinButton: 'Sit down',
      copied: 'Link copied. Send it to your friends.', copyFailed: 'Copy the link above by hand.',
      noResponse: "The table isn't responding. Please reconnect.", connectionLost: 'Connection lost. Please retry.',
      cardHidden: 'Face-down card', cardEmpty: 'Not dealt yet',
      'error.expired': 'This table has expired or the server restarted. Reconnect to start a new session.', 'error.not_found': 'Not found.',
      'error.hand_not_found': "That hand isn't finished or is older than the last 20.", 'error.invite_not_found': 'Table not found; the invite link may have expired.',
      'error.table_full': 'This table is full.', 'error.bad_name': 'Names need 1–12 characters, without control characters.',
      'error.bad_request': 'Bad request.', 'error.stale': 'The table moved on; act on the current position.',
      'error.not_your_turn': "It isn't your turn.", 'error.illegal_action': "That action isn't available now.",
      'error.hand_in_progress': "This hand isn't over yet.", 'error.not_seated': "You aren't seated yet.",
      'error.forbidden_origin': "Only this site's table can send actions.", 'error.server_error': 'Something went wrong. Refresh and try again.',
    },
  };
  let lang = (() => {
    try { const saved = localStorage.getItem('poker-lab-lang'); if (saved in STRINGS) return saved; } catch {}
    return navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en';
  })();
  const t = (key, vars = {}) => STRINGS[lang][key].replace(/\{(\w+)\}/g, (_, name) => vars[name]);
  let state = null, receivedAt = 0, busy = false, poller = null, amount = null, amountVersion = null, replay = null, replayIndex = 0, failed = false;
  let rebuyHand = null;
  const bb = (units) => (units / 2).toLocaleString('en-US', {maximumFractionDigits: 1});
  const signed = (units) => `${units > 0 ? '+' : units < 0 ? '−' : ''}${bb(Math.abs(units))}`;
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const nameOf = (p) => (lang === 'en' ? p.name_en : p.name);
  const card = (code, empty = false) => {
    if (!code) return `<span class="card ${empty ? 'empty' : 'back'}" aria-label="${t(empty ? 'cardEmpty' : 'cardHidden')}"></span>`;
    const rank = code.slice(0, -1).replace('T', '10'), suit = code.slice(-1).toLowerCase();
    const symbol = {s:'♠', h:'♥', d:'♦', c:'♣'}[suit] || suit;
    return `<span class="card ${suit === 'h' || suit === 'd' ? 'red' : ''}" aria-label="${esc(code)}"><span class="rank">${esc(rank)}</span><span class="suit">${symbol}</span><span class="corner-suit">${symbol}</span></span>`;
  };
  const cards = (values = [], count = 2, empty = false) => Array.from({length: Math.max(count, values.length)}, (_, i) => card(values[i], empty)).join('');
  const spot = (id) => (id - state.you + 6) % 6;  // Seat classes place the viewer at the bottom.
  // Server actions and last actions are codes and chip units; words come from STRINGS.
  const actionLabel = (kind, units, allIn) => t(`act.${kind}`, {a: bb(units)}) + (allIn ? t('allInSuffix') : '');
  const logLabel = (a) => actionLabel(a.kind === 'check_call' ? (a.amount ? 'call' : 'check') : a.kind, a.amount, a.all_in);
  const logLine = (a, players) => `${nameOf(players[a.player])} · ${logLabel(a)}`;
  const winnersText = (winners) =>
    winners.map((w) => `${nameOf(w)} +${bb(w.amount)} BB`).join(t('listSep')) || t('splitPot');
  const noteText = (note) => t(`note.${note.kind}`, note.kind === 'result'
    ? {actions: note.actions, net: bb(note.net)}
    : note.kind === 'pot_odds' ? {street: t(`street.${note.street}`), call: bb(note.call), eligible: bb(note.eligible), required: note.required} : {});
  function errorFrom(data, status) {
    const key = `error.${data.code}` in STRINGS[lang] ? `error.${data.code}` : null;
    return Object.assign(new Error(key ? t(key) : data.error), {status, code: data.code, key});
  }
  async function api(path, body, signal) {
    let response;
    try {
      response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', headers: {'Content-Type': 'application/json'}, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body), signal});
    } catch (error) {
      if (error.name === 'AbortError') throw error;
      throw Object.assign(new Error(t('connectionLost')), {key: 'connectionLost'});
    }
    let data;
    try { data = await response.json(); } catch { throw Object.assign(new Error(t('noResponse')), {key: 'noResponse'}); }
    if (!response.ok) throw errorFrom(data, response.status);
    return data;
  }
  const inviteCode = () => location.pathname.match(/^\/t\/([A-Za-z0-9_-]+)$/)?.[1] ?? null;
  const setState = (next) => { state = next; receivedAt = performance.now(); };
  // A slow reply must not undo a newer state the poll already delivered. The server
  // keeps versions increasing across table switches, so this holds for create and join.
  const accept = (next) => { if (!state || next.version >= state.version) setState(next); };
  const remaining = (seconds) => Math.max(0, Math.ceil(seconds - (performance.now() - receivedAt) / 1000));
  const countdown = (kind) => `<span class="countdown" data-countdown="${kind}"></span>`;
  // Countdowns tick locally between server updates.
  function tick() {
    document.querySelectorAll('[data-countdown]').forEach((el) => {
      const seconds = el.dataset.countdown === 'turn' ? state.turn_remaining : state.next_hand_in;
      el.textContent = seconds == null ? '' : `${remaining(seconds)}s`;
    });
  }
  setInterval(() => { if (state) tick(); }, 250);
  let noticeTimer = null;
  function notify(message) {
    clearTimeout(noticeTimer);
    $('notice').textContent = message; $('notice').hidden = false;
    noticeTimer = setTimeout(() => { $('notice').hidden = true; }, 4000);
  }
  let shownError = null;
  const errorText = (error) => (error.key ? t(error.key) : error.message || t('connectionLost'));
  function showError(error) { failed = true; stopPolling(); shownError = error; $('error-message').textContent = errorText(error); $('error-banner').hidden = false; }
  function clearError() { failed = false; $('error-banner').hidden = true; }
  function stopPolling() { poller?.abort(); poller = null; }
  // The server runs the game. Keep one long poll open while the tab is visible;
  // a hidden tab stops polling so the free server can sleep.
  async function poll() {
    if (poller || !state || failed || document.hidden) return;
    const controller = poller = new AbortController();
    try {
      while (poller === controller) {
        const next = await api(`/api/state?after=${state.version}`, undefined, controller.signal);
        if (poller === controller && next.version > state.version) { setState(next); render(); }
      }
    } catch (error) {
      if (poller === controller) { poller = null; showError(error); }
    }
  }
  async function transition(path, body = {}) {
    if (busy) return;
    busy = true; renderActions();
    try {
      accept(await api(path, body));
      clearError(); render();
    }
    catch (error) {
      // Someone joined, left or acted first: show the current table instead of failing.
      if (error.status !== 409 || !state) return showError(error);
      notify(error.message);
      try { accept(await api('/api/state')); render(); } catch (refresh) { showError(refresh); }
    }
    finally { busy = false; renderActions(); poll(); }
  }
  function applyStatic() {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    document.title = t('title');
    document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
  }
  function render() {
    if (!state) return;
    const players = state.players;
    $('street-label').textContent = state.complete ? t('handOver') : t(`street.${state.street}`);
    $('pot').innerHTML = `<span>${t(state.complete ? 'finalPot' : 'pot')}</span> <strong>${bb(state.pot)}</strong> <small>BB</small>`;
    $('board').innerHTML = cards(state.board, 5, true);
    const actor = players.find((p) => p.id === state.current_actor);
    $('table-message').textContent = state.pending ? t('pendingMsg')
      : state.complete ? winnersText(state.winners)
      : state.current_actor === state.you ? t('yourTurnMsg')
      : actor ? t('thinkingMsg', {name: nameOf(actor)}) : t('dealing');
    if (state.rebuys.length && rebuyHand !== state.hand_id) {
      rebuyHand = state.hand_id;
      notify(t('rebuys', {names: state.rebuys.map((seat) => nameOf(players[seat])).join(t('listSep'))}));
    }
    $('hand-marker').textContent = t('handNo', {n: state.hand_id});
    $('activity-hand').textContent = t('handNo', {n: String(state.hand_id).padStart(3, '0')});
    $('session-hands').innerHTML = `${Math.max(0, state.hand_id - (state.complete ? 0 : 1))} <small>${t('handsUnit')}</small>`;
    $('session-net').innerHTML = `${signed(state.session_net)} <small>BB</small>`;
    $('session-net').className = state.session_net > 0 ? 'positive' : state.session_net < 0 ? 'negative' : '';
    $('invite-card').hidden = !state.table.shared;
    $('invite-link').textContent = state.table.shared ? `${location.origin}/t/${state.table.invite}` : '';
    $('invite-button').hidden = state.table.shared;
    $('reset-button').hidden = state.table.shared;
    $('seats').innerHTML = players.map((p) => {
      const active = !state.complete && state.current_actor === p.id;
      const style = t(p.id === state.you ? 'style.you' : p.kind === 'human' ? 'style.friend' : `style.${p.style}`);
      const last = p.last_action;
      const status = p.leaving ? t('leaving') : p.away ? t('away') : p.all_in ? t('allIn')
        : active ? `${t('thinking')}${p.kind === 'human' ? countdown('turn') : ''}`
        : esc(last ? actionLabel(last.kind, last.amount, last.all_in) : t('seated'));
      return [
        `<div class="seat seat-${spot(p.id)} ${!p.in_hand ? 'folded' : ''} ${active ? 'active' : ''} ${p.all_in ? 'all-in' : ''}">`,
        '<div class="seat-person">',
        `<span class="avatar" style="--avatar-color:${p.color}">${esc(lang === 'en' ? p.name_en[0] : p.avatar)}</span>`,
        '<div class="seat-details">',
        `<div class="seat-name">${esc(nameOf(p))}</div>`,
        `<div class="seat-stack">${bb(p.stack)}<small>BB</small></div>`,
        '</div>',
        `<span class="seat-position">${state.dealer === p.id ? 'D' : esc(p.position)}</span>`,
        '</div>',
        `<div class="seat-style">${esc(style)}</div>`,
        `<div class="seat-cards">${cards(p.cards)}</div>`,
        `<div class="seat-action">${status}</div>`,
        '</div>',
        p.bet > 0 && !state.complete ? `<div class="bet-chip bet-${spot(p.id)}">${bb(p.bet)}</div>` : '',
      ].join('');
    }).join('');
    const list = $('activity-list'); const wasBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
    let previousStreet = '';
    list.innerHTML = state.actions.map((action) => {
      const divider = previousStreet !== action.street ? `<li class="street-divider">${esc(t(`street.${action.street}`))}</li>` : '';
      previousStreet = action.street;
      return `${divider}<li>${esc(logLine(action, players))}</li>`;
    }).join('') || `<li class="empty-activity">${t('activityReady')}</li>`;
    if (wasBottom) list.scrollTop = list.scrollHeight;
    renderActions();
    tick();
  }
  function renderActions() {
    if (!state) return;
    const panel = $('action-panel');
    if (state.players[state.you].away) {
      panel.innerHTML = `<div class="waiting-state">${t('awayPanel')}<button class="primary-button" id="back-action" ${busy ? 'disabled' : ''}>${t('back')}</button></div>`;
      $('back-action').onclick = () => transition('/api/back');
      return;
    }
    if (state.pending) {
      panel.innerHTML = `<div class="waiting-state"><span class="loading-dot"></span>${t('waitPending')}</div>`;
      return;
    }
    if (state.complete) {
      panel.innerHTML = [
        '<div class="hand-end">',
        '<div class="hand-end-copy">',
        `<p class="eyebrow">${t('eyebrowMore')}</p>`,
        `<h3>${esc(winnersText(state.winners))}</h3>`,
        `<p>${t('handEndCopy')}${state.next_hand_in == null ? '' : t('autoDeal', {c: countdown('deal')})}</p>`,
        '</div>',
        '<div class="hand-end-actions">',
        `<button class="secondary-button" id="review-hand" ${busy ? 'disabled' : ''}>${t('reviewHand')}</button>`,
        `<button class="primary-button" id="next-hand" ${busy ? 'disabled' : ''}>${t('nextHand')} <span aria-hidden="true">→</span></button>`,
        '</div>',
        '</div>',
      ].join('');
      $('review-hand').onclick = () => openHistory(state.hand_id);
      $('next-hand').onclick = () => transition('/api/next', {version: state.version});
      return;
    }
    if (state.current_actor !== state.you) {
      const actor = state.players.find((p) => p.id === state.current_actor);
      const waiting = actor ? t('waitActor', {name: nameOf(actor)}) : t('dealing');
      panel.innerHTML = `<div class="waiting-state"><span class="loading-dot"></span>${esc(waiting)}<span style="color:#a2aa97;font-size:10px;margin-left:8px">${t('waitHint')}</span></div>`;
      return;
    }
    const legal = state.legal, min = legal.min_raise_to, max = legal.max_raise_to;
    if (amountVersion !== state.version) { amount = min; amountVersion = state.version; }
    amount = Math.max(min, Math.min(max, Number(amount) || min));
    const hero = state.players.find((p) => p.id === state.you), canRaise = legal.can_raise;
    const disabled = busy ? 'disabled' : '';
    const raiseLabel = () => `${amount === max ? t('allIn') : t('raiseTo')}<span id="raise-label">${bb(amount)} BB</span>`;
    const sizing = [
      '<div class="sizing">',
      `<label for="raise-slider">${t('raiseTo')}</label>`,
      `<input id="raise-slider" aria-label="${t('raiseAria')}" type="range" min="${min}" max="${max}" value="${amount}" step="1" ${disabled}>`,
      '<div class="amount-input">',
      `<input id="raise-amount" type="number" aria-label="${t('raiseAriaBB')}" min="${min / 2}" max="${max / 2}" step="0.5" value="${amount / 2}" ${disabled}>`,
      '<span>BB</span>',
      '</div>',
      '<div class="sizing-presets">',
      `<button type="button" data-size="half" ${disabled}>${t('halfPot')}</button>`,
      `<button type="button" data-size="pot" ${disabled}>${t('potSize')}</button>`,
      `<button type="button" data-size="all" ${disabled}>${t('allIn')}</button>`,
      '</div>',
      '</div>',
    ].join('');
    panel.innerHTML = [
      '<div class="action-heading">',
      `<strong>${t('yourTurn')}${state.turn_remaining == null ? '' : countdown('turn')}</strong>`,
      `<small>${esc(hero.position)} · ${legal.can_check ? t('freeLook') : t('toCall', {a: bb(legal.call_amount)})}</small>`,
      '</div>',
      canRaise ? sizing : '',
      '<div class="action-buttons">',
      `<button class="action-button" id="fold-action" ${busy || !legal.can_fold ? 'disabled' : ''}>${t('fold')}</button>`,
      `<button class="action-button call" id="call-action" ${busy || (!legal.can_check && !legal.call_amount) ? 'disabled' : ''}>`,
      `${legal.can_check ? t('check') : t('call')}${!legal.can_check ? `<span>${bb(legal.call_amount)} BB</span>` : ''}`,
      '</button>',
      `<button class="action-button raise" id="raise-action" ${busy || !canRaise ? 'disabled' : ''}>`,
      canRaise ? raiseLabel() : `${t('raiseTo')}<span id="raise-label">${t('cantRaise')}</span>`,
      '</button>',
      '</div>',
    ].join('');
    $('fold-action').onclick = () => transition('/api/action', {version: state.version, action: 'fold'});
    $('call-action').onclick = () => transition('/api/action', {version: state.version, action: 'check_call'});
    $('raise-action').onclick = () => transition('/api/action', {version: state.version, action: 'raise', amount: Math.round(amount)});
    if (canRaise) {
      const setAmount = (value) => { amount = Math.max(min, Math.min(max, Math.round(Number(value) || min))); $('raise-slider').value = amount; $('raise-amount').value = amount / 2; $('raise-action').innerHTML = raiseLabel(); };
      $('raise-slider').oninput = (event) => setAmount(event.target.value);
      $('raise-amount').onchange = (event) => setAmount(Number(event.target.value) * 2);
      panel.querySelectorAll('[data-size]').forEach((button) => { button.onclick = () => {
        const base = hero.bet + legal.call_amount, potAfterCall = state.pot + legal.call_amount;
        setAmount(button.dataset.size === 'all' ? max : base + potAfterCall * (button.dataset.size === 'half' ? .5 : 1));
      }; });
    }
  }
  async function openHistory(handId) {
    if (!$('history-dialog').open) $('history-dialog').showModal();
    $('history-content').innerHTML = `<div class="waiting-state"><span class="loading-dot"></span>${t('loadingHistory')}</div>`;
    try {
      if (handId) { replay = await api(`/api/hand/${handId}`); replayIndex = 0; renderReplay(); }
      else {
        const data = await api('/api/history'); replay = null;
        const hands = data.hands;
        const handRow = (hand) => [
          `<button class="history-hand" data-hand="${hand.hand_id}">`,
          `<span class="hand-number">${String(hand.hand_id).padStart(2, '0')}</span>`,
          '<span class="hand-copy">',
          `<strong>${esc(winnersText(hand.winners))}</strong>`,
          `<small>${hand.board.map(esc).join(' · ') || t('endedPreflop')} · ${t('tapReplay')}</small>`,
          '</span>',
          `<span class="hand-net ${hand.net > 0 ? 'positive' : hand.net < 0 ? 'negative' : ''}">`,
          `${signed(hand.net)} <small style="font:9px var(--sans)">BB</small>`,
          '</span>',
          '</button>',
        ].join('');
        $('history-content').innerHTML = hands.length
          ? hands.map(handRow).join('')
          : `<div class="history-empty">${t('historyEmpty')}<br>${t('historyEmptyHint')}</div>`;
        $('history-content').querySelectorAll('[data-hand]').forEach((button) => { button.onclick = () => openHistory(Number(button.dataset.hand)); });
      }
    } catch (error) { $('history-content').innerHTML = `<div class="history-empty">${esc(error.message)}<br><button id="retry-history" class="secondary-button">${t('retryShort')}</button></div>`; $('retry-history').onclick = () => openHistory(handId); }
  }
  function renderReplay() {
    const frames = replay.frames, frame = frames[replayIndex];
    const lastAction = frame.actions.at(-1), last = replayIndex === frames.length - 1;
    const playerRow = (p) => [
      `<div class="replay-player ${!p.in_hand ? 'folded' : ''}">`,
      '<div>',
      `<div class="replay-player-name">${esc(nameOf(p))}</div>`,
      `<div class="replay-player-stack">${bb(p.stack)} BB ${p.all_in ? `· ${t('allIn')}` : ''}</div>`,
      '</div>',
      `<div class="replay-cards">${cards(p.cards)}</div>`,
      '</div>',
    ].join('');
    const notes = replay.notes.map((note) => `<p>${esc(noteText(note))}</p>`).join('');
    const event = frame.complete ? winnersText(frame.winners)
      : lastAction ? logLine(lastAction, frame.players) : t('replayStart');
    $('history-content').innerHTML = [
      `<button class="replay-back" id="back-history">${t('allHands')}</button>`,
      '<div class="replay-heading">',
      `<h3>${t('handNo', {n: replay.hand_id})}</h3>`,
      `<span>${t('replayStep', {i: replayIndex + 1, n: frames.length})}</span>`,
      '</div>',
      '<div class="replay-board">',
      `<div class="replay-board-label">${esc(t(`street.${frame.street}`))} ${frame.complete ? t('finished') : ''}</div>`,
      `<div class="board">${cards(frame.board, 5, true)}</div>`,
      `<div class="replay-pot">${bb(frame.pot)} <small style="font:9px var(--sans)">${t('potSuffix')}</small></div>`,
      '</div>',
      '<div class="replay-controls">',
      `<button id="replay-prev" aria-label="${t('prevStep')}" ${replayIndex === 0 ? 'disabled' : ''}>←</button>`,
      `<input type="range" id="replay-slider" min="0" max="${frames.length - 1}" value="${replayIndex}" step="1" aria-label="${t('replayProgress')}">`,
      `<button id="replay-next" aria-label="${t('nextStep')}" ${last ? 'disabled' : ''}>→</button>`,
      '</div>',
      `<div class="replay-event">${esc(event)}</div>`,
      `<div class="replay-players">${frame.players.map(playerRow).join('')}</div>`,
      `<div class="review-notes"><h4>${t('notesTitle')}</h4>${notes}</div>`,
      `<p class="replay-disclaimer">${t('disclaimer')}</p>`,
    ].join('');
    $('back-history').onclick = () => openHistory();
    $('replay-prev').onclick = () => { replayIndex = Math.max(0, replayIndex - 1); renderReplay(); };
    $('replay-next').onclick = () => { replayIndex = Math.min(frames.length - 1, replayIndex + 1); renderReplay(); };
    $('replay-slider').onchange = (event) => { replayIndex = Number(event.target.value); renderReplay(); $('replay-slider').focus(); };
  }
  $('history-button').onclick = () => openHistory();
  $('close-history').onclick = () => $('history-dialog').close();
  $('reset-button').onclick = () => $('reset-dialog').showModal();
  $('cancel-reset').onclick = () => $('reset-dialog').close();
  $('confirm-reset').onclick = () => { $('reset-dialog').close(); transition('/api/reset'); };
  // Shared tables: create one from the solo table, or join one from an invite link.
  let nameMode = null;
  const savedName = () => { try { return localStorage.getItem('poker-lab-name') || ''; } catch { return ''; } };
  function nameDialogText() {
    $('name-title').textContent = t(nameMode === 'create' ? 'createTitle' : 'joinTitle');
    $('name-copy').textContent = t(nameMode === 'create' ? 'createCopy' : 'joinCopy');
    $('confirm-name').textContent = t(nameMode === 'create' ? 'createButton' : 'joinButton');
  }
  function askName(mode) {
    nameMode = mode;
    nameDialogText();
    $('name-input').value = savedName();
    $('name-dialog').showModal();
  }
  async function submitName(name) {
    try { localStorage.setItem('poker-lab-name', name); } catch {}
    busy = true; renderActions();
    try {
      accept(await api(nameMode === 'join' ? '/api/join' : '/api/tables',
                       nameMode === 'join' ? {code: inviteCode(), name} : {name}));
      history.replaceState(null, '', `/t/${state.table.invite}`);
      clearError(); render();
    } catch (error) {
      if (error.status === 400) { notify(error.message); askName(nameMode); }
      else if (error.status === 404 || error.status === 409) { notify(error.message); history.replaceState(null, '', '/'); }
      else showError(error);
    } finally { busy = false; renderActions(); poll(); }
  }
  $('name-form').onsubmit = () => submitName($('name-input').value.trim());
  $('cancel-name').onclick = () => {
    $('name-dialog').close();
    if (nameMode === 'join') history.replaceState(null, '', '/');
  };
  $('invite-button').onclick = () => askName('create');
  $('copy-invite').onclick = async () => {
    try { await navigator.clipboard.writeText($('invite-link').textContent); notify(t('copied')); }
    catch { notify(t('copyFailed')); }
  };
  $('leave-table').onclick = async () => {
    await transition('/api/leave');
    if (!state.table.shared) history.replaceState(null, '', '/');
  };
  // Switching language re-renders everything in place, mid-hand included.
  $('lang-button').onclick = () => {
    lang = lang === 'zh' ? 'en' : 'zh';
    try { localStorage.setItem('poker-lab-lang', lang); } catch {}
    applyStatic();
    render();
    if (!$('error-banner').hidden) $('error-message').textContent = errorText(shownError);
    if (nameMode && $('name-dialog').open) nameDialogText();
    if ($('history-dialog').open) { if (replay) renderReplay(); else openHistory(); }
  };
  const checkInvite = () => {
    if (inviteCode() && state && state.table.invite !== inviteCode()) askName('join');
  };
  $('retry-button').onclick = async () => {
    if (busy) return; busy = true;
    // After a server restart the new session's versions start lower, so replace outright.
    try { setState(await api('/api/session', {})); clearError(); render(); checkInvite(); }
    catch (error) { showError(error); }
    finally { busy = false; renderActions(); poll(); }
  };
  document.addEventListener('visibilitychange', () => { if (document.hidden) stopPolling(); else poll(); });
  applyStatic();
  transition('/api/session').then(checkInvite);
})();
