const gpsState = document.querySelector("#gps-state");
let lastSentAt = 0;

function postPosition(position) {
  localStorage.setItem(
    "dispatchX:lastPosition",
    JSON.stringify({
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      timestamp: Date.now(),
    })
  );

  const now = Date.now();
  if (now - lastSentAt < 20000) return;
  lastSentAt = now;

  fetch("/api/gps", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
    }),
  })
    .then((response) => {
      if (!response.ok) throw new Error("GPS save failed");
      if (gpsState) gpsState.textContent = "GPS active";
    })
    .catch(() => {
      if (gpsState) gpsState.textContent = "GPS save failed";
    });
}

if ("geolocation" in navigator) {
  navigator.geolocation.watchPosition(
    postPosition,
    (error) => {
      console.warn("Driver GPS tracking failed.", error.code, error.message);
      if (!gpsState) return;
      gpsState.textContent =
        error.code === error.PERMISSION_DENIED ? "GPS permission needed" : "GPS signal unavailable";
    },
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
  );
} else if (gpsState) {
  gpsState.textContent = "GPS unavailable on this device";
}
