/* Shared quiz component. Usage (no JS needed in the HTML):
 *
 *   <div class="quiz" data-answer="b">
 *     <p class="q">question stem</p>
 *     <div class="opts">
 *       <button data-k="a">option one</button>
 *       <button data-k="b">option two</button>
 *     </div>
 *     <p class="fb" data-k="a">feedback shown when a is picked</p>
 *     <p class="fb" data-k="b">feedback shown when b is picked</p>
 *   </div>
 *
 * Feedback appears immediately and locks once answered. If the page has a <p class="score"> at the bottom, it's scored automatically.
 */
(function () {
  function init() {
    var quizzes = Array.prototype.slice.call(document.querySelectorAll('.quiz'));
    var done = 0, right = 0;
    var board = document.querySelector('.score');

    function paint() {
      if (!board) return;
      board.textContent = 'Answered ' + done + '/' + quizzes.length + ', correct ' + right;
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
