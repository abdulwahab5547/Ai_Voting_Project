/**
 * Shared webcam helper.
 * Exposes window.Camera with:
 *   - start(videoEl)            — request camera + stream into <video>
 *   - capture(videoEl, canvasEl) — return a base64 PNG data URL
 *   - stop(videoEl)             — release the camera
 */
(function () {
  let activeStream = null;

  async function start(videoEl) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("Camera API not available. Use a modern browser on http://localhost.");
    }
    activeStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
      audio: false,
    });
    videoEl.srcObject = activeStream;
    await videoEl.play();
  }

  function capture(videoEl, canvasEl) {
    const w = videoEl.videoWidth || 640;
    const h = videoEl.videoHeight || 480;
    canvasEl.width = w;
    canvasEl.height = h;
    const ctx = canvasEl.getContext("2d");
    ctx.drawImage(videoEl, 0, 0, w, h);
    return canvasEl.toDataURL("image/png");
  }

  function stop(videoEl) {
    if (activeStream) {
      activeStream.getTracks().forEach((t) => t.stop());
      activeStream = null;
    }
    if (videoEl) videoEl.srcObject = null;
  }

  window.Camera = { start, capture, stop };
})();
