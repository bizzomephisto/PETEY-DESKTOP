/* Shared settings navigation. Pages and section IDs come from the rendered catalog. */
function openSetting(view, targetId) {
    const target = targetId ? document.getElementById(targetId) : null;
    // Preserve old links when a section moves to a different settings category.
    const owner = target?.closest('.settings-view');
    showView(owner ? owner.id.replace('view-', '') : view);
    if (!target) {
        document.querySelector('.settings-view.active-view h1')?.focus({preventScroll: true});
        return;
    }
    for (let parent = target; parent; parent = parent.parentElement) {
        if (parent.tagName === 'DETAILS') parent.open = true;
    }
    target.scrollIntoView({block: 'start', behavior: 'auto'});
    const focusTarget = target.querySelector('summary, h2, input, select, button');
    if (focusTarget) {
        if (focusTarget.tagName === 'H2') focusTarget.tabIndex = -1;
        focusTarget.focus({preventScroll: true});
    }
}

(() => {
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-settings-view]');
        if (button) openSetting(button.dataset.settingsView, button.dataset.settingsTarget);
    });

    window.addEventListener('petey:view', event => {
        const page = document.getElementById(`view-${event.detail.view}`);
        const list = page?.querySelector('.settings-category-list');
        const active = list?.querySelector('[aria-current="page"]');
        if (active && list.scrollWidth > list.clientWidth) {
            list.scrollLeft += active.getBoundingClientRect().left - list.getBoundingClientRect().left - 8;
        }
    });

    const entries = [];
    for (const page of document.querySelectorAll('.settings-view')) {
        const view = page.id.replace('view-', '');
        const category = page.dataset.settingsTitle;
        const links = page.querySelector('.settings-section-links');
        for (const card of page.querySelectorAll('.settings-card[id]')) {
            const title = card.querySelector('h2')?.textContent.trim();
            if (!title) continue;
            // Do not index input values, dynamic statuses, credentials, or user content.
            const labels = [...card.querySelectorAll('h2, label > span, summary p')].map(label => label.textContent);
            entries.push({id: card.id, view, title, category,
                keywords: [category, card.dataset.settingsKeywords || '', ...labels].join(' ').toLowerCase()});
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = title;
            button.dataset.settingsView = view;
            button.dataset.settingsTarget = card.id;
            links.append(button);
        }
        links.hidden = links.childElementCount < 2;
    }

    for (const input of document.querySelectorAll('[data-settings-search]')) {
        const results = input.closest('nav').querySelector('.settings-search-results');
        results.id = `${input.closest('.settings-view').id}-search-results`;
        input.setAttribute('aria-controls', results.id);
        const clear = () => { input.value = ''; results.replaceChildren(); results.hidden = true; };
        input.addEventListener('input', () => {
            const words = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
            results.replaceChildren();
            results.hidden = !words.length;
            if (!words.length) return;
            const matches = entries.filter(entry => words.every(word => entry.keywords.includes(word)));
            const count = document.createElement('p');
            count.textContent = matches.length ? `${matches.length} matching sections` : 'No settings found. Try voice, model, theme, or memory.';
            results.append(count);
            for (const entry of matches) {
                const button = document.createElement('button');
                button.type = 'button';
                const title = document.createElement('strong'); title.textContent = entry.title;
                const category = document.createElement('small'); category.textContent = entry.category;
                button.append(title, category);
                button.addEventListener('click', () => { clear(); openSetting(entry.view, entry.id); });
                results.append(button);
            }
        });
        input.addEventListener('keydown', event => {
            if (event.key === 'Escape') clear();
            if (event.key === 'Enter') { event.preventDefault(); results.querySelector('button')?.click(); }
            if (event.key === 'ArrowDown' && !results.hidden) { event.preventDefault(); results.querySelector('button')?.focus(); }
        });
        results.addEventListener('keydown', event => {
            if (event.key === 'Escape') { clear(); input.focus(); }
        });
    }
})();
