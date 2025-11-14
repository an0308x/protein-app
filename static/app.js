let stage;
let mainComponent;
let mainRepresentation;

// in-memory annotations
let annotations = INITIAL_ANNOTATIONS || [];

// ----------------------
// NGL setup
// ----------------------
document.addEventListener("DOMContentLoaded", () => {
  stage = new NGL.Stage("viewport", { backgroundColor: "black" });

  window.addEventListener("resize", () => stage.handleResize());

  stage
    .loadFile(PDB_URL, { ext: "pdb" })
    .then((comp) => {
      mainComponent = comp;
      mainRepresentation = comp.addRepresentation("cartoon", {
        colorScheme: "chainname",
      });
      comp.autoView();
      applyAnnotationsTo3D();
    })
    .catch((err) => console.error(err));

  setupSequenceInteraction();
  renderAnnotationList();
  applyAnnotationsToSequence();

  const form = document.getElementById("annotation-form");
  form.addEventListener("submit", handleAnnotationSubmit);
});

// ----------------------
// Sequence interaction
// ----------------------
function setupSequenceInteraction() {
  const residues = document.querySelectorAll("#sequence-container .res");
  residues.forEach((span) => {
    span.addEventListener("click", () => {
      const idx = parseInt(span.dataset.index, 10);
      document.getElementById("start-index").value = idx;
      document.getElementById("end-index").value = idx;
      residues.forEach((s) => s.classList.remove("selected"));
      span.classList.add("selected");
    });
  });
}

// ----------------------
// Form submit
// ----------------------
async function handleAnnotationSubmit(e) {
  e.preventDefault();

  const startIndex = parseInt(
    document.getElementById("start-index").value,
    10
  );
  const endIndex = parseInt(
    document.getElementById("end-index").value,
    10
  );
  const label = document.getElementById("label").value.trim();
  const color = document.getElementById("color").value;

  if (
    Number.isNaN(startIndex) ||
    Number.isNaN(endIndex) ||
    startIndex < 0 ||
    endIndex < startIndex
  ) {
    alert("Invalid index range");
    return;
  }

  // save to backend
  const formData = new FormData();
  formData.append("start_index", String(startIndex));
  formData.append("end_index", String(endIndex));
  formData.append("label", label);
  formData.append("color", color);

  const resp = await fetch(`/p/${PROTEIN_SLUG}/annotations`, {
    method: "POST",
    body: formData,
  });

  if (!resp.ok) {
    const data = await resp.json();
    alert("Error: " + (data.detail || resp.statusText));
    return;
  }

  // locally track annotation
  annotations.push({
    start_index: startIndex,
    end_index: endIndex,
    label: label,
    color: color,
  });

  renderAnnotationList();
  applyAnnotationsToSequence();
  applyAnnotationsTo3D();
}

// ----------------------
// Sequence coloring
// ----------------------
function applyAnnotationsToSequence() {
  const residues = document.querySelectorAll("#sequence-container .res");
  residues.forEach((span) => {
    span.style.background = "";
    span.title = "";
  });

  annotations.forEach((ann) => {
    const { start_index, end_index, color, label } = ann;
    for (let i = start_index; i <= end_index; i++) {
      const span = document.querySelector(
        `#sequence-container .res[data-index="${i}"]`
      );
      if (!span) continue;
      span.style.background = color;
      span.title = label;
    }
  });
}

// ----------------------
// 3D coloring using NGL selection schemes
// We assume residue indices ~ sequence indices + 1
// ----------------------
function applyAnnotationsTo3D() {
  if (!mainRepresentation || !mainComponent) return;

  const schemeDef = annotations.map((ann) => {
    const startRes = ann.start_index + 1;
    const endRes = ann.end_index + 1;
    const sele = `${startRes}-${endRes}`; // all chains
    return [ann.color, sele];
  });

  // default color for remaining residues
  schemeDef.push(["#4b5563", "*"]);

  const schemeId = NGL.ColormakerRegistry.addSelectionScheme(
    schemeDef,
    "UserAnnotations"
  );
  mainRepresentation.setColor(schemeId);
  mainComponent.autoView();
}

// ----------------------
// Annotation list UI
// ----------------------
function renderAnnotationList() {
  const list = document.getElementById("annotation-list");
  list.innerHTML = "";

  if (!annotations.length) {
    const li = document.createElement("li");
    li.textContent = "No annotations yet.";
    list.appendChild(li);
    return;
  }

  annotations.forEach((ann) => {
    const li = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.style.display = "inline-block";
    swatch.style.width = "12px";
    swatch.style.height = "12px";
    swatch.style.borderRadius = "3px";
    swatch.style.marginRight = "6px";
    swatch.style.background = ann.color;

    li.appendChild(swatch);
    li.appendChild(
      document.createTextNode(
        `[${ann.start_index}-${ann.end_index}] ${ann.label}`
      )
    );
    list.appendChild(li);
  });
}

// ----------------------
// Copy share URL
// ----------------------
function copyShareUrl() {
  const input = document.getElementById("share-url-input");
  input.select();
  input.setSelectionRange(0, 99999);
  navigator.clipboard.writeText(input.value);
  alert("Copied share URL to clipboard");
}
