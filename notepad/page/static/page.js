// The notepad page. Small and plain: forms work without this file; this makes them not reload.
(() => {
  const WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  async function post(url, body) {
    const opts = { method: "POST", headers: { "X-Requested-With": "fetch", "Accept": "application/json" } };
    if (body) opts.body = body;
    try {
      const r = await fetch(url, opts);
      const data = await r.json().catch(() => ({}));
      return { ok: r.ok && data.ok, status: r.status, data };
    } catch (e) {
      return { ok: false, status: 0, data: {} };
    }
  }

  function say(card, text, error) {
    const m = card.querySelector(":scope > .msg");
    m.textContent = text || "";
    m.classList.toggle("is-error", !!error);
  }

  function setBusy(card, busy) {
    card.querySelectorAll(".controls button, .controls input, .x").forEach((el) => {
      if (busy) { el.dataset.was = el.disabled ? "1" : ""; el.disabled = true; }
      else { el.disabled = el.dataset.was === "1"; }
    });
    card.setAttribute("aria-busy", busy ? "true" : "false");
  }

  function recount() {
    const counts = {
      needs: document.querySelectorAll("#needs-list > .card:not(.is-started)").length,
      working: document.querySelectorAll("#working .card").length,
      read: document.querySelectorAll("#read .card:not(.is-started)").length,
    };
    for (const [k, n] of Object.entries(counts)) {
      const el = document.querySelector(`[data-count="${k}"]`);
      if (el) el.textContent = n;
    }
    const open = counts.needs + counts.read;
    const word = open < WORDS.length ? WORDS[open] : String(open);
    document.getElementById("sentence").textContent =
      open === 0 ? "Nothing needs you." : `${word} ${open === 1 ? "thing needs" : "things need"} you.`;
    document.getElementById("needs-empty").hidden = !!document.querySelector("#needs-list > .card");
    for (const id of ["working", "read"]) {
      const s = document.getElementById(id);
      if (s && !s.querySelector(".card")) s.hidden = true;
    }
  }

  function leave(card) {
    if (reduced) { card.remove(); recount(); return; }
    card.style.maxHeight = card.offsetHeight + "px";
    requestAnimationFrame(() => {
      card.classList.add("is-leaving");
      card.style.maxHeight = "0px";
      card.style.marginBottom = "-12px";
    });
    setTimeout(() => { card.remove(); recount(); }, 460);
  }

  function started(card, thread) {
    const box = card.querySelector(".started");
    const link = box.querySelector("a");
    if (thread) link.href = thread; else link.hidden = true;
    box.hidden = false;
    card.classList.add("is-started");
    say(card, "");
    recount();
  }

  // one handler for every form on every card
  document.addEventListener("submit", async (ev) => {
    const form = ev.target;
    const card = form.closest(".card");
    if (!card) return;
    ev.preventDefault();
    if (card.getAttribute("aria-busy") === "true") return;
    const kind = form.dataset.kind;
    let body = null;
    if (form.classList.contains("tell")) {
      const text = form.querySelector("input").value.trim();
      if (!text) return;
      body = new FormData(form);
    }
    const btn = form.querySelector("button");
    const label = btn.innerHTML;
    setBusy(card, true);
    if (kind === "act" && btn.classList.contains("btn")) btn.textContent = "Starting";
    say(card, kind === "act" ? "Starting a session in Slack." : "");
    const r = await post(form.action, body);
    if (kind === "act" && btn.classList.contains("btn")) btn.innerHTML = label;
    if (r.ok) {
      if (kind === "act") started(card, r.data.thread);
      else leave(card);
      return;
    }
    if (r.data && r.data.busy) { say(card, "Already starting."); return; }  // the first tap will answer
    setBusy(card, false);
    const sendBtn = card.querySelector(".tell .send");
    if (sendBtn) sendBtn.disabled = !card.querySelector(".tell input").value.trim();
    say(card, (r.data && r.data.error) || (kind === "act" ? "Could not start this. Nothing was changed."
                                                          : "Could not save this. Nothing was changed."), true);
  });

  // the send arrow and the Add button show only when there is text
  document.addEventListener("input", (ev) => {
    const input = ev.target;
    const form = input.closest(".tell, .add");
    if (!form) return;
    form.querySelector("button").disabled = !input.value.trim();
  });

  // add box
  const add = document.getElementById("add");
  add.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const input = add.querySelector("input");
    const btn = add.querySelector("button");
    const msg = add.querySelector(".msg");
    if (!input.value.trim()) return;
    const data = new FormData(add);   // before disabling: disabled inputs are left out
    btn.disabled = true; input.disabled = true;
    const r = await post(add.action, data);
    input.disabled = false;
    if (r.ok) {
      input.value = "";
      msg.textContent = "Added to your notepad.";
      msg.classList.remove("is-error");
      const holder = document.createElement("div");
      holder.innerHTML = r.data.html.trim();
      const card = holder.firstElementChild;
      card.dataset.seen = "1";   // he wrote it; it has been seen
      document.getElementById("needs-list").prepend(card);
      recount();
      setTimeout(() => { if (msg.textContent === "Added to your notepad.") msg.textContent = ""; }, 3000);
    } else {
      btn.disabled = false;
      msg.textContent = (r.data && r.data.error) || "Could not add this. Nothing was changed.";
      msg.classList.add("is-error");
    }
  });

  // read cards open on tap
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest(".expand");
    if (!b) return;
    const card = b.closest(".card");
    card.classList.add("is-open");
    b.setAttribute("aria-expanded", "true");
    const first = card.querySelector(".controls button, .controls input");
    if (first) first.focus({ preventScroll: true });
  });

  // seen: half the card on screen for one second. It moves to Read on the next load, not now.
  if ("IntersectionObserver" in window) {
    const timers = new Map();
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        const card = e.target;
        if (e.isIntersecting && e.intersectionRatio >= 0.5) {
          if (!timers.has(card)) {
            timers.set(card, setTimeout(() => {
              io.unobserve(card);
              card.dataset.seen = "1";
              post(`/items/${card.dataset.id}/seen`);
            }, 1000));
          }
        } else if (timers.has(card)) {
          clearTimeout(timers.get(card));
          timers.delete(card);
        }
      }
    }, { threshold: [0, 0.5, 1] });
    document.querySelectorAll('.card--needs[data-seen="0"]').forEach((c) => io.observe(c));
  }
})();
