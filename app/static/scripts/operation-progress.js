/* Shared monotonic progress and accessible banner rendering. */
window.createOperationProgress = () => ({
  status: "Running",
  progress: 0,
  reset() { this.status = "Running"; this.progress = 0; },
  advance(value) { this.progress = Math.max(this.progress, value); },
  finish(status) { this.status = status; if (status === "Completed") this.progress = 100; },
  render(tray, percent, stages, title, indeterminate = false) {
    if (indeterminate && this.status !== "Completed") {
      const running = this.status === "Running";
      percent.textContent = running ? "Working" : this.status;
      percent.removeAttribute("aria-valuenow");
      percent.setAttribute("aria-valuetext", running ? "Running; completion percentage unavailable" : this.status);
      percent.title = title;
      tray.dataset.indeterminate = String(running);
      tray.dataset.status = this.status.toLowerCase();
      tray.style.setProperty("--review-progress", "0%");
      return;
    }
    tray.dataset.indeterminate = "false";
    percent.textContent = `${this.progress}%`;
    percent.setAttribute("aria-valuenow", String(this.progress));
    percent.setAttribute("aria-valuetext", `${this.status}: ${this.progress}% of ${stages} stages complete`);
    percent.title = title;
    tray.style.setProperty("--review-progress", `${this.progress}%`);
    tray.dataset.status = this.status.toLowerCase();
  },
});
