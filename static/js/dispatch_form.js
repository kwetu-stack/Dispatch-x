const stops = document.querySelector("#stops");
const addStop = document.querySelector("#add-stop");

function bindRemoveButtons() {
  document.querySelectorAll("[data-remove-stop]").forEach((button) => {
    button.onclick = () => {
      if (document.querySelectorAll(".stop-row").length > 1) {
        button.closest(".stop-row").remove();
      }
    };
  });
}

addStop?.addEventListener("click", () => {
  const row = document.createElement("div");
  row.className = "stop-row";
  row.innerHTML = `
    <input name="customer_name[]" required placeholder="Customer name">
    <input name="invoice_number[]" required placeholder="Invoice number">
    <input name="invoice_value[]" type="number" min="0" step="0.01" required placeholder="Invoice value">
    <button class="btn danger small" type="button" data-remove-stop>Remove</button>
  `;
  stops.appendChild(row);
  bindRemoveButtons();
});

bindRemoveButtons();
