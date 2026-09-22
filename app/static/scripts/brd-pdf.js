/* Self-contained PDF export for the editable proposed BRD. */
window.BrdPdf = (() => {
  const width = 1240;
  const height = 1754;
  const margin = 84;
  const lineHeight = 33;
  const maxLineWidth = width - margin * 2;

  function pagesFor(text) {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    const pages = [];
    let y = margin;
    const startPage = () => {
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, width, height);
      context.fillStyle = "#172433";
      context.font = "25px Arial, sans-serif";
      y = margin;
    };
    const finishPage = () => {
      const encoded = canvas.toDataURL("image/jpeg", 0.88).split(",")[1];
      const binary = atob(encoded);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
      pages.push(bytes);
    };
    const drawLine = (line) => {
      if (y + lineHeight > height - margin) {
        finishPage();
        startPage();
      }
      context.fillText(line, margin, y);
      y += lineHeight;
    };
    startPage();
    for (const raw of text.split(/\r?\n/)) {
      if (!raw.trim()) {
        drawLine("");
        continue;
      }
      let line = "";
      for (const word of raw.split(/(\s+)/)) {
        if (!word) continue;
        if (context.measureText(line + word).width <= maxLineWidth) {
          line += word;
          continue;
        }
        if (line.trim()) drawLine(line.trimEnd());
        line = word.trimStart();
        while (line && context.measureText(line).width > maxLineWidth) {
          let cut = 1;
          while (cut < line.length && context.measureText(line.slice(0, cut + 1)).width <= maxLineWidth) cut++;
          drawLine(line.slice(0, cut));
          line = line.slice(cut);
        }
      }
      if (line) drawLine(line.trimEnd());
    }
    finishPage();
    return pages;
  }

  function pdfFor(text) {
    const images = pagesFor(text);
    const encoder = new TextEncoder();
    const parts = [];
    const offsets = [0];
    let length = 0;
    const add = (value) => {
      const bytes = typeof value === "string" ? encoder.encode(value) : value;
      parts.push(bytes);
      length += bytes.length;
    };
    const object = (id, value) => {
      offsets[id] = length;
      add(`${id} 0 obj\n${value}\nendobj\n`);
    };
    add("%PDF-1.4\n");
    object(1, "<< /Type /Catalog /Pages 2 0 R >>");
    const kids = images.map((_, index) => `${3 + index * 3} 0 R`).join(" ");
    object(2, `<< /Type /Pages /Kids [${kids}] /Count ${images.length} >>`);
    images.forEach((image, index) => {
      const pageId = 3 + index * 3;
      const contentId = pageId + 1;
      const imageId = pageId + 2;
      object(pageId, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im${index} ${imageId} 0 R >> >> /Contents ${contentId} 0 R >>`);
      const content = `q\n595 0 0 842 0 0 cm\n/Im${index} Do\nQ\n`;
      object(contentId, `<< /Length ${encoder.encode(content).length} >>\nstream\n${content}endstream`);
      offsets[imageId] = length;
      add(`${imageId} 0 obj\n<< /Type /XObject /Subtype /Image /Width ${width} /Height ${height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${image.length} >>\nstream\n`);
      add(image);
      add("\nendstream\nendobj\n");
    });
    const startXref = length;
    add(`xref\n0 ${offsets.length}\n0000000000 65535 f \n`);
    for (let id = 1; id < offsets.length; id++) add(`${String(offsets[id]).padStart(10, "0")} 00000 n \n`);
    add(`trailer\n<< /Size ${offsets.length} /Root 1 0 R >>\nstartxref\n${startXref}\n%%EOF\n`);
    return new Blob(parts, { type: "application/pdf" });
  }

  function download(text, filename) {
    const url = URL.createObjectURL(pdfFor(text));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  return { download };
})();
