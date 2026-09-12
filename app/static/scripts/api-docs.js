"use strict";

async function loadApiDocumentation() {
  const status = document.getElementById("api-docs-status");
  try {
    if (typeof SwaggerUIBundle !== "function")
      throw new Error("The API viewer could not load. Refresh this page.");
    const response = await fetch("/openapi.json", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (response.redirected || response.status === 401 || response.status === 403) {
      throw new Error("Your session has expired. Sign in again, then reopen API Docs.");
    }
    if (!response.ok)
      throw new Error(
        "The OpenAPI definition could not load. Refresh this page or check the application service.",
      );
    const schema = await response.json();
    window.ui = SwaggerUIBundle({
      spec: schema,
      dom_id: "#swagger-ui",
      layout: "BaseLayout",
      deepLinking: true,
      showExtensions: true,
      showCommonExtensions: true,
      validatorUrl: null,
      presets: [SwaggerUIBundle.presets.apis],
      onComplete: () => {
        status.hidden = true;
      },
    });
  } catch (error) {
    status.textContent = error.message;
    status.setAttribute("role", "alert");
  }
}

loadApiDocumentation();
