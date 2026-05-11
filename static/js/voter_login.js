/* Voter Face Login page logic. */
(async function () {
  const vid     = document.getElementById("vid");
  const snap    = document.getElementById("snap");
  const btnScan = document.getElementById("btn-scan");
  const status  = document.getElementById("status");

  function show(kind, message) {
    status.hidden = false;
    status.className = "scan-status " + kind;
    status.textContent = message;
  }

  try {
    await Camera.start(vid);
  } catch (err) {
    show("fail", "Camera error: " + err.message);
    btnScan.disabled = true;
    return;
  }

  btnScan.addEventListener("click", async () => {
    btnScan.disabled = true;
    show("info", "Scanning your face…");

    const dataUrl = Camera.capture(vid, snap);

    try {
      const res = await fetch("/voter/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: dataUrl }),
      });
      const data = await res.json();

      if (data.status === "ok") {
        show("ok", data.message + " Redirecting to the booth…");
        Camera.stop(vid);
        setTimeout(() => (window.location.href = data.redirect), 900);
      } else if (data.status === "closed") {
        show("warn", data.message);
        btnScan.disabled = false;
      } else if (data.status === "already_voted") {
        show("warn", data.message);
        btnScan.disabled = false;
      } else if (data.status === "fail") {
        show("fail", data.message);
        btnScan.disabled = false;
      } else {
        show("fail", data.message || "Something went wrong.");
        btnScan.disabled = false;
      }
    } catch (err) {
      show("fail", "Network error: " + err.message);
      btnScan.disabled = false;
    }
  });

  window.addEventListener("beforeunload", () => Camera.stop(vid));
})();
