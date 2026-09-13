/* 花瓣粒子层
   自下而上飘动的粉色花瓣；鼠标附近的会被"吸附"过来绕指轻转。
   - 数量：1300 片（平行类型化数组；想要更密/更疏改 COUNT 即可）
   - 绘制：全部走同一条"纯色路径填充"管线 —— 小花瓣是圆点（arc），
     大花瓣是压扁并带旋转的椭圆（ellipse，看起来像侧过来的花瓣）。
   - 半分辨率渲染，再由 CSS 放大铺满视口
   - 吸附：力场式，近处改为轻推形成"环"，并带切向分量让花瓣绕着指针转
   - 美化点：风感横移、近大远小的景深、更扁的花瓣、更多低透明度层次
*/
(function () {
  "use strict";
  var canvas = document.getElementById("petals");
  if (!canvas || !canvas.getContext) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  var ctx = canvas.getContext("2d");
  var W = 0, H = 0;
  var SCALE = 0.5;

  /* ---------- 可调参数 ---------- */
  var COUNT = 1300;               // 粒子总数（移动端可降到 700~900）
  var BIG_RATIO = 0.18;           // 大花瓣比例，高一点形状更丰富
  var SHIFT = 6;                  // 每 64 片共用一个颜色/透明度，减少色块感

  var SMALL_SIZES = [1.2, 1.6, 2.0, 2.4, 2.8];      // 小花瓣半径（量化成 5 档）
  var BIG_SIZES = [3.8, 4.6, 5.4, 6.2, 7.0];        // 大花瓣半高（量化成 5 档）

  var REACH = 240;                // 鼠标影响半径（px）
  var REACH2 = REACH * REACH;
  var RING = 64;                  // 吸附环：比它更近就改为轻推，避免堆在指针上抖
  var RELAX = 0.03;               // 速度回归自然漂移的速率
  var PULL = 0.035;               // 向指针的吸力（减弱，别吸成一坨）
  var PUSH = 0.11;                // 环内的推力
  var SWIRL = 1.25;               // 切向力（增强，绕指针打转更明显）
  var ALIGN = 0.04;               // 大花瓣转向指针的强度
  var VMAX = 2.8, VMAX2 = VMAX * VMAX;
  var WIND = 0.06;                // 整体横向风，让飘动有方向感

  var TAU = Math.PI * 2;
  var COLS = 5, ALPHAS = 5;
  var BUCKETS = [0.045, 0.08, 0.13, 0.20, 0.30];    // 更多低透明度，层次更柔

  var DOTS = [];                  // 颜色串（颜色 × 透明度）
  var NBLOCK = Math.ceil(COUNT / (1 << SHIFT));
  var BLOCK = new Uint8Array(NBLOCK);   // 每块的（颜色,透明度）组合编号

  /* 花瓣颜色跟着页面主体色（--accent）走 */
  function accentPalette() {
    var fallback = ["240,166,192", "246,197,216", "250,214,228", "233,163,190", "252,226,236"];
    var raw = "";
    try {
      raw = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
    } catch (e) { /* ignore */ }
    var m = /^#?([0-9a-f]{6})$/i.exec(raw);
    if (!m) return fallback;
    var n = parseInt(m[1], 16);
    var r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    function mix(k) {
      var f = function (c) {
        return Math.max(0, Math.min(255, Math.round(k > 1 ? c + (255 - c) * (k - 1) : c * k)));
      };
      return f(r) + "," + f(g) + "," + f(b);
    }
    return [mix(0.78), mix(0.92), mix(1), mix(1.16), mix(1.3)];
  }
  var PALETTE = accentPalette();

  function bake() {
    DOTS = [];
    for (var ci = 0; ci < COLS; ci++) {
      for (var ai = 0; ai < ALPHAS; ai++) {
        DOTS.push("rgba(" + PALETTE[ci] + "," + BUCKETS[ai] + ")");
      }
    }
    /* 块 -> (颜色, 透明度)：铺开，保证每种组合都有粒子 */
    var total = COLS * ALPHAS;
    for (var b = 0; b < NBLOCK; b++) BLOCK[b] = (b * 13 + 7) % total;
  }

  /* 平行数组 */
  var xs, ys, vxs, vys, sizes, rots, rvs, phs, phvs, sways, ups, bigs;

  function seed() {
    var n = COUNT;
    xs = new Float32Array(n); ys = new Float32Array(n);
    vxs = new Float32Array(n); vys = new Float32Array(n);
    sizes = new Float32Array(n); rots = new Float32Array(n);
    rvs = new Float32Array(n); phs = new Float32Array(n);
    phvs = new Float32Array(n); sways = new Float32Array(n);
    ups = new Float32Array(n); bigs = new Uint8Array(n);
    for (var i = 0; i < n; i++) initPetal(i, false);
    if (window.__petalStats) window.__petalStats.n = n;
  }

  function initPetal(i, fromBottom) {
    var big = Math.random() < BIG_RATIO;
    bigs[i] = big ? 1 : 0;

    var base = big ? BIG_SIZES[(Math.random() * BIG_SIZES.length) | 0]
                   : SMALL_SIZES[(Math.random() * SMALL_SIZES.length) | 0];
    /* 景深：0.7~1.3 的尺寸系数，制造近大远小 */
    var depth = 0.7 + Math.random() * 0.6;
    sizes[i] = base * depth;

    xs[i] = Math.random() * W;
    ys[i] = fromBottom ? H + 20 + Math.random() * 60 : Math.random() * H;

    /* 远的小花瓣飘得慢，近的大花瓣飘得快 */
    ups[i] = (0.16 + Math.random() * 0.46) * (0.75 + depth * 0.4);
    vxs[i] = 0;
    vys[i] = -ups[i];
    sways[i] = 0.5 + Math.random() * 1.6;
    phs[i] = Math.random() * TAU;
    phvs[i] = 0.004 + Math.random() * 0.008;
    rots[i] = Math.random() * TAU;
    rvs[i] = (Math.random() - 0.5) * 0.012;
  }

  var mouse = { x: -9999, y: -9999, on: false };
  var dt = 16.667;

  /* 1) 物理：位移 + 鼠标力场 + 边界回收 */
  function physics(t) {
    var mOn = mouse.on, mx = mouse.x, my = mouse.y;
    for (var i = 0; i < COUNT; i++) {
      var x = xs[i], y = ys[i];

      phs[i] += phvs[i] * t;

      /* 左右摆动 + 整体风，回归自然漂移速度 */
      var vx = vxs[i] + (Math.sin(phs[i]) * 0.24 * sways[i] + WIND - vxs[i]) * RELAX * t;
      var vy = vys[i] + (-ups[i] - vys[i]) * RELAX * t;

      if (mOn) {
        var dx = mx - x, dy = my - y;
        var d2 = dx * dx + dy * dy;
        if (d2 < REACH2) {
          var d = Math.sqrt(d2);
          if (d < 0.6) d = 0.6;                       // 距离过小时方向会乱跳
          var nx = dx / d, ny = dy / d;
          var w = 1 - d / REACH;                      // 边界处自然为 0，无突变
          var pull = d > RING ? w * PULL : -(1 - d / RING) * PUSH;
          vx += (nx * pull + (-ny) * pull * SWIRL) * t;
          vy += (ny * pull + nx * pull * SWIRL) * t;

          if (bigs[i]) {                              // 只有大花瓣需要转向指针
            var diff = Math.atan2(dx, -dy) - rots[i];
            diff = ((diff + Math.PI) % TAU + TAU) % TAU - Math.PI;
            rots[i] += diff * ALIGN * w * t;
          }

          var sp2 = vx * vx + vy * vy;
          if (sp2 > VMAX2) {
            var sc = VMAX / Math.sqrt(sp2);
            vx *= sc; vy *= sc;
          }
        }
      }

      x += vx * t;
      y += vy * t;

      if (y < -30) {                                  // 飘出顶部：从底部重新放一片
        initPetal(i, true);
        x = xs[i]; y = ys[i]; vx = 0; vy = vys[i];
      } else if (x < -26) {
        x = W + 22;
      } else if (x > W + 26) {
        x = -22;
      }

      xs[i] = x; ys[i] = y; vxs[i] = vx; vys[i] = vy;
    }
  }

  /* 2) 绘制：一遍走完，全是纯色路径填充（同块才重设 fillStyle）
        小花瓣 = 圆点；大花瓣 = 压扁并带自身旋转的椭圆 */
  function draw(t) {
    var last = -1;
    for (var i = 0; i < COUNT; i++) {
      var b = BLOCK[i >> SHIFT];
      if (b !== last) { ctx.fillStyle = DOTS[b]; last = b; }

      var s = sizes[i];
      ctx.beginPath();
      if (bigs[i]) {
        var rot = rots[i] + rvs[i] * t;
        if (rot >= TAU) rot -= TAU;
        else if (rot < 0) rot += TAU;
        rots[i] = rot;
        /* 更扁的椭圆，像被风侧过来的花瓣 */
        ctx.ellipse(xs[i], ys[i], s * 1.35, s * 0.55, rot, 0, TAU);
      } else {
        ctx.arc(xs[i], ys[i], s, 0, TAU);
      }
      ctx.fill();
    }
  }

  function frame(ts) {
    if (frame._last) dt = Math.min(50, Math.max(4, ts - frame._last));
    frame._last = ts;
    var t = dt / 16.667;

    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    ctx.clearRect(0, 0, W, H);

    physics(t);
    draw(t);

    requestAnimationFrame(frame);
  }

  function resize() {
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = Math.ceil(W * SCALE);
    canvas.height = Math.ceil(H * SCALE);
    ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
    bake();
    seed();
  }

  window.addEventListener("resize", function () {
    clearTimeout(resize._t);
    resize._t = setTimeout(resize, 200);
  });

  window.addEventListener("mousemove", function (e) {
    mouse.x = e.clientX; mouse.y = e.clientY; mouse.on = true;
  }, { passive: true });

  window.addEventListener("mouseleave", function () {
    mouse.on = false; mouse.x = -9999; mouse.y = -9999;
  });

  window.addEventListener("blur", function () {
    mouse.on = false;
  });

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) frame._last = 0;
  });

  window.__petalStats = { n: 0 };
  resize();
  requestAnimationFrame(frame);
})();