// Show Miles only for mileage claims and Amount for everything else.
// The server checks the same rule; this only keeps the form honest.
document.addEventListener("DOMContentLoaded", function () {
  var category = document.getElementById("category");
  var amountField = document.getElementById("amount-field");
  var milesField = document.getElementById("miles-field");
  if (!category || !amountField || !milesField) {
    return;
  }
  function sync() {
    var mileage = category.value === "mileage";
    milesField.hidden = !mileage;
    milesField.querySelector("input").disabled = !mileage;
    amountField.hidden = mileage;
    amountField.querySelector("input").disabled = mileage;
  }
  category.addEventListener("change", sync);
  sync();
});
