(() => {
  const initialize = () => {
    const builder = document.querySelector("[data-task-formset]");
    if (!builder) return;

    const list = builder.querySelector("[data-task-form-list]");
    const template = builder.querySelector("[data-task-empty-form]");
    const totalForms = builder.querySelector("[name$='-TOTAL_FORMS']");
    const addButton = builder.querySelector("[data-add-task]");
    if (!list || !template || !totalForms || !addButton) return;

    const updateNumbers = () => {
      let visibleIndex = 1;
      list.querySelectorAll("[data-task-form]").forEach((row) => {
        if (row.hidden) return;
        const number = row.querySelector("[data-task-number]");
        if (number) number.textContent = String(visibleIndex).padStart(2, "0");
        visibleIndex += 1;
      });
    };

    const bindRemove = (row) => {
      row.querySelector("[data-remove-task]")?.addEventListener("click", () => {
        const deleteInput = row.querySelector("input[name$='-DELETE']");
        if (deleteInput) deleteInput.checked = true;
        row.hidden = true;
        row.querySelectorAll("input:not([name$='-DELETE']), textarea").forEach((field) => {
          field.disabled = true;
        });
        updateNumbers();
      });
    };

    list.querySelectorAll("[data-task-form]").forEach(bindRemove);
    addButton.addEventListener("click", () => {
      const index = Number(totalForms.value);
      const fragment = template.content.cloneNode(true);
      fragment.querySelectorAll("[name], [id], label[for]").forEach((element) => {
        if (element.name) element.name = element.name.replaceAll("__prefix__", index);
        if (element.id) element.id = element.id.replaceAll("__prefix__", index);
        if (element.htmlFor) element.htmlFor = element.htmlFor.replaceAll("__prefix__", index);
      });
      const row = fragment.querySelector("[data-task-form]");
      if (!row) return;
      list.appendChild(fragment);
      totalForms.value = index + 1;
      bindRemove(row);
      updateNumbers();
      row.querySelector("input[type='text']")?.focus();
    });
    updateNumbers();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, {once: true});
  } else {
    initialize();
  }
})();
