(() => {
  const byId = name => document.getElementById(`tasks-${name}`);
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  let state = {tasks: [], actions: [], show_upcoming_in_rail: false};
  let rows = [];
  let reviewed = [];
  let selectedDays = new Set();
  let editingId = null;
  let busy = false;
  byId('timezone-name').textContent = zone;

  async function api(path = '', options = {}) {
    const response = await fetch('/api/desktop/tasks' + path, options);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Task request failed.');
    return payload;
  }

  function status(message, error = false) {
    byId('status').textContent = message;
    byId('status').dataset.type = error ? 'error' : 'success';
  }

  function formatDue(value) {
    if (!value) return 'No future run';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'Invalid time' :
      new Intl.DateTimeFormat([], {dateStyle: 'medium', timeStyle: 'short'}).format(date);
  }

  function defaultSchedule() {
    const next = new Date(Date.now() + 60 * 60 * 1000);
    const pad = number => String(number).padStart(2, '0');
    byId('date').value = `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}`;
    byId('time').value = `${pad(next.getHours())}:${pad(next.getMinutes())}`;
  }

  function actionFor(id) { return state.actions.find(action => action.id === id); }

  function markDirty() {
    reviewed = [];
    byId('review').hidden = true;
    byId('save').disabled = true;
  }

  function renderPalette() {
    const palette = byId('palette');
    palette.replaceChildren();
    for (const action of state.actions) {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'tasks-palette-card';
      card.draggable = true;
      const name = document.createElement('strong');
      name.textContent = action.addon_name;
      const label = document.createElement('span');
      label.textContent = action.label;
      card.append(name, label);
      card.addEventListener('click', () => addStep(action.id));
      card.addEventListener('dragstart', event => event.dataTransfer.setData('application/x-petey-task-action', action.id));
      palette.append(card);
    }
  }

  function addStep(actionId, index = rows.length) {
    if (!actionFor(actionId)) return;
    rows.splice(index, 0, {action_id: actionId, instruction: ''});
    markDirty();
    renderSteps();
    byId('steps').querySelectorAll('textarea')[index]?.focus();
  }

  function moveStep(from, to) {
    if (from < 0 || from >= rows.length || to < 0 || to >= rows.length || from === to) return;
    rows.splice(to, 0, rows.splice(from, 1)[0]);
    markDirty();
    renderSteps();
  }

  function renderSteps() {
    const container = byId('steps');
    container.replaceChildren();
    if (!rows.length) {
      const empty = document.createElement('p');
      empty.className = 'tasks-drop-hint';
      empty.textContent = 'Drop an add-on here, or click one on the left.';
      container.append(empty);
      return;
    }
    rows.forEach((row, index) => {
      const action = actionFor(row.action_id);
      const item = document.createElement('div');
      item.className = 'tasks-step';
      item.addEventListener('dragover', event => event.preventDefault());
      item.addEventListener('drop', event => {
        event.preventDefault(); event.stopPropagation();
        const source = event.dataTransfer.getData('application/x-petey-task-row');
        const actionId = event.dataTransfer.getData('application/x-petey-task-action');
        if (source !== '') moveStep(Number(source), index);
        else if (actionId) addStep(actionId, index);
      });
      const top = document.createElement('div');
      top.className = 'tasks-step-top';
      const grip = document.createElement('button');
      grip.type = 'button'; grip.className = 'tasks-step-grip'; grip.draggable = true;
      grip.textContent = '⠿'; grip.title = 'Drag to reorder'; grip.setAttribute('aria-label', `Drag step ${index + 1}`);
      grip.addEventListener('dragstart', event => event.dataTransfer.setData('application/x-petey-task-row', String(index)));
      const heading = document.createElement('strong');
      heading.textContent = `${index + 1}. ${action?.addon_name || 'Unavailable add-on'} · ${action?.label || row.action_id}`;
      const controls = document.createElement('div');
      controls.className = 'tasks-step-controls';
      const control = (label, handler, disabled = false) => {
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = label; button.disabled = disabled;
        button.addEventListener('click', handler); controls.append(button);
      };
      control('↑', () => moveStep(index, index - 1), index === 0);
      control('↓', () => moveStep(index, index + 1), index === rows.length - 1);
      control('Remove', () => { rows.splice(index, 1); markDirty(); renderSteps(); });
      top.append(grip, heading, controls);
      const field = document.createElement('textarea');
      field.rows = 2; field.maxLength = 500;
      field.placeholder = row.action_id.startsWith('home-assistant.') ? 'Turn on outside light' :
        row.action_id.startsWith('spotify.') ? 'Play Here Comes the Sun by The Beatles' :
        row.action_id.startsWith('petey-webcam.') ? 'Shedfeed' : 'What should PETEY remind you about?';
      field.setAttribute('aria-label', `Instruction for step ${index + 1}`);
      field.value = row.instruction || '';
      field.addEventListener('input', () => { row.instruction = field.value; markDirty(); });
      item.append(top, field);
      container.append(item);
    });
  }

  byId('steps').addEventListener('dragover', event => event.preventDefault());
  byId('steps').addEventListener('drop', event => {
    event.preventDefault();
    const actionId = event.dataTransfer.getData('application/x-petey-task-action');
    if (actionId) addStep(actionId);
  });

  function renderDays() {
    byId('weekdays').hidden = byId('repeat').value !== 'selected_days';
    document.querySelectorAll('[data-task-weekday]').forEach(button => {
      button.setAttribute('aria-pressed', String(selectedDays.has(Number(button.dataset.taskWeekday))));
    });
  }
  document.querySelectorAll('[data-task-weekday]').forEach(button => button.addEventListener('click', () => {
    const day = Number(button.dataset.taskWeekday);
    if (selectedDays.has(day)) selectedDays.delete(day); else selectedDays.add(day);
    renderDays(); markDirty();
  }));
  for (const name of ['name', 'date', 'time', 'repeat', 'enabled']) {
    byId(name).addEventListener('change', () => { renderDays(); markDirty(); });
  }
  byId('name').addEventListener('input', markDirty);

  function formPayload() {
    return {
      title: byId('name').value.trim(), start_date: byId('date').value,
      time: byId('time').value, recurrence: byId('repeat').value,
      selected_days: [...selectedDays].sort(), timezone: zone,
      enabled: byId('enabled').checked,
    };
  }

  function renderReview(nextRuns = []) {
    const review = byId('review');
    const list = byId('review-steps');
    list.replaceChildren();
    reviewed.forEach((step, index) => {
      const item = document.createElement('div');
      item.className = 'tasks-reviewed-step';
      const title = document.createElement('strong');
      title.textContent = `${index + 1}. ${actionFor(step.action_id)?.addon_name || step.action_id}`;
      const summary = document.createElement('span');
      summary.textContent = step.summary;
      item.append(title, summary);
      if (step.options?.length > 1) {
        const label = document.createElement('label');
        label.textContent = 'Choose the exact track';
        const select = document.createElement('select');
        step.options.forEach((option, optionIndex) => select.add(new Option(option.label, String(optionIndex))));
        select.addEventListener('change', () => {
          const option = step.options[Number(select.value)];
          step.arguments = option.arguments;
          step.summary = option.label;
          summary.textContent = step.summary;
        });
        label.append(select); item.append(label);
      }
      list.append(item);
    });
    byId('next-runs').textContent = nextRuns.length ?
      `Next runs: ${nextRuns.map(formatDue).join(' · ')}` : 'No future run.';
    review.hidden = false;
    byId('save').disabled = false;
  }

  byId('preview').addEventListener('click', async () => {
    if (busy) return;
    if (!byId('form').reportValidity()) return;
    if (!rows.length) { status('Add at least one add-on step.', true); return; }
    if (byId('repeat').value === 'selected_days' && !selectedDays.size) {
      status('Choose at least one day of the week.', true); return;
    }
    busy = true;
    markDirty();
    try {
      const result = await api('/preview', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({...formPayload(), steps: rows})});
      reviewed = result.steps;
      renderReview(result.next_runs);
      status('Review each resolved action and its next run dates, then save.');
    } catch (error) { status(error.message, true); }
    finally { busy = false; }
  });

  function resetForm() {
    editingId = null; rows = []; reviewed = []; selectedDays = new Set();
    byId('form').reset(); byId('form-title').textContent = 'New task';
    byId('cancel').hidden = true; byId('enabled').checked = true;
    byId('repeat').value = 'once'; defaultSchedule();
    renderDays(); renderSteps(); markDirty();
  }
  byId('cancel').addEventListener('click', resetForm);

  byId('form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !reviewed.length) { status('Review the actions before saving.', true); return; }
    busy = true;
    const steps = reviewed.map(({action_id, arguments: args, summary, instruction}) =>
      ({action_id, arguments: args, summary, instruction}));
    try {
      await api(editingId ? `/${editingId}` : '', {method: editingId ? 'PUT' : 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...formPayload(), steps})});
      await refresh(); resetForm(); status('Task saved.');
    } catch (error) { status(error.message, true); }
    finally { busy = false; }
  });

  function renderRail() {
    const upcoming = state.tasks.filter(task => task.enabled && task.next_run_at);
    byId('rail-count').textContent = String(upcoming.length);
    const container = byId('upcoming');
    container.hidden = !state.show_upcoming_in_rail;
    container.replaceChildren();
    if (!state.show_upcoming_in_rail) return;
    if (!upcoming.length) {
      const empty = document.createElement('p'); empty.className = 'command-empty';
      empty.textContent = 'No upcoming tasks.'; container.append(empty); return;
    }
    for (const task of upcoming.slice(0, 3)) {
      const item = document.createElement('div'); item.className = 'tasks-upcoming-item';
      const title = document.createElement('strong'); title.textContent = task.title;
      const due = document.createElement('span'); due.textContent = formatDue(task.next_run_at);
      item.append(title, due); container.append(item);
    }
  }

  function editTask(task) {
    const steps = task.steps || [{action_id: task.action_id, arguments: task.arguments, summary: task.title}];
    if (steps.some(step => !actionFor(step.action_id))) {
      status('Enable this task’s add-on before editing its actions.', true); return;
    }
    if (task.timezone !== zone) status(`This task uses ${task.timezone}. Saving here moves it to ${zone}.`);
    editingId = task.id;
    byId('form-title').textContent = 'Edit task'; byId('cancel').hidden = false;
    byId('name').value = task.title; byId('date').value = task.start_date;
    byId('time').value = task.time;
    byId('repeat').value = task.recurrence === 'weekly' ? 'selected_days' : task.recurrence;
    selectedDays = new Set(task.recurrence === 'weekly' ?
      [new Date(`${task.start_date}T12:00:00`).getDay()] : (task.selected_days || []));
    byId('enabled').checked = task.enabled;
    rows = [];
    let collapsedLegacyArea = false;
    for (const step of steps) {
      const instruction = step.instruction || Object.values(step.arguments || {})[0] || step.summary || '';
      let legacyNamedLight = false;
      if (step.action_id === 'home-assistant.light' && /\blights\s*$/i.test(instruction)) {
        try { legacyNamedLight = !!JSON.parse(step.arguments?.payload_json || '{}').name; }
        catch (_) { /* An invalid saved action still needs a fresh review. */ }
      }
      if (legacyNamedLight && rows.at(-1)?.action_id === step.action_id &&
          rows.at(-1)?.instruction === instruction) {
        collapsedLegacyArea = true;
        continue;
      }
      rows.push({action_id: step.action_id, instruction});
    }
    renderDays(); renderSteps(); markDirty();
    if (collapsedLegacyArea) status('This older room-light task was expanded into separate lights. Review again to use one area action.');
    byId('form').scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  async function mutate(path, options, success) {
    if (busy) return;
    busy = true;
    try {
      const result = await api(path, options);
      await refresh(); status(path.endsWith('/run') ? result.status : success);
    } catch (error) { status(error.message, true); }
    finally { busy = false; }
  }

  function renderList() {
    const list = byId('list'); list.replaceChildren();
    if (!state.tasks.length) {
      const empty = document.createElement('p'); empty.className = 'muted';
      empty.textContent = 'No tasks yet. Add an add-on above to get started.';
      list.append(empty); return;
    }
    for (const task of state.tasks) {
      const row = document.createElement('article'); row.className = 'tasks-row';
      const heading = document.createElement('div'); heading.className = 'tasks-row-heading';
      const title = document.createElement('strong'); title.textContent = task.title;
      const stateText = document.createElement('span');
      stateText.textContent = task.enabled ? task.next_run_at ? 'Scheduled' : 'Finished' : 'Paused';
      heading.append(title, stateText);
      const steps = task.steps || [{action_id: task.action_id}];
      const meta = document.createElement('div'); meta.className = 'tasks-row-meta';
      meta.textContent = `${steps.length} step${steps.length === 1 ? '' : 's'} · ${formatDue(task.next_run_at)} · ${task.recurrence === 'selected_days' ? (task.selected_days || []).map(day => ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][day]).join(', ') : task.recurrence}`;
      const result = document.createElement('div'); result.className = 'tasks-row-meta';
      result.textContent = task.last_status || 'Waiting for first run';
      const actions = document.createElement('div'); actions.className = 'tasks-row-actions';
      const button = (label, handler, className = '') => {
        const item = document.createElement('button'); item.type = 'button';
        item.textContent = label; item.className = className;
        item.addEventListener('click', handler); actions.append(item);
      };
      button('Edit', () => editTask(task));
      button('Run now', () => mutate(`/${task.id}/run`, {method: 'POST'}, 'Task action ran.'));
      if (task.next_run_at) button(task.enabled ? 'Pause' : 'Resume', () => mutate(
        `/${task.id}`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({...task, enabled: !task.enabled})},
        task.enabled ? 'Task paused.' : 'Task resumed.'));
      button('Delete', () => {
        if (window.confirm(`Delete task “${task.title}”?`)) mutate(`/${task.id}`, {method: 'DELETE'}, 'Task deleted.');
      }, 'tasks-delete');
      row.append(heading, meta, result, actions); list.append(row);
    }
  }

  function render() {
    renderPalette(); renderList(); renderRail();
    byId('show-upcoming').checked = state.show_upcoming_in_rail;
  }
  async function refresh() { state = await api(); render(); }
  byId('show-upcoming').addEventListener('change', async event => {
    try {
      state = await api('/settings', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({show_upcoming_in_rail: event.target.checked})}); render();
    } catch (error) { event.target.checked = !event.target.checked; status(error.message, true); }
  });
  refresh().then(resetForm).catch(error => status(error.message, true));
  window.addEventListener('petey:view', event => {
    if (event.detail.view === 'tasks') refresh().catch(error => status(error.message, true));
  });
  window.setInterval(() => { if (!document.hidden) refresh().catch(() => {}); }, 30000);
})();
