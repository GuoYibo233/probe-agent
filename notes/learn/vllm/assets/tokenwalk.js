/* Token-by-token stepper. Data is embedded in #twdata by build_token_walk.py,
   each token already carries {id, s, ch, rcp, b} -- channel classification is done on the converter side,
   this file is only responsible for releasing them one at a time, it doesn't recompute the rules. */

(function () {
  var host = document.getElementById('tw');
  var raw = document.getElementById('twdata');
  if (!host || !raw) return;

  var DATA = JSON.parse(raw.textContent);
  var LANES = DATA.steps.concat([DATA.toolcall]);

  var BUCKET = {
    reasoning: 'thinking analysis',
    content: 'body final',
    tool: 'tool commentary to=',
    drop: 'dropped',
    frame: 'structural markers'
  };

  var cur = 0;   // which lane number
  var i = 0;     // how many tokens have been released so far

  host.innerHTML =
    '<div class="tw">' +
      '<div class="tw-steps" role="group" aria-label="select a step"></div>' +
      '<div class="tw-bar">' +
        '<span>token <b class="pos">0</b> / <span class="tot">0</span></span>' +
        '<span>prompt <b class="np">0</b> tokens</span>' +
        '<span>channel <b class="chan">—</b></span>' +
        '<span>recipient <b class="rcp">—</b></span>' +
      '</div>' +
      '<div class="tw-cur"><span class="id">—</span>' +
        '<span class="piece"></span><span class="dest"></span></div>' +
      '<div class="tw-stream" tabindex="0" aria-live="off"></div>' +
      '<div class="tw-buckets"></div>' +
      '<div class="tw-ctl">' +
        '<button class="primary" data-a="one">next token</button>' +
        '<button data-a="turn">next turning point</button>' +
        '<button data-a="end">run to end</button>' +
        '<button data-a="reset">back to start</button>' +
      '</div>' +
      '<p class="tw-hint">Keyboard: → or space advances one token, Shift+→ jumps to the next turning point. ' +
      'Turning point = a channel switch or a closing marker.</p>' +
      '<div class="tw-tail"></div>' +
    '</div>';

  var $ = function (s) { return host.querySelector(s); };
  var elSteps = $('.tw-steps'), elStream = $('.tw-stream'),
      elBuckets = $('.tw-buckets'), elTail = $('.tw-tail'),
      elCur = $('.tw-cur');

  LANES.forEach(function (lane, n) {
    var b = document.createElement('button');
    b.textContent = lane.step === 'tool' ? 'single tool call' : ('step ' + lane.step);
    b.setAttribute('aria-pressed', 'false');
    b.addEventListener('click', function () { cur = n; i = 0; render(true); });
    elSteps.appendChild(b);
  });

  function lane() { return LANES[cur]; }

  function isTurn(n) {
    // Turning point: this token's channel/recipient differs from the previous one, or it's a closing marker
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
      d.innerHTML = '<b>' + (count[k4] || 0) + '</b>' + BUCKET[k4] + ' · characters';
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
      h += '<p>This one is a standalone send: the question and tool definitions come from the 2026-08-02 ToolHop ' +
           'record, entry 0; there are ' + L.tool_names.length + ' tools (' +
           esc(L.tool_names.join(', ')) + ').' +
           'AppWorld\'s prompt chain has no tools, so it never reaches the tool-call channel.</p>';
    }
    h += '<p>Last 260 characters of the prompt (generation continues from here):</p><pre>' +
         esc(L.prompt_tail) + '</pre>';
    if (done) {
      h += '<p>This step stopped at <code>finish_reason=' + esc(String(L.finish)) +
           '</code>, <code>stop_reason=' + esc(String(L.stop)) + '</code>, ' +
           'using ' + L.usage.out + ' output tokens.';
      if (L.stop === null) {
        h += ' stop_reason is null because it was stopped by the model\'s own built-in eos (' +
             '<code>&lt;|return|&gt;</code>), not a stop word we passed.';
      }
      h += '</p>';
      if (L.action) {
        h += '<p>The code pulled out of the body text and actually run in AppWorld:</p><pre>' +
             esc(L.action) + '</pre>';
      }
      if (L.env) {
        h += '<p>Environment\'s response (this becomes the next step\'s user message):</p><pre>' +
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
