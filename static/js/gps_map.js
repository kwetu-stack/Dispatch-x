const mapNode = document.querySelector("#map");
const markers = JSON.parse(mapNode.dataset.markers || "[]");
const defaultCenter = [-1.286389, 36.817223];
const map = L.map("map").setView(defaultCenter, 12);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

if (markers.length) {
  const bounds = [];
  markers.forEach((item) => {
    const point = [item.lat, item.lng];
    bounds.push(point);
    L.marker(point)
      .addTo(map)
      .bindPopup(`<strong>${item.driver}</strong><br>${item.route}<br>Last update: ${item.last_update}`);
  });
  map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
} else {
  L.marker(defaultCenter).addTo(map).bindPopup("No active driver GPS yet.");
}
