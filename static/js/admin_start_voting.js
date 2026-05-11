/* Admin → Start Voting (face-gated) page logic. */
(async function () {
  const vid    = document.getElementById("vid");
  const snap   = document.getElementById("snap");
  const btn    = document.getElementById("btn-start");
  const status = document.getElementById("status");

  function show(kind, message) {
    status.hidden = false;
    status.className = "scan-status " + kind;
    status.textContent = message;
  }

  try {
    await Camera.start(vid);
  } catch (err) {
    show("fail", "Camera error: " + err.message);
    btn.disabled = true;
    return;
  }

  btn.addEventListener("click", async () => {
    btn.disabled = true;
    show("info", "Verifying admin face…");

    const dataUrl = Camera.capture(vid, snap);
    try {
      const res = await fetch("/admin/start_voting", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: dataUrl }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        show("ok", data.message);
        Camera.stop(vid);
        setTimeout(() => (window.location.href = data.redirect), 900);
      } else {
        show("fail", data.message || "Verification failed.");
        btn.disabled = false;
      }
    } catch (err) {
      show("fail", "Network error: " + err.message);
      btn.disabled = false;
    }
  });

  window.addEventListener("beforeunload", () => Camera.stop(vid));
})();
