(() => {
  const initialize = () => {
  const form = document.querySelector("#equipmentcomponent_form");
  if (!form) return;

  const equipment = form.querySelector("#id_equipment");
  const parent = form.querySelector("#id_parent");
  const endpoint = equipment?.dataset.optionsUrl;
  if (!equipment || !parent || !endpoint) return;
  let activeRequest;

  const resetParent = (label, disabled = true) => {
    parent.replaceChildren(new Option(label, ""));
    parent.disabled = disabled;
    parent.setAttribute("aria-busy", "false");
  };

  equipment.addEventListener("change", async () => {
    if (activeRequest) activeRequest.abort();
    if (!equipment.value) {
      resetParent("请先选择设备");
      return;
    }

    resetParent("正在加载…");
    parent.setAttribute("aria-busy", "true");
    activeRequest = new AbortController();
    const url = new URL(endpoint, window.location.origin);
    url.searchParams.set("equipment", equipment.value);
    if (parent.dataset.currentComponentId) {
      url.searchParams.set("exclude", parent.dataset.currentComponentId);
    }

    try {
      const response = await fetch(url, {
        headers: {"X-Requested-With": "XMLHttpRequest"},
        signal: activeRequest.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const options = [new Option("无上级部件（顶层部件）", "")];
      data.components.forEach((item) => options.push(new Option(item.label, item.value)));
      parent.replaceChildren(...options);
      parent.disabled = false;
      parent.setAttribute("aria-busy", "false");
    } catch (error) {
      if (error.name === "AbortError") return;
      resetParent("上级部件加载失败");
    }
  });

  parent.disabled = !equipment.value;
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, {once: true});
  } else {
    initialize();
  }
})();
