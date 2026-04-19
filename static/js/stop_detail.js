const deliveryForm = document.querySelector("#delivery-form");
const state = document.querySelector("#capture-state");
const latInput = document.querySelector("#proof-lat");
const lngInput = document.querySelector("#proof-lng");
const proofInput = document.querySelector("#proof-photo");
const takeProofButton = document.querySelector("#take-proof-button");
const cameraPanel = document.querySelector("#camera-panel");
const cameraVideo = document.querySelector("#proof-camera");
const proofCanvas = document.querySelector("#proof-canvas");
const captureProofButton = document.querySelector("#capture-proof-button");
const cancelCameraButton = document.querySelector("#cancel-camera-button");

const mobileDevice =
  window.matchMedia("(pointer: coarse)").matches &&
  /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);

let cameraStream = null;
let gpsPending = false;
let gpsCallbacks = [];

if (takeProofButton) {
  takeProofButton.textContent = mobileDevice ? "Take Proof & Deliver" : "Upload Proof Photo";
}

if (proofInput && mobileDevice) {
  proofInput.setAttribute("capture", "environment");
}

function runGpsCallbacks() {
  const callbacks = gpsCallbacks.splice(0);
  callbacks.forEach((callback) => callback?.());
}

function clearGpsCallbacks() {
  gpsCallbacks = [];
}

function readRecentStoredPosition() {
  try {
    const stored = JSON.parse(localStorage.getItem("dispatchX:lastPosition") || "null");
    if (!stored?.latitude || !stored?.longitude || !stored?.timestamp) return null;
    if (Date.now() - stored.timestamp > 5 * 60 * 1000) return null;
    return stored;
  } catch {
    return null;
  }
}

function setGpsCoordinates(latitude, longitude) {
  latInput.value = latitude;
  lngInput.value = longitude;
}

function requestGps(successCallback) {
  if (latInput.value && lngInput.value) {
    successCallback?.();
    return;
  }

  if (successCallback) gpsCallbacks.push(successCallback);
  if (gpsPending) return;

  if (!("geolocation" in navigator)) {
    state.textContent = "GPS is required but unavailable on this device.";
    alert("Location access required.");
    clearGpsCallbacks();
    return;
  }

  state.textContent = "Capturing location...";
  gpsPending = true;
  navigator.geolocation.getCurrentPosition(
    function (position) {
      gpsPending = false;
      setGpsCoordinates(position.coords.latitude, position.coords.longitude);
      localStorage.setItem(
        "dispatchX:lastPosition",
        JSON.stringify({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          timestamp: Date.now(),
        })
      );
      console.log("Delivery GPS captured.", position.coords.latitude, position.coords.longitude);
      state.textContent = "Location captured. Add proof photo to save delivery.";
      runGpsCallbacks();
    },
    function (error) {
      gpsPending = false;
      console.warn("Delivery GPS capture failed.", error.code, error.message);
      if (error.code === error.PERMISSION_DENIED) {
        clearGpsCallbacks();
        alert("Location access required.");
        state.textContent = "Location permission required to save delivery.";
        return;
      }
      const stored = readRecentStoredPosition();
      if (stored) {
        setGpsCoordinates(stored.latitude, stored.longitude);
        console.log("Delivery GPS used recent stored position.", stored.latitude, stored.longitude);
        state.textContent = "Location captured. Add proof photo to save delivery.";
        runGpsCallbacks();
        return;
      }
      clearGpsCallbacks();
      state.textContent = "Could not capture location. Move outside or try again.";
    },
    { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 }
  );
}

function stopCamera() {
  cameraStream?.getTracks().forEach((track) => track.stop());
  cameraStream = null;
  if (cameraVideo) cameraVideo.srcObject = null;
  cameraPanel?.classList.add("is-hidden");
}

async function startMobileCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    state.textContent = "Camera access is unavailable in this browser.";
    return;
  }

  try {
    state.textContent = "Opening camera...";
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });
    cameraVideo.srcObject = cameraStream;
    cameraPanel?.classList.remove("is-hidden");
    state.textContent = "Take the proof photo to complete delivery.";
  } catch {
    state.textContent = "Camera permission required to take proof photo.";
  }
}

function attachProofBlob(blob) {
  const file = new File([blob], `proof_${Date.now()}.jpg`, { type: "image/jpeg" });
  const files = new DataTransfer();
  files.items.add(file);
  proofInput.files = files.files;
}

function saveWhenReady() {
  if (!proofInput.files.length) return;
  requestGps(() => {
    state.textContent = "Saving delivery...";
    deliveryForm.requestSubmit();
  });
}

function startProofCapture() {
  if (mobileDevice) {
    startMobileCamera();
    return;
  }

  state.textContent = "Choose proof photo.";
  proofInput?.click();
}

takeProofButton?.addEventListener("click", () => {
  requestGps(startProofCapture);
});

proofInput?.addEventListener("change", () => {
  if (!proofInput.files.length) {
    state.textContent = "Proof photo is required before delivery can be saved.";
    return;
  }
  saveWhenReady();
});

captureProofButton?.addEventListener("click", () => {
  if (!cameraVideo.videoWidth || !cameraVideo.videoHeight) {
    state.textContent = "Camera is still starting. Try again.";
    return;
  }

  proofCanvas.width = cameraVideo.videoWidth;
  proofCanvas.height = cameraVideo.videoHeight;
  proofCanvas.getContext("2d").drawImage(cameraVideo, 0, 0);
  proofCanvas.toBlob(
    (blob) => {
      if (!blob) {
        state.textContent = "Could not capture proof photo. Try again.";
        return;
      }
      attachProofBlob(blob);
      stopCamera();
      state.textContent = "Photo captured. Saving delivery...";
      saveWhenReady();
    },
    "image/jpeg",
    0.9
  );
});

cancelCameraButton?.addEventListener("click", () => {
  stopCamera();
  state.textContent = "Proof photo is required before delivery can be saved.";
});

deliveryForm?.addEventListener("submit", (event) => {
  if (latInput.value && lngInput.value && proofInput.files.length) return;

  event.preventDefault();
  requestGps(() => {
    if (!proofInput.files.length) {
      state.textContent = mobileDevice
        ? "Take a proof photo before saving delivery."
        : "Upload a proof photo before saving delivery.";
      return;
    }

    state.textContent = "Saving delivery...";
    deliveryForm.requestSubmit();
  });
});
