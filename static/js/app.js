document.querySelectorAll("[data-nav-toggle]").forEach((element) => {
  element.addEventListener("click", () => document.body.classList.toggle("nav-open"));
});
