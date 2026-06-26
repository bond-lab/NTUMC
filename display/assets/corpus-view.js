'use strict';

// Data injected inline by the HTML page:
//   conceptInfo[key] = {l: lemma, s: synset_id, w: [wid, ...]}
//   docLang = language code of this document (e.g. "jpn")
//   docGenre = genre string (e.g. "stories")
//   dataPath = relative path to data/ directory (e.g. "../data")
/* global conceptInfo, docLang, docGenre, dataPath, docStats */

// =========================================================================
// DOM references
// =========================================================================

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
var synsetDefs = {};
var synsetSyns = {};
var slinksData = null;
var sentData   = {};
var manifest   = null;
var neDefs     = {};

var fetchCache = {};

var settings = {
  showWordId: false,
  defLang: 'eng',
  synLang: 'eng',
  transLang: '',
  showSentNums: false,
  showInlineTrans: false,
  showSentiment: false
};

// Feature state
var sentNumsCreated = false;
var searchMatches = [];
var searchIndex = -1;

// =========================================================================
// Data loading
// =========================================================================

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
  if (status) status.textContent = 'Loading…';
  return Promise.all([
    loadDefLang(settings.defLang),
    loadSynLang(settings.synLang),
    loadTransLang(settings.transLang)
  ]).then(function() {
    if (status) status.textContent = '';
    if (pinnedElement) showTooltip(pinnedElement);
    updateInlineTranslations();
  });
}

// =========================================================================
// Settings
// =========================================================================

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
      if (parsed.showSentNums !== undefined) settings.showSentNums = parsed.showSentNums;
      if (parsed.showInlineTrans !== undefined) settings.showInlineTrans = parsed.showInlineTrans;
    }
  } catch(e) { /* ignore */ }
}

function persistSettings() {
  try {
    localStorage.setItem('ntumc-display-settings', JSON.stringify(settings));
  } catch(e) { /* ignore */ }
}

// =========================================================================
// POS badge
// =========================================================================

function posBadgeClass(pos) {
  if (!pos) return 'pos-other';
  var p = pos.toLowerCase();
  if (p.startsWith('nn') || p === 'n') return 'pos-n';
  if (p.startsWith('vb') || p === 'v') return 'pos-v';
  if (p.startsWith('jj') || p === 'j' || p === 'a' || p === 's') return 'pos-j';
  if (p.startsWith('rb') || p === 'r') return 'pos-r';
  return 'pos-other';
}

// =========================================================================
// Highlight helpers
// =========================================================================

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

// =========================================================================
// Tooltip
// =========================================================================

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
        if (settings.showWordId && tag) {
          html += '<span class="synset-id">' + escapeHTML(tag) + '</span>';
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

// =========================================================================
// Core event handlers
// =========================================================================

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

  // Sync inline translations button state
  var itBtn = document.getElementById('toggleInlineTrans');
  if (itBtn && settings.showInlineTrans) {
    itBtn.classList.toggle('active', !!settings.transLang);
  }

  bootstrap.Modal.getInstance(document.getElementById('settingsModal')).hide();
}

// =========================================================================
// Translation popover
// =========================================================================

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

// =========================================================================
// UI injection — adds toolbar, progress bar to existing pages
// =========================================================================

