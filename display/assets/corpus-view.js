'use strict';

// Data injected inline by the HTML page (compact keys):
//   conceptInfo[key] = {l: lemma, s: synset_id, w: [wid, ...]}
//   synsetInfo[id]   = {d: definition, s: [synonym, ...], p: pos}
/* global conceptInfo, synsetInfo */

const story   = document.getElementById('story');
const tooltip = document.getElementById('tooltip');
const tooltipContent   = document.getElementById('tooltipContent');
const copyBtn          = document.getElementById('copyBtn');
const closeBtn         = document.getElementById('closeBtn');
const saveSettingsBtn  = document.getElementById('saveSettings');
const showWordIdToggle = document.getElementById('showWordIdToggle');
const showSynsToggle   = document.getElementById('showSynsToggle');

let pinnedElement = null;
let settings = { showWordId: false, showSyns: true };

// Penn Treebank POS → badge CSS class
function posBadgeClass(pos) {
  if (!pos) return 'pos-other';
  const p = pos.toLowerCase();
  if (p.startsWith('nn') || p === 'n') return 'pos-n';
  if (p.startsWith('vb') || p === 'v') return 'pos-v';
  if (p.startsWith('jj') || p === 'j' || p === 'a' || p === 's') return 'pos-j';
  if (p.startsWith('rb') || p === 'r') return 'pos-r';
  return 'pos-other';
}

// -------------------------------------------------------------------------
// Highlight helpers — word elements use <w> tag, attrs data-c/data-ns
// -------------------------------------------------------------------------

function highlightConcept(conceptId) {
  const info = conceptInfo[conceptId];
  const isMWE = info && info.w && info.w.length > 1;
  const cls   = isMWE ? 'mwe-highlight' : 'highlight';
  story.querySelectorAll(`[data-c~="${conceptId}"]`)
       .forEach(el => el.classList.add(cls));
}

function clearHighlights() {
  story.querySelectorAll('.highlight, .mwe-highlight')
       .forEach(el => el.classList.remove('highlight', 'mwe-highlight'));
}

// -------------------------------------------------------------------------
// Tooltip
// -------------------------------------------------------------------------

function buildTooltipHTML(element) {
  const wordId    = element.id;
  const pos       = element.dataset.p || '';
  const lemma     = element.dataset.l || element.textContent;
  const cidsAttr  = element.dataset.c || '';
  const badgeCls  = posBadgeClass(pos);

  let html = `<div class="mb-1">
    <span class="lemma">${escapeHTML(lemma)}</span>
    <span class="badge ${badgeCls} ms-1">${escapeHTML(pos)}</span>
    ${settings.showWordId
      ? `<span class="text-muted small ms-1">(${escapeHTML(wordId)})</span>`
      : ''}
  </div>`;

  if (cidsAttr) {
    cidsAttr.split(' ').forEach(cid => {
      const concept = conceptInfo[cid];
      if (!concept) return;
      const synInfo = synsetInfo[concept.s];

      html += `<div class="concept-block mt-1">`;
      if (concept.l && concept.l !== lemma) {
        html += `<div class="concept-lemma">${escapeHTML(concept.l)}</div>`;
      }
      if (synInfo) {
        if (synInfo.d) {
          html += `<div class="synset-def">${escapeHTML(synInfo.d)}</div>`;
        }
        if (settings.showSyns && synInfo.s && synInfo.s.length) {
          html += `<div class="synset-syns">≈ ${synInfo.s.map(escapeHTML).join(', ')}</div>`;
        }
        // Future: synInfo.trans for target-language translation
      }
      html += `</div>`;
    });
  }

  return html;
}

function showTooltip(element) {
  tooltipContent.innerHTML = buildTooltipHTML(element);
  tooltip.style.display = 'block';
  positionTooltip(element);
}

function hideTooltip() {
  tooltip.style.display = 'none';
}

function positionTooltip(element) {
  const rect = element.getBoundingClientRect();
  const left = Math.min(rect.left + window.scrollX,
                        window.innerWidth - tooltip.offsetWidth - 8);
  tooltip.style.left = Math.max(0, left) + 'px';
  tooltip.style.top  = (rect.bottom + window.scrollY + 6) + 'px';
}

// -------------------------------------------------------------------------
// Event handlers
// -------------------------------------------------------------------------

function handleMouseOver(event) {
  if (pinnedElement) return;
  const el   = event.currentTarget;
  const cids = el.dataset.c;
  if (cids) cids.split(' ').forEach(highlightConcept);
  showTooltip(el);
}

function handleMouseOut() {
  if (pinnedElement) return;
  clearHighlights();
  hideTooltip();
}

function handleMouseMove(event) {
  if (!pinnedElement && tooltip.style.display === 'block') {
    positionTooltip(event.currentTarget);
  }
}

function handleClick(event) {
  const el = event.currentTarget;
  if (pinnedElement === el) {
    closeTooltip();
  } else {
    if (pinnedElement) pinnedElement.classList.remove('pinned');
    clearHighlights();
    pinnedElement = el;
    pinnedElement.classList.add('pinned');
    const cids = el.dataset.c;
    if (cids) cids.split(' ').forEach(highlightConcept);
    showTooltip(el);
  }
}

function closeTooltip() {
  if (pinnedElement) {
    pinnedElement.classList.remove('pinned');
    pinnedElement = null;
  }
  clearHighlights();
  hideTooltip();
}

function copyTooltipContent() {
  navigator.clipboard.writeText(tooltipContent.innerText).then(() => {
    copyBtn.classList.replace('bi-clipboard', 'bi-check');
    setTimeout(() => copyBtn.classList.replace('bi-check', 'bi-clipboard'), 2000);
  });
}

function saveSettings() {
  settings.showWordId = showWordIdToggle.checked;
  settings.showSyns   = showSynsToggle.checked;
  if (pinnedElement) showTooltip(pinnedElement);
  bootstrap.Modal.getInstance(document.getElementById('settingsModal')).hide();
}

// -------------------------------------------------------------------------
// Utility
// -------------------------------------------------------------------------

function escapeHTML(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// -------------------------------------------------------------------------
// Init
// -------------------------------------------------------------------------

function init() {
  showWordIdToggle.checked = settings.showWordId;
  showSynsToggle.checked   = settings.showSyns;

  story.querySelectorAll('w').forEach(el => {
    el.addEventListener('mouseover',  handleMouseOver);
    el.addEventListener('mouseout',   handleMouseOut);
    el.addEventListener('mousemove',  handleMouseMove);
    el.addEventListener('click',      handleClick);
  });

  copyBtn.addEventListener('click',      copyTooltipContent);
  closeBtn.addEventListener('click',     closeTooltip);
  saveSettingsBtn.addEventListener('click', saveSettings);
}

init();
