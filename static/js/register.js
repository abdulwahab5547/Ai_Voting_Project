/* Admin → Register Voter page logic. */
(async function () {
  const vid       = document.getElementById("vid");
  const snap      = document.getElementById("snap");
  const preview   = document.getElementById("preview");
  const btnCap    = document.getElementById("btn-capture");
  const btnRetake = document.getElementById("btn-retake");
  const btnSave   = document.getElementById("btn-save");
  const imgInput  = document.getElementById("image-input");
  const hint      = document.getElementById("capture-hint");

  try {
    await Camera.start(vid);
  } catch (err) {
    hint.textContent = "Camera error: " + err.message;
    btnCap.disabled = true;
    return;
  }

  btnCap.addEventListener("click", () => {
    const dataUrl = Camera.capture(vid, snap);
    imgInput.value = dataUrl;
    preview.src = dataUrl;
    preview.hidden = false;
    vid.hidden = true;
    btnCap.hidden = true;
    btnRetake.hidden = false;
    btnSave.disabled = false;
    hint.textContent = "Looking good. Now click Save Voter.";
  });

  btnRetake.addEventListener("click", () => {
    imgInput.value = "";
    preview.hidden = true;
    vid.hidden = false;
    btnCap.hidden = false;
    btnRetake.hidden = true;
    btnSave.disabled = true;
    hint.textContent = "Capture a photo first.";
  });

  window.addEventListener("beforeunload", () => Camera.stop(vid));
})();
