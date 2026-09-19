(() => {
  'use strict';
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const panels = [...document.querySelectorAll('[role="tabpanel"]')];
  const search = document.querySelector('#search');
  const status = document.querySelector('#status');
  const cards = [...document.querySelectorAll('.question')];
  const indexed = cards.map(card => ({card, text: card.textContent.toLocaleLowerCase()}));
  let active = tabs[0].dataset.family;
  let counts = {};

  function activate(family) {
    active = family;
    tabs.forEach(tab => {
      const selected = tab.dataset.family === family;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    panels.forEach(panel => { panel.hidden = panel.dataset.family !== family; });
    updateStatus();
  }

  function updateStatus() {
    const matching = Object.values(counts).reduce((a, b) => a + b, 0);
    const current = counts[active] || 0;
    status.textContent = search.value.trim()
      ? `${current} ${current === 1 ? 'match' : 'matches'} in ${active} · ${matching} across all families`
      : `${current} ${current === 1 ? 'question' : 'questions'} in this family · ${cards.length} in the pack`;
    document.querySelector('#empty').hidden = (counts[active] || 0) !== 0;
  }

  function filter() {
    const query = search.value.trim().toLocaleLowerCase();
    const exact = cards.find(card => card.dataset.caseId.toLocaleLowerCase() === query);
    counts = Object.fromEntries(tabs.map(tab => [tab.dataset.family, 0]));
    indexed.forEach(({card, text}) => {
      const match = !query || (exact ? card === exact : text.includes(query));
      card.hidden = !match;
      if (match) counts[card.dataset.family]++;
    });
    tabs.forEach(tab => { tab.querySelector('.count').textContent = counts[tab.dataset.family]; });
    if (!counts[active]) {
      const first = tabs.find(tab => counts[tab.dataset.family]);
      if (first) activate(first.dataset.family);
    }
    updateStatus();
  }

  function followHash() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const target = document.getElementById(id) || cards.find(card => card.dataset.caseId === id);
    if (!target) return;
    if (target.classList.contains('question')) {
      search.value = '';
      filter();
      activate(target.dataset.family);
      requestAnimationFrame(() => target.scrollIntoView({block: 'start'}));
    } else if (target.getAttribute('role') === 'tabpanel') {
      activate(target.dataset.family);
    }
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => {
      activate(tab.dataset.family);
      history.replaceState(null, '', `#family-${active}`);
      window.scrollTo({top: 0});
    });
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else return;
      event.preventDefault();
      tabs[next].click(); tabs[next].focus();
    });
  });
  search.addEventListener('input', filter);
  search.addEventListener('keydown', event => {
    if (event.key === 'Escape') { search.value = ''; filter(); }
  });
  window.addEventListener('hashchange', followHash);
  filter(); activate(active); followHash();
})();