function injectUI() {
  // Reading progress bar
  if (!document.getElementById('readingProgress')) {
    var pb = document.createElement('div');
    pb.id = 'readingProgress';
    document.body.insertBefore(pb, document.body.firstChild);
  }

  // Toolbar — inject before the story card
  var storyCard = story ? story.closest('.card') : null;
  if (storyCard && !document.getElementById('corpusToolbar')) {
    var toolbar = document.createElement('div');
    toolbar.id = 'corpusToolbar';
    toolbar.className = 'corpus-toolbar';
    toolbar.innerHTML =
      '<div class="toolbar-group">' +
        '<div class="toolbar-search">' +
          '<i class="bi bi-search"></i>' +
          '<input type="text" id="searchInput" placeholder="Search text…" aria-label="Search">' +
          '<span id="searchCount" class="search-count"></span>' +
        '</div>' +
      '</div>' +
      '<div class="toolbar-group">' +
        '<button id="toggleSentNums" class="toolbar-btn" title="Sentence numbers">' +
          '<i class="bi bi-hash"></i>' +
        '</button>' +
        '<button id="toggleInlineTrans" class="toolbar-btn" title="Inline translations">' +
          '<i class="bi bi-translate"></i>' +
        '</button>' +
        '<button id="toggleSentiment" class="toolbar-btn" title="Show sentiment">' +
          '<i class="bi bi-heart"></i>' +
        '</button>' +
        '<button id="tocToggle" class="toolbar-btn" title="Table of contents">' +
          '<i class="bi bi-list-nested"></i>' +
        '</button>' +
        '<button id="toggleStats" class="toolbar-btn" title="Annotation statistics">' +
          '<i class="bi bi-bar-chart-line"></i>' +
        '</button>' +
        '<button id="downloadTsv" class="toolbar-btn" title="Download annotations (TSV)">' +
          '<i class="bi bi-filetype-csv"></i>' +
        '</button>' +
        '<button id="downloadJson" class="toolbar-btn" title="Download annotations (JSON)">' +
          '<i class="bi bi-filetype-json"></i>' +
        '</button>' +
        '<button class="toolbar-btn" title="Settings"' +
          ' data-bs-toggle="modal" data-bs-target="#settingsModal">' +
          '<i class="bi bi-gear"></i>' +
        '</button>' +
      '</div>';
    storyCard.parentNode.insertBefore(toolbar, storyCard);

    // Hide original standalone settings icon
    var origIcon = document.getElementById('settingsIcon');
    if (origIcon) origIcon.style.display = 'none';
  }
}

// =========================================================================
// Reading progress
// =========================================================================

function updateReadingProgress() {
  var bar = document.getElementById('readingProgress');
  if (!bar) return;
  var scrolled = window.scrollY;
  var height = document.documentElement.scrollHeight - window.innerHeight;
  bar.style.width = (height > 0 ? (scrolled / height * 100) : 0) + '%';
}

// =========================================================================
// Search
// =========================================================================

function performSearch(query) {
  clearSearch();
  if (!query || query.length < 1) return;

  var q = query.toLowerCase();
  var words = story.querySelectorAll('w');

  words.forEach(function(el) {
    var text = el.textContent.toLowerCase();
    var lemma = (el.dataset.l || '').toLowerCase();
    if (text.indexOf(q) !== -1 || lemma.indexOf(q) !== -1) {
      el.classList.add('search-match');
      searchMatches.push(el);
    }
  });

  var countEl = document.getElementById('searchCount');
  if (countEl) {
    countEl.textContent = searchMatches.length > 0
      ? searchMatches.length + ' found'
      : (query ? 'no matches' : '');
  }

  if (searchMatches.length > 0) {
    searchIndex = 0;
    scrollToSearchMatch(0);
  }
}

function clearSearch() {
  searchMatches.forEach(function(el) {
    el.classList.remove('search-match', 'search-current');
  });
  searchMatches = [];
  searchIndex = -1;
  var countEl = document.getElementById('searchCount');
  if (countEl) countEl.textContent = '';
}

function scrollToSearchMatch(idx) {
  if (idx < 0 || idx >= searchMatches.length) return;
  searchMatches.forEach(function(el) { el.classList.remove('search-current'); });
  searchMatches[idx].classList.add('search-current');
  searchMatches[idx].scrollIntoView({ behavior: 'smooth', block: 'center' });
  searchIndex = idx;
  var countEl = document.getElementById('searchCount');
  if (countEl) countEl.textContent = (idx + 1) + '/' + searchMatches.length;
}

function nextSearchMatch() {
  if (searchMatches.length === 0) return;
  scrollToSearchMatch((searchIndex + 1) % searchMatches.length);
}

function prevSearchMatch() {
  if (searchMatches.length === 0) return;
  scrollToSearchMatch((searchIndex - 1 + searchMatches.length) % searchMatches.length);
}

// =========================================================================
// Sentence numbers
// =========================================================================

function createSentenceNumbers() {
  if (sentNumsCreated) return;
  story.querySelectorAll('.sent').forEach(function(el) {
    var sid = el.id.replace('s', '');
    var num = document.createElement('span');
    num.className = 'sent-num';
    num.textContent = sid;
    el.insertBefore(num, el.firstChild);
  });
  sentNumsCreated = true;
}

