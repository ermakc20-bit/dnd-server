/* Bounded regression: phone draft transition and confirmed-offline room administration. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.VTT_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.VTT_E2E_URL || 'http://127.0.0.1:5189';
if (!['localhost', '127.0.0.1'].includes(new URL(base).hostname)) throw new Error('Only local synthetic acceptance is allowed');
const output = process.env.VTT_E2E_OUTPUT || '/private/tmp/dnd-t09-e2e';
const connected = page => page.getByText(/Последняя синхронизация:.*Связь установлена/).waitFor({ timeout: 15000 });
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.VTT_CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage(); const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base);
    await page.getByRole('button', { name: 'Создать кампанию', exact: true }).click();
    await page.getByLabel('Название кампании', { exact: true }).fill('Сохранить черновик перехода');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('status').filter({ hasText: 'Черновик кампании сохранён' }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Сохранить кампанию', exact: true }).count(), 0);
    assert.equal(await page.getByRole('textbox', { name: 'Название кампании', exact: true }).count(), 0);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.setViewportSize({ width: 1440, height: 900 });
    assert.equal(await page.getByLabel('Название кампании', { exact: true }).inputValue(), 'Сохранить черновик перехода');
    await page.getByRole('button', { name: 'Сохранить кампанию', exact: true }).click();
    await connected(page);
    await page.getByRole('button', { name: 'Участники', exact: true }).click();
    await page.getByRole('button', { name: 'Выпустить приглашение', exact: true }).click();
    const invitation = page.locator('output.invite-link'); await invitation.waitFor();
    const playerContext = await browser.newContext(); const player = await playerContext.newPage();
    await player.goto(await invitation.textContent());
    await player.getByLabel('Ваше имя', { exact: true }).fill('Игрок границы');
    await player.getByRole('button', { name: 'Войти в комнату', exact: true }).click();
    await connected(player);
    await page.getByRole('button', { name: 'Показать участников', exact: true }).click();
    await page.getByRole('button', { name: 'Удалить', exact: true }).waitFor();
    await page.getByLabel('PIN комнаты', { exact: true }).fill('1234');
    let durableRequests = 0;
    page.on('request', request => {
      if (['POST', 'PATCH', 'DELETE'].includes(request.method()) &&
          /\/api\/v1\/rooms\/[^/]+\/(invites|access|participants\/[^/]+)(?:\/|$)/.test(new URL(request.url()).pathname)) durableRequests++;
    });
    await context.setOffline(true);
    await page.getByRole('status').filter({ hasText: 'Только чтение · последнее подтверждённое состояние' }).waitFor();
    const actions = ['Выпустить приглашение', 'Перевыпустить', 'Отозвать', 'Сохранить PIN', 'Убрать PIN', 'Закрыть комнату', 'Удалить'];
    for (const name of actions) {
      const button = page.getByRole('button', { name, exact: true });
      assert.equal(await button.isDisabled(), true, name);
      await button.evaluate(element => element.click());
    }
    assert.equal(durableRequests, 0);
    assert.equal(await page.getByRole('button', { name: 'Показать участников', exact: true }).isEnabled(), true);
    assert.equal(await page.getByText(/^Игрок границы · игрок/).count(), 1);
    await context.setOffline(false); await connected(page);
    assert.equal(await page.getByLabel('PIN комнаты', { exact: true }).inputValue(), '1234');
    for (const name of actions) assert.equal(await page.getByRole('button', { name, exact: true }).isEnabled(), true, name);
    await page.getByRole('button', { name: 'Перевыпустить', exact: true }).click();
    await page.waitForTimeout(100);
    assert.equal(durableRequests, 1);
    assert.deepEqual(errors, []);
    fs.mkdirSync(output, { recursive: true });
    fs.writeFileSync(path.join(output, 'boundary-results.json'), JSON.stringify({ status: 'passed',
      phone_draft_transition: 'hidden/restored', offline_admin_actions_disabled: actions.length,
      offline_durable_requests: 0, resynced_online_write_requests: 1, page_errors: errors }, null, 2));
    console.log('T09 boundary browser PASS: phone draft hidden/restored; 7 offline writes disabled/0 requests; online resync write succeeds');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exit(1); });
