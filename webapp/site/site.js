/* iSofa — veb-sayt: savatcha, filtr, galereya. Savatcha Telegram ilovasi bilan bir xil joyda saqlanadi
   (localStorage "cart"), shuning uchun «Rasmiylashtirish» bosilganda ilova o'sha savatchani ko'radi. */
"use strict";
(function () {
  const B = JSON.parse(document.getElementById("boot").textContent);
  const P = B.products, T = B.t, LANG = B.lang;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = n => Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " " + T.som;
  const store = {
    get(k, d) { try { const v = JSON.parse(localStorage.getItem(k)); return v ?? d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* maxfiy rejim */ } },
  };
  store.set("lang", LANG);  // ilova ham shu tilda ochilsin

  /* ---------------- savatcha ---------------- */
  let cart = store.get("cart", {});
  if (typeof cart !== "object" || !cart) cart = {};
  function clean() {  // sotuvdan olinganlarini olib tashlaymiz
    for (const id in cart) if (!P[id] || !P[id].stock || !(cart[id] > 0)) delete cart[id];
  }
  clean();
  const count = () => Object.values(cart).reduce((a, b) => a + b, 0);
  function save() { store.set("cart", cart); paint(); }
  function paint() {
    const n = count(), c = $("#cartCnt");
    if (c) { c.hidden = !n; if (c.textContent !== String(n)) { c.textContent = n; c.classList.remove("bump"); void c.offsetWidth; c.classList.add("bump"); } }
    $$("[data-add]").forEach(b => {
      const inCart = !!cart[b.dataset.add];
      b.classList.toggle("in", inCart);
      const s = b.querySelector("span"); if (s) s.textContent = inCart ? T.added : T.add;
    });
    renderDrawer();
  }
  function add(id, open) {
    if (!P[id] || !P[id].stock) return;
    if (!cart[id]) cart[id] = 1; else if (open) { /* «Hozir buyurtma» — miqdorni oshirmaymiz */ } else cart[id] = Math.min(99, cart[id] + 1);
    save();
    if (open) return checkout();
    toast("🛒 " + T.added);
  }
  function checkout() {
    clean(); store.set("cart", cart);
    location.href = "/app?go=cart&lang=" + LANG;
  }
  const svgCart = '<svg viewBox="0 0 24 24"><path d="M3 4h2l2.2 10.2a2 2 0 0 0 2 1.6h7.6a2 2 0 0 0 2-1.5L20.5 8H6.2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const sofa = '<div class="ph"><svg class="ph-art" viewBox="0 0 200 120"><g fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M38 58V44c0-8 6-14 14-14h96c8 0 14 6 14 14v14"/><path d="M30 60c-6 0-10 4-10 10v18h160V70c0-6-4-10-10-10s-10 4-10 10v6H50v-6c0-6-4-10-10-10Z"/></g></svg></div>';
  function renderDrawer() {
    const list = $("#cartList"), foot = $("#cartFoot");
    if (!list) return;
    const ids = Object.keys(cart);
    if (!ids.length) {
      list.innerHTML = `<div class="cart-empty">${svgCart}${esc(T.cart_empty)}</div>`;
      foot.innerHTML = ""; foot.hidden = true; return;
    }
    let total = 0;
    list.innerHTML = ids.map(id => {
      const p = P[id], q = cart[id]; total += p.price * q;
      return `<div class="ci"><a class="ci-img" href="${esc(p.url)}">${p.img ? `<img src="${esc(p.img)}" alt="">` : sofa}</a>
        <div><a href="${esc(p.url)}">${esc(p.name)}</a><div class="ci-p">${money(p.price)}</div>
          <div class="qty"><button data-q="-1" data-id="${id}" aria-label="−">−</button><span>${q}</span><button data-q="1" data-id="${id}" aria-label="+">+</button></div></div>
        <div><div class="ci-sum">${money(p.price * q)}</div><button class="ci-del" data-del="${id}">${esc(T.remove)}</button></div></div>`;
    }).join("");
    foot.hidden = false;
    foot.innerHTML = `<div class="tot"><span>${esc(T.total)}</span><b>${money(total)}</b></div>
      <p class="hint">${esc(T.checkout_hint)}</p><button class="btn" id="goCheckout">${esc(T.checkout)} →</button>`;
  }
  const drawer = $("#drawer"), shade = $("#shade");
  function openCart() {
    renderDrawer(); shade.hidden = false; drawer.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => { shade.classList.add("on"); drawer.classList.add("on"); });
    document.body.style.overflow = "hidden";
  }
  function closeCart() {
    shade.classList.remove("on"); drawer.classList.remove("on"); drawer.setAttribute("aria-hidden", "true");
    document.body.style.overflow = ""; setTimeout(() => { if (!drawer.classList.contains("on")) shade.hidden = true; }, 300);
  }
  $("#cartBtn").onclick = openCart;
  $("#drawerClose").onclick = closeCart;
  shade.onclick = closeCart;
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeCart(); });
  drawer.addEventListener("click", e => {
    const q = e.target.closest("[data-q]"), d = e.target.closest("[data-del]");
    if (q) { const id = q.dataset.id; cart[id] = (cart[id] || 0) + +q.dataset.q; if (cart[id] < 1) delete cart[id]; else cart[id] = Math.min(99, cart[id]); save(); }
    if (d) { delete cart[d.dataset.del]; save(); }
    if (e.target.closest("#goCheckout")) checkout();
  });
  document.addEventListener("click", e => {
    const a = e.target.closest("[data-add]"), b = e.target.closest("[data-buy]");
    if (a) { e.preventDefault(); if (cart[a.dataset.add]) openCart(); else add(a.dataset.add); }
    if (b) { e.preventDefault(); add(b.dataset.buy, true); }
  });
  window.addEventListener("storage", e => { if (e.key === "cart") { cart = store.get("cart", {}); clean(); paint(); } });

  let tt;
  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.classList.add("on");
    clearTimeout(tt); tt = setTimeout(() => t.classList.remove("on"), 1800);
  }

  /* ---------------- menyu ---------------- */
  const menu = $("#menu"), burger = $("#burger");
  burger.onclick = () => menu.classList.toggle("on");
  menu.addEventListener("click", e => { if (e.target.closest("a")) menu.classList.remove("on"); });
  const top = $("#top");
  const onScroll = () => top.classList.toggle("scrolled", scrollY > 8);
  addEventListener("scroll", onScroll, { passive: true }); onScroll();
  // til almashtirishda hozirgi bo'limda qolamiz
  $$(".langsw a").forEach(a => a.addEventListener("click", () => { store.set("lang", a.dataset.lang); a.href += location.hash; }));

  /* ---------------- katalog: filtr, qidiruv, saralash ---------------- */
  const grid = $("#grid");
  if (grid) {
    const cards = $$(".card", grid);
    let cat = "0", q = "";
    const chips = $("#chips");
    function apply() {
      let shown = 0;
      cards.forEach(c => {
        const ok = (cat === "0" || c.dataset.cat === cat) && (!q || c.dataset.name.includes(q));
        c.hidden = !ok; if (ok) shown++;
      });
      $("#nothing").hidden = shown > 0;
    }
    function pick(id) {
      cat = String(id);
      $$(".chip", chips).forEach(b => b.classList.toggle("on", b.dataset.cat === cat));
      apply();
    }
    chips && chips.addEventListener("click", e => { const b = e.target.closest("[data-cat]"); if (b) pick(b.dataset.cat); });
    $$("[data-pick]").forEach(b => b.addEventListener("click", () => {
      pick(b.dataset.pick); $("#katalog").scrollIntoView({ behavior: "smooth" });
    }));
    const qi = $("#q");
    qi && qi.addEventListener("input", () => { q = qi.value.trim().toLowerCase(); apply(); });
    const sort = $("#sort");
    if (sort) {
      sort.value = store.get("site_sort", "new");
      const doSort = () => {
        const k = sort.value; store.set("site_sort", k);
        const by = { new: c => -c.dataset.new, cheap: c => +c.dataset.price, exp: c => -c.dataset.price }[k] || (c => 0);
        cards.slice().sort((a, b) => by(a) - by(b)).forEach(c => grid.appendChild(c));
      };
      sort.onchange = doSort; doSort();
    }
    const want = new URLSearchParams(location.search).get("cat");
    if (want) pick(want);
  }

  /* ---------------- galereya ---------------- */
  const track = $("#gTrack");
  if (track) {
    const thumbs = $$(".thumb");
    const goTo = i => track.scrollTo({ left: track.clientWidth * i, behavior: "smooth" });
    thumbs.forEach(t => t.addEventListener("click", () => goTo(+t.dataset.go)));
    let raf;
    track.addEventListener("scroll", () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const i = Math.round(track.scrollLeft / track.clientWidth);
        thumbs.forEach(t => t.classList.toggle("on", +t.dataset.go === i));
        $$(".g-slide", track).forEach((s, k) => { if (k !== i) $$("video", s).forEach(v => v.pause()); });
      });
    }, { passive: true });
  }

  /* ---------------- paydo bo'lish animatsiyasi ---------------- */
  if ("IntersectionObserver" in window) {
    const els = $$(".sec-t, .cat, .card, .steps li, .faq details, .band-in, .feat");
    const io = new IntersectionObserver(es => es.forEach(en => { if (en.isIntersecting) { en.target.classList.add("seen"); io.unobserve(en.target); } }),
      { rootMargin: "0px 0px -6% 0px" });
    els.forEach((el, i) => {
      const r = el.getBoundingClientRect();
      if (r.top < innerHeight) return;  // ekranda turganlarini tegmaymiz
      el.classList.add("reveal"); el.style.transitionDelay = (i % 4) * 60 + "ms"; io.observe(el);
    });
  }

  /* ---------------- telefonga o'rnatish (PWA) ---------------- */
  if ("serviceWorker" in navigator) addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
  let deferred;
  const ib = $("#installBtn");
  addEventListener("beforeinstallprompt", e => { e.preventDefault(); deferred = e; if (ib) ib.hidden = false; });
  ib && ib.addEventListener("click", async () => { if (!deferred) return; deferred.prompt(); await deferred.userChoice.catch(() => {}); deferred = null; ib.hidden = true; });

  paint();
})();