function toggleSentenceNumbers() {
  settings.showSentNums = !settings.showSentNums;
  document.body.classList.toggle('show-sent-nums', settings.showSentNums);
  var btn = document.getElementById('toggleSentNums');
  if (btn) btn.classList.toggle('active', settings.showSentNums);
  if (settings.showSentNums) createSentenceNumbers();
  persistSettings();
}

// =========================================================================
// Inline translations
// =========================================================================

function toggleInlineTranslations() {
  settings.showInlineTrans = !settings.showInlineTrans;
  var btn = document.getElementById('toggleInlineTrans');
  if (btn) btn.classList.toggle('active', settings.showInlineTrans);

  if (settings.showInlineTrans && settings.transLang) {
    loadTransLang(settings.transLang).then(updateInlineTranslations);
  } else {
    updateInlineTranslations();
  }
  persistSettings();
}

function updateInlineTranslations() {
  story.querySelectorAll('.inline-trans').forEach(function(el) { el.remove(); });

  var lang = settings.transLang;
  if (!settings.showInlineTrans || !lang || !slinksData || !sentData[lang]) return;

  story.querySelectorAll('.sent').forEach(function(sentEl) {
    var sid = sentEl.id.replace('s', '');
    var text = getTranslation(sid);
    if (!text) return;
    var block = document.createElement('div');
    block.className = 'inline-trans';
    block.textContent = text;
    // Insert after the sentence element
    var next = sentEl.nextSibling;
    sentEl.parentNode.insertBefore(block, next);
  });
}

// =========================================================================
// Sentiment underlines
// =========================================================================

function sentimentColor(score) {
  var t = Math.min(Math.abs(score) / 100, 1);
  if (score >= 0) {
    return 'hsl(142,' + Math.round(50 + t * 30) + '%,' + Math.round(58 - t * 23) + '%)';
  }
  return 'hsl(0,' + Math.round(55 + t * 29) + '%,' + Math.round(58 - t * 13) + '%)';
}

function applySentimentUnderlines() {
  story.querySelectorAll('w').forEach(function(w) {
    var cids = (w.dataset.c || '').split(' ').filter(Boolean);
    var scores = cids.map(function(cid) {
      var c = conceptInfo[cid];
      return (c && c.v !== undefined) ? c.v : null;
    }).filter(function(s) { return s !== null; });
    if (!scores.length) return;
    var avg = scores.reduce(function(a, b) { return a + b; }, 0) / scores.length;
    if (avg === 0) return;
    w.style.textDecoration = 'underline 2px';
    w.style.textDecorationColor = sentimentColor(avg);
  });
}

function clearSentimentUnderlines() {
  if (!story) return;
  story.querySelectorAll('w').forEach(function(w) {
    w.style.textDecoration = '';
    w.style.textDecorationColor = '';
  });
}

function toggleSentiment() {
  settings.showSentiment = !settings.showSentiment;
  var btn = document.getElementById('toggleSentiment');
  if (btn) btn.classList.toggle('active', settings.showSentiment);
  if (settings.showSentiment) {
    applySentimentUnderlines();
  } else {
    clearSentimentUnderlines();
  }
  persistSettings();
}

// =========================================================================
// Table of contents
// =========================================================================

