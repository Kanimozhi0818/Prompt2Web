/**
 * SiteForge AI – Frontend Script
 * Handles: form validation, color picker sync,
 *          image upload rows (add/remove/preview),
 *          fetch to /upload then /generate, loading UX,
 *          navbar scroll effect, and error toast.
 */

/* ============================================================
   DOM REFERENCES
   ============================================================ */
const form          = document.getElementById('generate-form');
const submitBtn     = document.getElementById('submit-btn');
const btnText       = submitBtn.querySelector('.btn-text');
const btnLoader     = document.getElementById('btn-loader');
const overlay       = document.getElementById('loading-overlay');
const errorToast    = document.getElementById('error-toast');
const toastMsg      = document.getElementById('toast-message');
const toastClose    = document.getElementById('toast-close');
const navbar        = document.querySelector('.navbar');
const colorPicker   = document.getElementById('color_picker');
const colorText     = document.getElementById('color_theme');

/* ---- Loading step elements ---- */
const loadingSteps  = [
  document.getElementById('lstep1'),
  document.getElementById('lstep2'),
  document.getElementById('lstep3'),
  document.getElementById('lstep4'),
];

let stepIntervalId = null;

/* ============================================================
   NAVBAR – scroll shadow
   ============================================================ */
window.addEventListener('scroll', () => {
  navbar.classList.toggle('scrolled', window.scrollY > 30);
}, { passive: true });

/* ============================================================
   COLOR PICKER SYNC
   ============================================================ */
colorPicker.addEventListener('input', () => {
  colorText.value = colorPicker.value;
});

colorText.addEventListener('input', () => {
  const val = colorText.value.trim();
  // Basic hex validation
  if (/^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/.test(val)) {
    colorPicker.value = val;
  }
});

/* ============================================================
   FORM VALIDATION
   ============================================================ */
function validateForm() {
  let valid = true;

  const fields = [
    { id: 'website_name', errId: 'err-name', msg: 'Website name is required.' },
    { id: 'website_type', errId: 'err-type', msg: 'Business type is required.' },
    { id: 'description',  errId: 'err-desc', msg: 'Please add a brief description.' },
  ];

  fields.forEach(({ id, errId, msg }) => {
    const input = document.getElementById(id);
    const err   = document.getElementById(errId);

    if (!input.value.trim()) {
      input.classList.add('error-field');
      err.textContent = msg;
      valid = false;
    } else {
      input.classList.remove('error-field');
      err.textContent = '';
    }
  });

  return valid;
}

/* Live clear errors on focus */
['website_name','website_type','description'].forEach(id => {
  document.getElementById(id).addEventListener('focus', function () {
    this.classList.remove('error-field');
    const errId = { website_name:'err-name', website_type:'err-type', description:'err-desc' }[id];
    document.getElementById(errId).textContent = '';
  });
});

/* ============================================================
   LOADING STEPS ANIMATION
   ============================================================ */
function startLoadingSteps() {
  let current = 0;

  loadingSteps.forEach(s => s.className = 'lstep');
  loadingSteps[0].classList.add('active');

  stepIntervalId = setInterval(() => {
    loadingSteps[current].className = 'lstep done';
    loadingSteps[current].textContent = '✅ ' + loadingSteps[current].textContent.replace(/^.{2}/, '');
    current++;

    if (current < loadingSteps.length) {
      loadingSteps[current].classList.add('active');
    } else {
      clearInterval(stepIntervalId);
    }
  }, 3500);
}

function stopLoadingSteps() {
  clearInterval(stepIntervalId);
}

/* ============================================================
   SHOW / HIDE LOADING + BUTTON STATE
   ============================================================ */
function setLoading(active) {
  if (active) {
    btnText.hidden  = true;
    btnLoader.hidden = false;
    submitBtn.disabled = true;
    overlay.hidden  = false;
    document.body.style.overflow = 'hidden';
    startLoadingSteps();
  } else {
    btnText.hidden  = false;
    btnLoader.hidden = true;
    submitBtn.disabled = false;
    overlay.hidden  = true;
    document.body.style.overflow = '';
    stopLoadingSteps();
  }
}

/* ============================================================
   ERROR TOAST
   ============================================================ */
function showError(message) {
  toastMsg.textContent = message;
  errorToast.hidden = false;
  // Auto-hide after 7 s
  setTimeout(() => { errorToast.hidden = true; }, 7000);
}

toastClose.addEventListener('click', () => { errorToast.hidden = true; });

/* ============================================================
   IMAGE UPLOAD ROWS
   ============================================================ */
