/* Supporting pages link to the same workflow represented by the workspace tabs. */
(() => {
  const main = document.querySelector("main");
  if (!main || document.querySelector(".workflow-navigation")) return;
  const navigation = document.createElement("section");
  navigation.className = "workflow-navigation";
  navigation.setAttribute("aria-label", "Quality workflow navigation");
  navigation.innerHTML = `<div class="stage-navigation-heading"><div><span class="stage-eyebrow">Your workspace</span><h2>Workflow outputs</h2></div><p>Review, refine and move to the next stage.</p></div>`;
  const links = document.createElement("nav");
  links.className = "stage-tabs";
  links.setAttribute("aria-label", "Quality workflow stages");
  window.workflowStages.forEach(({view, title, description}, index) => {
    const link = document.createElement("a");
    link.href = `/?view=${view}`;
    link.dataset.workflowStep = view;
    const number = document.createElement("span");
    number.className = "stage-number";
    number.setAttribute("aria-hidden", "true");
    number.textContent = String(index + 1).padStart(2, "0");
    const copy = document.createElement("span");
    copy.className = "stage-tab-copy";
    const label = document.createElement("strong");
    label.textContent = title;
    const hint = document.createElement("small");
    hint.textContent = description;
    copy.append(label, hint);
    link.append(number, copy);
    links.append(link);
  });
  navigation.append(links);
  const header = main.querySelector(".topbar");
  if (header) header.after(navigation);
  else main.prepend(navigation);
})();