function buildTOC() {
  if (!story) return false;
  var headings = story.querySelectorAll('h1, h2, h3, h4, h5, h6');
  if (headings.length < 3) return false;

  var panel = document.createElement('div');
  panel.id = 'tocPanel';
  panel.className = 'toc-panel';
  panel.innerHTML = '<h6>Contents</h6><ul id="tocList"></ul>';
  document.body.appendChild(panel);

  var list = panel.querySelector('#tocList');
  headings.forEach(function(h, i) {
    if (!h.id) h.id = 'toc-h-' + i;
    var level = parseInt(h.tagName.charAt(1));
    var li = document.createElement('li');
    var a = document.createElement('a');
    a.href = '#' + h.id;
    a.textContent = h.textContent.trim();
    a.className = 'toc-h' + level;
    a.addEventListener('click', function(e) {
      e.preventDefault();
      h.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    li.appendChild(a);
    list.appendChild(li);
  });
  return true;
}

function toggleTOC() {
  var panel = document.getElementById('tocPanel');
  if (!panel) return;
  panel.classList.toggle('visible');
  var btn = document.getElementById('tocToggle');
  if (btn) btn.classList.toggle('active', panel.classList.contains('visible'));
}

// =========================================================================
// Download TSV / JSON
// =========================================================================

function downloadAnnotationsJSON() {
  var docName = location.pathname.split('/').pop().replace(/-view\.html$/, '');
  var genre = (typeof docGenre !== 'undefined') ? docGenre : 'other';
  var url = dataPath + '/docs/' + docLang + '-' + genre + '-' + docName + '.jsonl';
  fetch(url).then(function(r) {
    if (!r.ok) throw new Error('Not found: ' + url);
    return r.text();
  }).then(function(text) {
    var blob = new Blob([text], {type: 'application/json'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = docLang + '-' + genre + '-' + docName + '.jsonl';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }).catch(function(e) { console.warn('JSON download unavailable:', e); });
}

function downloadAnnotationsTSV() {
  var rows = ['sentence_id\tconcept_id\tconcept_lemma\tsynset\tword_ids\twords'];

  var keys = Object.keys(conceptInfo).sort(function(a, b) {
    var pa = a.replace('c', '').split(':').map(Number);
    var pb = b.replace('c', '').split(':').map(Number);
    return pa[0] - pb[0] || pa[1] - pb[1];
  });

  keys.forEach(function(key) {
    var parts = key.replace('c', '').split(':');
    var sid = parts[0], cid = parts[1];
    var info = conceptInfo[key];
    var wordTexts = info.w.map(function(wid) {
      var el = document.getElementById('w' + sid + ':' + wid);
      return el ? el.textContent : '';
    });
    rows.push([
      sid, cid, info.l || '', info.s || '',
      info.w.join(','), wordTexts.join(' ')
    ].join('\t'));
  });

  var blob = new Blob([rows.join('\n')], { type: 'text/tab-separated-values;charset=utf-8' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = (document.title || 'annotations').replace(/[^a-zA-Z0-9._-]/g, '_') + '.tsv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// =========================================================================
// Annotation statistics panel
// =========================================================================

function buildStatsPanel() {
  var stats = (typeof docStats !== 'undefined') ? docStats : null;
  if (!stats || !stats.sents) return false;

  var taggable = stats.tagged + stats.w + stats.e + stats['null'];
  var total = taggable + stats.x;
  var pct = taggable > 0 ? (stats.tagged / taggable * 100).toFixed(1) : '—';

  var panel = document.createElement('div');
  panel.id = 'statsPanel';
  panel.className = 'stats-panel';
  panel.innerHTML =
    '<table class="table table-sm mb-0">' +
    '<thead><tr><th>Measure</th><th class="text-end">Count</th></tr></thead>' +
    '<tbody>' +
    '<tr><td>Sentences</td><td class="text-end">' + stats.sents.toLocaleString() + '</td></tr>' +
    '<tr><td>Words (tokens)</td><td class="text-end">' + stats.words.toLocaleString() + '</td></tr>' +
    '<tr class="table-group-divider"><td>Tagged concepts</td><td class="text-end">' + stats.tagged.toLocaleString() + '</td></tr>' +
    '<tr><td><code>w</code> — function word</td><td class="text-end">' + stats.w.toLocaleString() + '</td></tr>' +
    '<tr><td><code>e</code> — error</td><td class="text-end">' + stats.e.toLocaleString() + '</td></tr>' +
    '<tr><td><code>x</code> — not taggable</td><td class="text-end">' + stats.x.toLocaleString() + '</td></tr>' +
    '<tr><td>Untagged (null)</td><td class="text-end">' + stats['null'].toLocaleString() + '</td></tr>' +
    '<tr class="table-group-divider"><td>Total concepts</td><td class="text-end">' + total.toLocaleString() + '</td></tr>' +
    '<tr><td>Tagging rate</td><td class="text-end"><strong>' + pct + '%</strong></td></tr>' +
    '</tbody></table>';

  var storyCard = story.closest('.card');
  if (storyCard) storyCard.parentNode.insertBefore(panel, storyCard);
  return true;
}

function toggleStats() {
  var panel = document.getElementById('statsPanel');
  if (!panel) return;
  panel.classList.toggle('visible');
  var btn = document.getElementById('toggleStats');
  if (btn) btn.classList.toggle('active', panel.classList.contains('visible'));
}

// =========================================================================
// Utility
// =========================================================================

function escapeHTML(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// =========================================================================
// Init
// =========================================================================

function init() {
  loadSettings();
  showWordIdToggle.checked = settings.showWordId;

  // Inject toolbar and progress bar
  injectUI();

  // Wire word events
  story.querySelectorAll('w').forEach(function(el) {
    el.addEventListener('mouseover',  handleMouseOver);
    el.addEventListener('mouseout',   handleMouseOut);
    el.addEventListener('mousemove',  handleMouseMove);
    el.addEventListener('click',      handleClick);
  });

  // Wire translation icons
  story.querySelectorAll('.trans-icon').forEach(function(el) {
    el.addEventListener('click', handleTransClick);
  });

  // Click-away
  document.addEventListener('click', function(e) {
    if (activeTransPopover && !activeTransPopover.contains(e.target)
        && !e.target.classList.contains('trans-icon')) {
      closeTransPopover();
    }
  });

  copyBtn.addEventListener('click',      copyTooltipContent);
  closeBtn.addEventListener('click',     closeTooltip);
  saveSettingsBtn.addEventListener('click', saveSettings);

  // ---- Toolbar wiring ----
  var searchInput = document.getElementById('searchInput');
  if (searchInput) {
    var debounce = null;
    searchInput.addEventListener('input', function() {
      clearTimeout(debounce);
      debounce = setTimeout(function() { performSearch(searchInput.value); }, 200);
    });
    searchInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (e.shiftKey) prevSearchMatch(); else nextSearchMatch();
      }
      if (e.key === 'Escape') { searchInput.value = ''; clearSearch(); searchInput.blur(); }
    });
  }

  var sentNumBtn = document.getElementById('toggleSentNums');
  if (sentNumBtn) sentNumBtn.addEventListener('click', toggleSentenceNumbers);

  var inlineTransBtn = document.getElementById('toggleInlineTrans');
  if (inlineTransBtn) inlineTransBtn.addEventListener('click', toggleInlineTranslations);

  var sentimentBtn = document.getElementById('toggleSentiment');
  if (sentimentBtn) {
    var hasSentimentData = Object.values(conceptInfo).some(function(c) {
      return c.v !== undefined;
    });
    if (hasSentimentData) {
      sentimentBtn.addEventListener('click', toggleSentiment);
    } else {
      sentimentBtn.style.display = 'none';
    }
  }

  var tocBtn = document.getElementById('tocToggle');
  var hasTOC = buildTOC();
  if (tocBtn) {
    if (hasTOC) {
      tocBtn.addEventListener('click', toggleTOC);
    } else {
      tocBtn.style.display = 'none';
    }
  }

  var statsBtn = document.getElementById('toggleStats');
  var hasStats = buildStatsPanel();
  if (statsBtn) {
    if (hasStats) {
      statsBtn.addEventListener('click', toggleStats);
    } else {
      statsBtn.style.display = 'none';
    }
  }

  var dlBtn = document.getElementById('downloadTsv');
  if (dlBtn) dlBtn.addEventListener('click', downloadAnnotationsTSV);

  var dlJsonBtn = document.getElementById('downloadJson');
  if (dlJsonBtn) dlJsonBtn.addEventListener('click', downloadAnnotationsJSON);

  // Reading progress
  window.addEventListener('scroll', updateReadingProgress, { passive: true });
  updateReadingProgress();

  // Keyboard shortcuts
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { closeTooltip(); closeTransPopover(); }
    if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
      var si = document.getElementById('searchInput');
      if (si) { e.preventDefault(); si.focus(); si.select(); }
    }
  });

  // Apply saved sentence numbers
  if (settings.showSentNums) {
    document.body.classList.add('show-sent-nums');
    if (sentNumBtn) sentNumBtn.classList.add('active');
    createSentenceNumbers();
  }

  // Apply saved sentiment state
  if (settings.showSentiment) {
    if (sentimentBtn) sentimentBtn.classList.add('active');
    applySentimentUnderlines();
  }

  // Load manifest then language data
  loadManifest().then(function() {
    return applyLanguageSettings();
  }).then(function() {
    if (settings.showInlineTrans && settings.transLang) {
      if (inlineTransBtn) inlineTransBtn.classList.add('active');
      updateInlineTranslations();
    }
  });
}

init();