const imageRowsContainer = document.getElementById('image-rows-container');
const addImgBtn          = document.getElementById('add-img-btn');
const MAX_IMAGES         = 8;

const SECTION_OPTIONS = [
  { value: 'hero',     label: '🌄 Hero Background' },
  { value: 'about',    label: '🏢 About Section'   },
  { value: 'services', label: '⭐ Services Cards'   },
  { value: 'gallery',  label: '🖼 Gallery Grid'     },
  { value: 'contact',  label: '📩 Contact Banner'   },
];

function getRowCount() {
  return imageRowsContainer.querySelectorAll('.image-row').length;
}

function updateAddBtn() {
  addImgBtn.disabled = getRowCount() >= MAX_IMAGES;
}

function addImageRow() {
  if (getRowCount() >= MAX_IMAGES) return;

  const row = document.createElement('div');
  row.className = 'image-row';

  // Thumbnail
  const thumbWrap = document.createElement('div');
  thumbWrap.className = 'img-thumb-wrap';
  thumbWrap.innerHTML = '🖼';

  // File + label column
  const fileCol = document.createElement('div');
  fileCol.className = 'img-file-col';

  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = 'image/png,image/jpeg,image/gif,image/webp,image/svg+xml';
  fileInput.className = 'img-file-input';

  // Live thumbnail preview
  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      thumbWrap.innerHTML = '';
      const img = document.createElement('img');
      img.src = ev.target.result;
      img.alt = 'preview';
      thumbWrap.appendChild(img);
    };
    reader.readAsDataURL(file);
  });

  fileCol.appendChild(fileInput);

  // Section dropdown
  const select = document.createElement('select');
  select.className = 'img-section-select';
  SECTION_OPTIONS.forEach(({ value, label }) => {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = label;
    select.appendChild(opt);
  });

  // Remove button
  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.className = 'remove-img-btn';
  removeBtn.title = 'Remove image';
  removeBtn.innerHTML = '✕';
  removeBtn.addEventListener('click', () => {
    row.remove();
    updateAddBtn();
    if (getRowCount() === 0) {
      showEmptyHint();
    }
  });

  row.appendChild(thumbWrap);
  row.appendChild(fileCol);
  row.appendChild(select);
  row.appendChild(removeBtn);

  // Remove empty hint if present
  const hint = imageRowsContainer.querySelector('.img-upload-empty');
  if (hint) hint.remove();

  imageRowsContainer.appendChild(row);
  updateAddBtn();
}

function showEmptyHint() {
  if (!imageRowsContainer.querySelector('.img-upload-empty')) {
    const hint = document.createElement('p');
    hint.className = 'img-upload-empty';
    hint.textContent = 'No images added yet. Click "+ Add Image" above to get started.';
    imageRowsContainer.appendChild(hint);
  }
}

// Show initial hint
showEmptyHint();

/* Upload a single file to /upload, returns the server URL */
async function uploadSingleImage(file) {
  const fd = new FormData();
  fd.append('image', file);
  const res = await fetch('/upload', { method: 'POST', body: fd });
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || 'Upload failed');
  return data.url;
}

/* ============================================================
   FORM SUBMIT → UPLOAD IMAGES → GENERATE → REDIRECT
   ============================================================ */
form.addEventListener('submit', async (e) => {
  e.preventDefault();

  if (!validateForm()) return;

  setLoading(true);

  try {
    // ── 1. Upload all images that have a file selected ────────
    const rows = imageRowsContainer.querySelectorAll('.image-row');
    const images = [];

    for (const row of rows) {
      const fileInput = row.querySelector('.img-file-input');
      const select    = row.querySelector('.img-section-select');
      if (fileInput.files.length === 0) continue;

      const url = await uploadSingleImage(fileInput.files[0]);
      images.push({ url, section: select.value });
    }

    // ── 2. Build payload and generate website ─────────────────
    const payload = {
      website_name: document.getElementById('website_name').value.trim(),
      website_type: document.getElementById('website_type').value.trim(),
      description:  document.getElementById('description').value.trim(),
      color_theme:  document.getElementById('color_theme').value.trim() || '#2563eb',
      pages:        document.getElementById('pages').value.trim(),
      images,
    };

    const response = await fetch('/generate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });

    const data = await response.json();

    if (!response.ok || data.error) {
      throw new Error(data.error || `Server error (${response.status})`);
    }

    // Success → navigate to appropriate preview
    if (data.view_type === "fullscreen") {
      window.location.href = "/preview"; // The backend /preview route ALREADY handles the logic!
    } else {
      window.location.href = "/preview";
    }

  } catch (err) {
    setLoading(false);
    showError(err.message || 'Something went wrong. Please try again.');
  }
});
