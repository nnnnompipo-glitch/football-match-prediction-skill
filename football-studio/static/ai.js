function loadStyles() {
  if (document.querySelector('link[data-ai-styles]')) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.dataset.aiStyles = '';
  link.href = new URL('./ai.css', import.meta.url).href;
  document.head.append(link);
}

async function api(action, body) {
  let response;
  try {
    response = await fetch(`/api/ai/${action}`, body === undefined ? { cache: 'no-store' } : {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error('无法连接本机应用，请确认服务已启动。');
  }
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error(`本机服务返回了无效响应（HTTP ${response.status}）。`);
  }
  if (!response.ok || result.error) throw new Error(result.error || `请求未完成（HTTP ${response.status}）。`);
  return result;
}

function showStatus(element, text, error = false) {
  element.textContent = text;
  element.classList.toggle('ai-error', error);
}

export async function renderSettings(container) {
  loadStyles();
  const region = document.createElement('section');
  region.className = 'ai-settings ai-card';
  region.innerHTML = `
    <header class="ai-card-head">
      <div><h2>大模型服务</h2><p>连接支持 Chat Completions 的服务，用于解读研究结果。</p></div>
    </header>
    <form class="ai-form">
      <fieldset disabled>
        <label class="ai-field"><span>服务地址 <small>Base URL</small></span>
          <input type="url" required name="base_url" autocomplete="off" spellcheck="false" placeholder="https://api.openai.com/v1" />
        </label>
        <label class="ai-field"><span>模型 ID</span>
          <input type="text" required name="model" autocomplete="off" spellcheck="false" maxlength="256" placeholder="填写服务商提供的模型 ID" />
        </label>
        <label class="ai-field"><span>API 密钥 <small>API Key</small></span>
          <span class="ai-secret"><input type="password" name="api_key" autocomplete="new-password" spellcheck="false" maxlength="4096" placeholder="输入密钥" />
            <button type="button" data-action="reveal" aria-label="显示密钥" aria-pressed="false">显示</button></span>
        </label>
        <div class="ai-key-tools"><label class="ai-check"><input type="checkbox" name="remember_key" />在此设备记住密钥</label>
          <button type="button" data-action="remove" hidden>移除已保存的密钥</button></div>
        <p class="ai-help" data-key-note></p>
        <div class="ai-actions"><button class="ai-primary" type="submit">保存设置</button>
          <button class="ai-secondary" type="button" data-action="test">测试连接</button></div>
      </fieldset>
      <p class="ai-status" role="status" aria-live="polite">正在读取设置…</p>
    </form>`;
  container.replaceChildren(region);
  const form = region.querySelector('form');
  const fields = form.elements;
  const fieldset = form.querySelector('fieldset');
  const status = form.querySelector('[role="status"]');
  const keyInput = fields.namedItem('api_key');
  const remember = fields.namedItem('remember_key');
  const remove = form.querySelector('[data-action="remove"]');
  const reveal = form.querySelector('[data-action="reveal"]');
  const test = form.querySelector('[data-action="test"]');
  let clearKey = false;

  function updateValues(config) {
    fields.namedItem('base_url').value = config.base_url;
    fields.namedItem('model').value = config.model;
    const hasKey = config.has_key;
    clearKey = false;
    keyInput.value = '';
    keyInput.type = 'password';
    reveal.textContent = '显示';
    reveal.setAttribute('aria-label', '显示密钥');
    reveal.setAttribute('aria-pressed', 'false');
    keyInput.placeholder = hasKey ? '已设置密钥，留空可继续使用' : '输入密钥';
    remove.hidden = !hasKey;
    remove.textContent = '移除已保存的密钥';
    remember.checked = config.remember_key;
    remember.closest('label').hidden = !config.can_remember;
    form.querySelector('[data-key-note]').textContent = config.can_remember
      ? '勾选后由 Windows 为当前用户加密保存。默认只保留到本机服务关闭。'
      : '密钥仅保留到本机服务关闭。服务地址和模型 ID 会保存在此设备。';
  }

  function values() {
    return {
      base_url: fields.namedItem('base_url').value.trim(), model: fields.namedItem('model').value.trim(),
      api_key: keyInput.value.trim(), remember_key: remember.checked, clear_key: clearKey,
    };
  }

  reveal.addEventListener('click', () => {
    const visible = keyInput.type === 'password';
    keyInput.type = visible ? 'text' : 'password';
    reveal.textContent = visible ? '隐藏' : '显示';
    reveal.setAttribute('aria-label', visible ? '隐藏密钥' : '显示密钥');
    reveal.setAttribute('aria-pressed', String(visible));
  });
  remove.addEventListener('click', () => {
    clearKey = !clearKey;
    keyInput.value = '';
    keyInput.placeholder = clearKey ? '保存设置后移除原密钥' : '已设置密钥，留空可继续使用';
    remove.textContent = clearKey ? '撤销移除' : '移除已保存的密钥';
    showStatus(status, clearKey ? '原密钥将在保存时移除。' : '');
  });
  async function submit(action) {
    if (!form.reportValidity()) return;
    const config = values();
    fieldset.disabled = true;
    showStatus(status, action === 'test' ? '正在请求模型…' : '正在保存…');
    try {
      const result = await api(action, config);
      if (action === 'test') {
        showStatus(status, `连接成功，${result.model} 已响应。`);
      } else {
        updateValues(result);
        showStatus(status, '设置已保存。');
        document.dispatchEvent(new CustomEvent('football-ai-settings-updated', { detail: result }));
      }
    } catch (err) {
      showStatus(status, err.message, true);
    } finally {
      fieldset.disabled = false;
    }
  }
  form.addEventListener('submit', event => { event.preventDefault(); submit('settings'); });
  test.addEventListener('click', () => submit('test'));
  try {
    updateValues(await api('settings'));
    showStatus(status, '');
    fieldset.disabled = false;
  } catch (err) {
    showStatus(status, err.message, true);
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'ai-secondary';
    retry.textContent = '重新读取';
    retry.onclick = () => renderSettings(container);
    status.after(retry);
  }
}

export function mountAnalysis(container, result, task = '赛前预测') {
  loadStyles();
  const section = document.createElement('section');
  section.className = 'ai-analysis ai-card';
  section.innerHTML = `
    <header class="ai-card-head"><div><h2>AI 解读</h2><p>生成时会将这份结果和你的问题发送至已配置的模型服务。</p></div></header>
    <form class="ai-form"><label class="ai-field"><span>想了解什么 <small>选填</small></span>
      <input type="text" name="question" maxlength="1500" placeholder="例如，哪项因素对这次预测影响最大？" /></label>
      <div class="ai-actions"><button type="submit" class="ai-primary">生成解读</button></div>
      <p class="ai-status" role="status" aria-live="polite"></p></form>
    <article class="ai-answer" hidden><h3>模型解读</h3><div></div></article>`;
  container.replaceChildren(section);
  const form = section.querySelector('form');
  const button = form.querySelector('button');
  const status = form.querySelector('[role="status"]');
  const answer = section.querySelector('.ai-answer');
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (button.disabled) return;
    button.disabled = true;
    section.setAttribute('aria-busy', 'true');
    showStatus(status, '模型正在解读本次结果…');
    try {
      const data = await api('analyze', { result, task, question: form.elements.namedItem('question').value.trim() });
      answer.querySelector('h3').textContent = `模型解读 · ${data.model}`;
      answer.querySelector('div').textContent = data.analysis;
      answer.hidden = false;
      button.textContent = '重新生成';
      showStatus(status, '解读已生成。');
    } catch (err) {
      showStatus(status, err.message, true);
      const settings = document.createElement('a');
      settings.href = '#settings';
      settings.textContent = '查看模型设置';
      status.append(' ', settings);
    } finally {
      section.removeAttribute('aria-busy');
      button.disabled = false;
    }
  });
}
