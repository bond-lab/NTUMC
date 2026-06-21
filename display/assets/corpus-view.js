'use strict';

// Data injected inline by the HTML page:
//   conceptInfo[key] = {l: lemma, s: synset_id, w: [wid, ...]}
//   docLang = language code of this document (e.g. "jpn")
//   dataPath = relative path to data/ directory (e.g. "../data")
/* global conceptInfo, docLang, dataPath */

var story   = document.getElementById('story');
var tooltip = document.getElementById('tooltip');
var tooltipContent   = document.getElementById('tooltipContent');
var copyBtn          = document.getElementById('copyBtn');
var closeBtn         = document.getElementById('closeBtn');
var saveSettingsBtn  = document.getElementById('saveSettings');
var showWordIdToggle = document.getElementById('showWordIdToggle');
var defLangSelect    = document.getElementById('defLangSelect');
var synLangSelect    = document.getElementById('synLangSelect');
var transLangSelect  = document.getElementById('transLangSelect');
var langStatus       = document.getElementById('langStatus');

var pinnedElement = null;
var activeTransPopover = null;

// Dynamic data (populated by fetches)
var synsetDefs = {};    // {synset_id: "definition"}
var synsetSyns = {};    // {synset_id: ["syn1", ...]}
var slinksData = null;  // full slinks.json object
var sentData   = {};    // {lang: {sid: "text"}}
var manifest   = null;  // manifest.json object
var neDefs     = {};    // named entity definitions

// Fetch cache to avoid re-downloading
var fetchCache = {};

var settings = {
  showWordId: false,
  defLang: 'eng',
  synLang: 'eng',
  transLang: ''
};

// -------------------------------------------------------------------------
// Data loading
// -------------------------------------------------------------------------

