(() => {
  const initialize = () => {
    const form = document.querySelector("[data-work-order-form], #workorder_form");
    if (!form) return;

    const warehouse = form.querySelector("#id_warehouse");
    const equipment = form.querySelector("#id_equipment");
    const component = form.querySelector("#id_component");
    const assignee = form.querySelector("#id_assignee");
    const scheduleType = form.querySelector("#id_schedule_type");
    const endpoint = form.dataset.optionsUrl || warehouse?.dataset.optionsUrl;
    if (!warehouse || !equipment || !component || !assignee || !endpoint) return;
    let activeRequest;
    const labels = {
      selectWarehouse: warehouse.dataset.labelSelectWarehouse || "请先选择仓库",
      selectEquipment: warehouse.dataset.labelSelectEquipment || "请先选择设备",
      loading: warehouse.dataset.labelLoading || "正在加载…",
      chooseEquipment: warehouse.dataset.labelChooseEquipment || "请选择设备",
      noEquipment: warehouse.dataset.labelNoEquipment || "该仓库没有可用设备",
      unassigned: warehouse.dataset.labelUnassigned || "待认领（不指定负责人）",
      noAssignee: warehouse.dataset.labelNoAssignee || "该仓库没有可接单人员",
      wholeEquipment: warehouse.dataset.labelWholeEquipment || "整机（不选择部件）",
      noComponents: warehouse.dataset.labelNoComponents || "整机（没有已登记部件）",
      equipmentError: warehouse.dataset.labelEquipmentError || "设备加载失败",
      assigneeError: warehouse.dataset.labelAssigneeError || "负责人加载失败",
      componentError: warehouse.dataset.labelComponentError || "部件加载失败",
    };

    const resetSelect = (select, label, disabled = true) => {
      select.replaceChildren(new Option(label, ""));
      select.disabled = disabled;
      select.setAttribute("aria-busy", "false");
    };

    const populate = (select, items, emptyLabel, noItemsLabel, optional = false) => {
      const options = [new Option(items.length || optional ? emptyLabel : noItemsLabel, "")];
      items.forEach((item) => options.push(new Option(item.label, item.value)));
      select.replaceChildren(...options);
      select.disabled = !items.length && !optional;
      select.setAttribute("aria-busy", "false");
    };

    const loadOptions = async (params) => {
      if (activeRequest) activeRequest.abort();
      activeRequest = new AbortController();
      const url = new URL(endpoint, window.location.origin);
      Object.entries(params).forEach(([key, value]) => value && url.searchParams.set(key, value));
      const response = await fetch(url, {
        headers: {"X-Requested-With": "XMLHttpRequest"},
        signal: activeRequest.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    };

    warehouse.addEventListener("change", async () => {
      equipment.dataset.loadedForWarehouse = warehouse.value;
      resetSelect(component, labels.selectEquipment);
      if (!warehouse.value) {
        delete equipment.dataset.loadedForWarehouse;
        resetSelect(equipment, labels.selectWarehouse);
        resetSelect(assignee, labels.selectWarehouse);
        return;
      }

      resetSelect(equipment, labels.loading);
      resetSelect(assignee, labels.loading);
      equipment.setAttribute("aria-busy", "true");
      assignee.setAttribute("aria-busy", "true");
      try {
        const data = await loadOptions({warehouse: warehouse.value});
        populate(equipment, data.equipment, labels.chooseEquipment, labels.noEquipment);
        populate(assignee, data.assignees, labels.unassigned, labels.noAssignee, true);
      } catch (error) {
        if (error.name === "AbortError") return;
        delete equipment.dataset.loadedForWarehouse;
        resetSelect(equipment, labels.equipmentError);
        resetSelect(assignee, labels.assigneeError);
      }
    });

    equipment.addEventListener("change", async () => {
      if (!equipment.value) {
        resetSelect(component, labels.selectEquipment);
        return;
      }

      resetSelect(component, labels.loading);
      component.setAttribute("aria-busy", "true");
      try {
        const data = await loadOptions({warehouse: warehouse.value, equipment: equipment.value});
        populate(component, data.components, labels.wholeEquipment, labels.noComponents, true);
      } catch (error) {
        if (error.name === "AbortError") return;
        resetSelect(component, labels.componentError);
      }
    });

    const toggleRecurrence = () => {
      if (!scheduleType) return;
      const recurring = scheduleType.value === "RECURRING";
      ["recurrence_unit", "recurrence_interval", "recurrence_end_at", "recurrence_active"]
        .forEach((name) => {
          const field = form.querySelector(`#id_${name}`);
          if (!field) return;
          field.disabled = !recurring;
          const container = field.closest("[data-recurrence-field], .form-row");
          if (container) container.hidden = !recurring;
        });
    };

    if (scheduleType) scheduleType.addEventListener("change", toggleRecurrence);
    toggleRecurrence();
    equipment.disabled = !warehouse.value;
    assignee.disabled = !warehouse.value;
    component.disabled = !equipment.value;

    const restoreDependentOptions = () => {
      if (
        warehouse.value
        && equipment.dataset.loadedForWarehouse !== warehouse.value
        && equipment.options.length <= 1
      ) {
        warehouse.dispatchEvent(new Event("change"));
      }
    };
    restoreDependentOptions();
    window.addEventListener("pageshow", restoreDependentOptions);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, {once: true});
  } else {
    initialize();
  }
})();
