/* 逐 token 步进器。数据由 build_token_walk.py 嵌在 #twdata 里，
   每个 token 已经带好了 {id, s, ch, rcp, b}——频道判定在转换器那边做完，
   这里只负责一个一个放出来，不重算规则。 */

(function () {
  var host = document.getElementById('tw');
  var raw = document.getElementById('twdata');
  if (!host || !raw) return;

  var DATA = JSON.parse(raw.textContent);
  var LANES = DATA.steps.concat([DATA.toolcall]);

  var BUCKET = {
    reasoning: '思考 analysis',
    content: '正文 final',
    tool: '工具 commentary to=',
    drop: '丢掉',
    frame: '结构标记'
  };

  var cur = 0;   // 第几条 lane
  var i = 0;     // 已放出多少个 token

  host.innerHTML =
    '<div class="tw">' +
      '<div class="tw-steps" role="group" aria-label="选一步"></div>' +
      '<div class="tw-bar">' +
        '<span>token <b class="pos">0</b> / <span class="tot">0</span></span>' +
        '<span>提示词 <b class="np">0</b> 个 token</span>' +
        '<span>频道 <b class="chan">—</b></span>' +
        '<span>收件人 <b class="rcp">—</b></span>' +
      '</div>' +
      '<div class="tw-cur"><span class="id">—</span>' +
        '<span class="piece"></span><span class="dest"></span></div>' +
      '<div class="tw-stream" tabindex="0" aria-live="off"></div>' +
      '<div class="tw-buckets"></div>' +
      '<div class="tw-ctl">' +
        '<button class="primary" data-a="one">下一个 token</button>' +
        '<button data-a="turn">下一个转折点</button>' +
        '<button data-a="end">跑到底</button>' +
        '<button data-a="reset">回开头</button>' +
      '</div>' +
      '<p class="tw-hint">键盘：→ 或空格前进一个 token，Shift+→ 跳到下一个转折点。' +
      '转折点 = 频道切换或收尾标记。</p>' +
      '<div class="tw-tail"></div>' +
    '</div>';

  var $ = function (s) { return host.querySelector(s); };
  var elSteps = $('.tw-steps'), elStream = $('.tw-stream'),
      elBuckets = $('.tw-buckets'), elTail = $('.tw-tail'),
      elCur = $('.tw-cur');

  LANES.forEach(function (lane, n) {
    var b = document.createElement('button');
    b.textContent = lane.step === 'tool' ? '工具调用单发' : ('第 ' + lane.step + ' 步');
    b.setAttribute('aria-pressed', 'false');
    b.addEventListener('click', function () { cur = n; i = 0; render(true); });
    elSteps.appendChild(b);
  });

  function lane() { return LANES[cur]; }

  function isTurn(n) {
    // 转折点：这个 token 的频道/收件人跟上一个不一样，或者它是收尾标记
    var t = lane().tokens[n];
    if (!t) return false;
    if (/^<\|(end|return|call)\|>$/.test(t.s)) return true;
    var p = lane().tokens[n - 1];
    if (!p) return true;
    return p.ch !== t.ch || p.rcp !== t.rcp;
  }

  function spanFor(t, n) {
    var e = document.createElement('span');
    e.className = 'b-' + t.b;
    e.dataset.n = n;
    e.textContent = t.s;
    return e;
  }

  function render(hard) {
    var L = lane(), toks = L.tokens;
    Array.prototype.forEach.call(elSteps.children, function (b, n) {
      b.setAttribute('aria-pressed', n === cur ? 'true' : 'false');
    });

    if (hard || elStream.childElementCount > i) {
      elStream.textContent = '';
      for (var k = 0; k < i; k++) elStream.appendChild(spanFor(toks[k], k));
    } else {
      for (var k2 = elStream.childElementCount; k2 < i; k2++) {
        elStream.appendChild(spanFor(toks[k2], k2));
      }
    }
    var last = elStream.lastElementChild;
    Array.prototype.forEach.call(elStream.querySelectorAll('.now'), function (e) {
      e.classList.remove('now');
    });
    if (last) {
      last.classList.add('now');
      last.scrollIntoView({ block: 'nearest' });
    }

    var t = i > 0 ? toks[i - 1] : null;
    $('.pos').textContent = i;
    $('.tot').textContent = toks.length;
    $('.np').textContent = L.n_prompt;
    $('.chan').textContent = t && t.ch ? t.ch : '—';
    $('.rcp').textContent = t && t.rcp ? t.rcp : '—';
    $('.id').textContent = t ? t.id : '—';
    var piece = $('.piece');
    piece.textContent = t ? t.s : '';
    piece.className = 'piece' + (t && t.b === 'frame' ? ' frame' : '');
    $('.dest').textContent = t ? ('→ ' + BUCKET[t.b]) : '';
    elCur.dataset.b = t ? t.b : '';

    var count = {};
    for (var k3 = 0; k3 < i; k3++) {
      var b = toks[k3].b;
      count[b] = (count[b] || 0) + toks[k3].s.length;
    }
    elBuckets.textContent = '';
    ['reasoning', 'content', 'tool', 'drop', 'frame'].forEach(function (k4) {
      var d = document.createElement('div');
      d.className = 'k-' + k4;
      d.innerHTML = '<b>' + (count[k4] || 0) + '</b>' + BUCKET[k4] + ' · 字符';
      elBuckets.appendChild(d);
    });

    $('[data-a="one"]').disabled = i >= toks.length;
    $('[data-a="turn"]').disabled = i >= toks.length;
    $('[data-a="end"]').disabled = i >= toks.length;

    renderTail(L, i >= toks.length);
  }

  function renderTail(L, done) {
    var h = '';
    if (L.step === 'tool') {
      h += '<p>这一条是单独发的：题目与工具定义取自 2026-08-02 那次 ToolHop ' +
           '记录的第 0 条，工具有 ' + L.tool_names.length + ' 个（' +
           esc(L.tool_names.join('、')) + '）。' +
           'AppWorld 那条链的提示词里没有 tools，所以走不出工具调用这条频道。</p>';
    }
    h += '<p>提示词最后 260 个字符（生成从这里接着往下写）：</p><pre>' +
         esc(L.prompt_tail) + '</pre>';
    if (done) {
      h += '<p>这一步停在 <code>finish_reason=' + esc(String(L.finish)) +
           '</code>，<code>stop_reason=' + esc(String(L.stop)) + '</code>，' +
           '用了 ' + L.usage.out + ' 个输出 token。';
      if (L.stop === null) {
        h += ' stop_reason 是 null，因为停它的是模型自带的 eos（' +
             '<code>&lt;|return|&gt;</code>），不是我们传的停止词。';
      }
      h += '</p>';
      if (L.action) {
        h += '<p>从正文里抠出来、真的丢进 AppWorld 执行的代码：</p><pre>' +
             esc(L.action) + '</pre>';
      }
      if (L.env) {
        h += '<p>环境返回（下一步的 user 消息就是它）：</p><pre>' +
             esc(L.env) + '</pre>';
      }
    }
    elTail.innerHTML = h;
  }

  function esc(s) {
    return String(s === undefined || s === null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function step(n) { i = Math.min(lane().tokens.length, i + n); render(false); }

  function toTurn() {
    var toks = lane().tokens;
    var n = i + 1;
    while (n < toks.length && !isTurn(n)) n++;
    i = Math.min(toks.length, n + 1);
    render(false);
  }

  host.addEventListener('click', function (e) {
    var b = e.target.closest('[data-a]');
    if (!b) return;
    if (b.dataset.a === 'one') step(1);
    else if (b.dataset.a === 'turn') toTurn();
    else if (b.dataset.a === 'end') { i = lane().tokens.length; render(false); }
    else if (b.dataset.a === 'reset') { i = 0; render(true); }
  });

  document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'ArrowRight' || e.key === ' ') {
      e.preventDefault();
      if (e.shiftKey) toTurn(); else step(1);
    }
  });

  render(true);
})();