function fetchJSON(url) {
  if (fetchCache[url]) return fetchCache[url];
  fetchCache[url] = fetch(url).then(function(r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).catch(function() { return null; });
  return fetchCache[url];
}

function loadManifest() {
  return fetchJSON(dataPath + '/manifest.json').then(function(data) {
    if (!data) return;
    manifest = data;
    neDefs = data.ne_defs || {};
    populateDropdowns();
  });
}

function loadDefLang(lang) {
  if (!lang) { synsetDefs = {}; return Promise.resolve(); }
  return fetchJSON(dataPath + '/wn-defs-' + lang + '.json').then(function(data) {
    synsetDefs = data || {};
  });
}

function loadSynLang(lang) {
  if (!lang) { synsetSyns = {}; return Promise.resolve(); }
  return fetchJSON(dataPath + '/wn-syns-' + lang + '.json').then(function(data) {
    synsetSyns = data || {};
  });
}

function loadSlinks() {
  if (slinksData) return Promise.resolve();
  return fetchJSON(dataPath + '/slinks.json').then(function(data) {
    slinksData = data || {};
  });
}

function loadSentLang(lang) {
  if (!lang || sentData[lang]) return Promise.resolve();
  return fetchJSON(dataPath + '/sent-' + lang + '.json').then(function(data) {
    if (data) sentData[lang] = data;
  });
}

function loadTransLang(lang) {
  if (!lang) {
    document.body.classList.remove('show-trans');
    return Promise.resolve();
  }
  return loadSlinks().then(function() {
    return loadSentLang(lang);
  }).then(function() {
    document.body.classList.add('show-trans');
  });
}

function applyLanguageSettings() {
  var status = langStatus;
  if (status) status.textContent = 'Loading...';
  return Promise.all([
    loadDefLang(settings.defLang),
    loadSynLang(settings.synLang),
    loadTransLang(settings.transLang)
  ]).then(function() {
    if (status) status.textContent = '';
    if (pinnedElement) showTooltip(pinnedElement);
  });
}

// -------------------------------------------------------------------------
// Settings dropdowns
// -------------------------------------------------------------------------

function populateDropdowns() {
  if (!manifest) return;
  var names = manifest.lang_names || {};

  function fillSelect(select, langs, currentVal) {
    var none = select.querySelector('option[value=""]');
    select.innerHTML = '';
    if (none) select.appendChild(none);
    langs.forEach(function(lang) {
      var opt = document.createElement('option');
      opt.value = lang;
      opt.textContent = names[lang] || lang;
      select.appendChild(opt);
    });
    select.value = currentVal;
  }

  fillSelect(defLangSelect, manifest.defs || [], settings.defLang);
  fillSelect(synLangSelect, manifest.syns || [], settings.synLang);

  var transLangs = (manifest.trans && manifest.trans[docLang]) || [];
  fillSelect(transLangSelect, transLangs, settings.transLang);
}

function loadSettings() {
  try {
    var saved = localStorage.getItem('ntumc-display-settings');
    if (saved) {
      var parsed = JSON.parse(saved);
      if (parsed.showWordId !== undefined) settings.showWordId = parsed.showWordId;
      if (parsed.defLang !== undefined) settings.defLang = parsed.defLang;
      if (parsed.synLang !== undefined) settings.synLang = parsed.synLang;
      if (parsed.transLang !== undefined) settings.transLang = parsed.transLang;
    }
  } catch(e) { /* ignore */ }
}

function persistSettings() {
  try {
    localStorage.setItem('ntumc-display-settings', JSON.stringify(settings));
  } catch(e) { /* ignore */ }
}

// -------------------------------------------------------------------------
// POS badge
// -------------------------------------------------------------------------

function posBadgeClass(pos) {
  if (!pos) return 'pos-other';
  var p = pos.toLowerCase();
  if (p.startsWith('nn') || p === 'n') return 'pos-n';
  if (p.startsWith('vb') || p === 'v') return 'pos-v';
  if (p.startsWith('jj') || p === 'j' || p === 'a' || p === 's') return 'pos-j';
  if (p.startsWith('rb') || p === 'r') return 'pos-r';
  return 'pos-other';
}

// -------------------------------------------------------------------------
// Highlight helpers
// -------------------------------------------------------------------------

function highlightConcept(conceptId) {
  var info = conceptInfo[conceptId];
  var isMWE = info && info.w && info.w.length > 1;
  var cls   = isMWE ? 'mwe-highlight' : 'highlight';
  story.querySelectorAll('[data-c~="' + conceptId + '"]')
       .forEach(function(el) { el.classList.add(cls); });
}

function clearHighlights() {
  story.querySelectorAll('.highlight, .mwe-highlight')
       .forEach(function(el) { el.classList.remove('highlight', 'mwe-highlight'); });
}

// -------------------------------------------------------------------------
// Tooltip
// -------------------------------------------------------------------------

function buildTooltipHTML(element) {
  var wordId    = element.id;
  var pos       = element.dataset.p || '';
  var lemma     = element.dataset.l || element.textContent;
  var cidsAttr  = element.dataset.c || '';
  var badgeCls  = posBadgeClass(pos);

  var html = '<div class="mb-1">'
    + '<span class="lemma">' + escapeHTML(lemma) + '</span>'
    + '<span class="badge ' + badgeCls + ' ms-1">' + escapeHTML(pos) + '</span>'
    + (settings.showWordId
       ? '<span class="text-muted small ms-1">(' + escapeHTML(wordId) + ')</span>'
       : '')
    + '</div>';

  if (cidsAttr) {
    cidsAttr.split(' ').forEach(function(cid) {
      var concept = conceptInfo[cid];
      if (!concept) return;
      var tag = concept.s;

      html += '<div class="concept-block mt-1">';
      if (concept.l && concept.l !== lemma) {
        html += '<div class="concept-lemma">' + escapeHTML(concept.l) + '</div>';
      }

      // Named entity or synset
      if (neDefs[tag]) {
        html += '<div class="synset-def">' + escapeHTML(neDefs[tag]) + '</div>';
      } else {
        var def = synsetDefs[tag];
        if (def) {
          html += '<div class="synset-def">' + escapeHTML(def) + '</div>';
        }
        var syns = synsetSyns[tag];
        if (syns && syns.length) {
          html += '<div class="synset-syns">≈ ' + syns.map(escapeHTML).join(', ') + '</div>';
        }
      }
      html += '</div>';
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
  var rect = element.getBoundingClientRect();
  var left = Math.min(rect.left + window.scrollX,
                      window.innerWidth - tooltip.offsetWidth - 8);
  tooltip.style.left = Math.max(0, left) + 'px';
  tooltip.style.top  = (rect.bottom + window.scrollY + 6) + 'px';
}

// -------------------------------------------------------------------------
// Event handlers
// -------------------------------------------------------------------------

function handleMouseOver(event) {
  if (pinnedElement) return;
  var el   = event.currentTarget;
  var cids = el.dataset.c;
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
  var el = event.currentTarget;
  if (pinnedElement === el) {
    closeTooltip();
  } else {
    if (pinnedElement) pinnedElement.classList.remove('pinned');
    clearHighlights();
    pinnedElement = el;
    pinnedElement.classList.add('pinned');
    var cids = el.dataset.c;
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
  navigator.clipboard.writeText(tooltipContent.innerText).then(function() {
    copyBtn.classList.replace('bi-clipboard', 'bi-check');
    setTimeout(function() { copyBtn.classList.replace('bi-check', 'bi-clipboard'); }, 2000);
  });
}

function saveSettings() {
  settings.showWordId = showWordIdToggle.checked;
  settings.defLang  = defLangSelect.value;
  settings.synLang  = synLangSelect.value;
  settings.transLang = transLangSelect.value;
  persistSettings();
  applyLanguageSettings();
  bootstrap.Modal.getInstance(document.getElementById('settingsModal')).hide();
}

// -------------------------------------------------------------------------
// Translation popover
// -------------------------------------------------------------------------

function closeTransPopover() {
  if (activeTransPopover) {
    activeTransPopover.remove();
    activeTransPopover = null;
  }
}

function getTranslation(sid) {
  var tl = settings.transLang;
  if (!tl || !slinksData) return null;
  var langLinks = slinksData[docLang];
  if (!langLinks) return null;
  var pairLinks = langLinks[tl];
  if (!pairLinks) return null;
  var tgtSids = pairLinks[String(sid)];
  if (!tgtSids || !sentData[tl]) return null;
  var texts = [];
  tgtSids.forEach(function(tsid) {
    var t = sentData[tl][String(tsid)];
    if (t) texts.push(t);
  });
  return texts.length ? texts.join(' / ') : null;
}

function showTransPopover(icon) {
  closeTransPopover();
  var sid = icon.dataset.sid;
  var text = getTranslation(sid);
  if (!text) return;

  var pop = document.createElement('div');
  pop.className = 'trans-popover';
  pop.innerHTML = '<i class="bi bi-x-lg trans-close"></i>'
    + '<span class="trans-text">' + escapeHTML(text) + '</span>';
  document.body.appendChild(pop);
  pop.querySelector('.trans-close').addEventListener('click', closeTransPopover);

  var rect = icon.getBoundingClientRect();
  var left = Math.min(rect.left + window.scrollX,
                      window.innerWidth - pop.offsetWidth - 8);
  pop.style.left = Math.max(0, left) + 'px';
  pop.style.top  = (rect.bottom + window.scrollY + 4) + 'px';
  activeTransPopover = pop;
  activeTransPopover._sid = sid;
}

function handleTransClick(event) {
  event.stopPropagation();
  var icon = event.currentTarget;
  if (activeTransPopover && activeTransPopover._sid === icon.dataset.sid) {
    closeTransPopover();
  } else {
    showTransPopover(icon);
  }
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
  loadSettings();
  showWordIdToggle.checked = settings.showWordId;

  story.querySelectorAll('w').forEach(function(el) {
    el.addEventListener('mouseover',  handleMouseOver);
    el.addEventListener('mouseout',   handleMouseOut);
    el.addEventListener('mousemove',  handleMouseMove);
    el.addEventListener('click',      handleClick);
  });

  story.querySelectorAll('.trans-icon').forEach(function(el) {
    el.addEventListener('click', handleTransClick);
  });

  document.addEventListener('click', function(e) {
    if (activeTransPopover && !activeTransPopover.contains(e.target)
        && !e.target.classList.contains('trans-icon')) {
      closeTransPopover();
    }
  });

  copyBtn.addEventListener('click',      copyTooltipContent);
  closeBtn.addEventListener('click',     closeTooltip);
  saveSettingsBtn.addEventListener('click', saveSettings);

  // Load manifest, then apply saved language settings
  loadManifest().then(function() {
    return applyLanguageSettings();
  });
}

init();
