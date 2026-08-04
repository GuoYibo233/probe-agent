/* 共用测验组件。用法（HTML 里不写任何 JS）：
 *
 *   <div class="quiz" data-answer="b">
 *     <p class="q">题干</p>
 *     <div class="opts">
 *       <button data-k="a">选项一</button>
 *       <button data-k="b">选项二</button>
 *     </div>
 *     <p class="fb" data-k="a">选 a 时给的反馈</p>
 *     <p class="fb" data-k="b">选 b 时给的反馈</p>
 *   </div>
 *
 * 反馈立刻出，答完锁定。页面底部若有 <p class="score"> 会自动计分。
 */
(function () {
  function init() {
    var quizzes = Array.prototype.slice.call(document.querySelectorAll('.quiz'));
    var done = 0, right = 0;
    var board = document.querySelector('.score');

    function paint() {
      if (!board) return;
      board.textContent = '已答 ' + done + '/' + quizzes.length + '，答对 ' + right;
    }
    paint();

    quizzes.forEach(function (quiz) {
      var key = quiz.getAttribute('data-answer');
      var btns = Array.prototype.slice.call(quiz.querySelectorAll('.opts button'));

      btns.forEach(function (btn) {
        btn.addEventListener('click', function () {
          if (quiz.getAttribute('data-done')) return;

          var picked = btn.getAttribute('data-k');
          var ok = picked === key;
          quiz.setAttribute('data-done', ok ? 'right' : 'wrong');
          done += 1;
          if (ok) right += 1;
          paint();

          btns.forEach(function (b) {
            b.disabled = true;
            var k = b.getAttribute('data-k');
            if (k === key) b.classList.add('right');
            else if (k === picked) b.classList.add('wrong');
          });

          var fb = quiz.querySelector('.fb[data-k="' + picked + '"]')
                || quiz.querySelector('.fb:not([data-k])');
          if (fb) fb.classList.add('show');
        });
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
