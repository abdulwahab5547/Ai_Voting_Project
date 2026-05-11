/* Admin → Enroll Face page logic. */
(async function () {
  const vid       = document.getElementById("vid");
  const snap      = document.getElementById("snap");
  const btn       = document.getElementById("btn-enroll");
  const status    = document.getElementById("status");
  const nameInput = document.getElementById("admin-name");

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
    show("info", "Enrolling…");

    const dataUrl = Camera.capture(vid, snap);
    try {
      const res = await fetch("/admin/face_enroll", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image: dataUrl,
          name: (nameInput.value || "Admin").trim(),
        }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        show("ok", data.message + " You can now start a voting session.");
      } else {
        show("fail", data.message || "Enrollment failed.");
        btn.disabled = false;
      }
    } catch (err) {
      show("fail", "Network error: " + err.message);
      btn.disabled = false;
    }
  });

  window.addEventListener("beforeunload", () => Camera.stop(vid));
})();
