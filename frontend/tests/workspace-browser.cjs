const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  // UI tests never contact social platforms or publish anything.
  await context.route('**/*', (route) => route.request().url().startsWith('http://127.0.0.1:3000') ? route.continue() : route.abort());
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('http://127.0.0.1:3000', { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Bagikan produk. Lebih simpel.' }).waitFor();
  assert.equal(await page.getByRole('checkbox').count(), 3);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await fs.mkdir('qa', { recursive: true });
  await page.screenshot({ path: 'qa/desktop.jpg', fullPage: true, type: 'jpeg', quality: 65 });
  const link = 'https://example.com/product?affiliate_id=demo%2F123&campaign=launch';
  await page.getByLabel('Link produk affiliate').fill(link);
  await page.getByLabel('Nama produk').fill('Produk uji');
  await page.getByRole('button', { name: 'Simpan draft' }).click();
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await page.getByLabel('Link produk affiliate').inputValue(), link);
  await page.getByRole('button', { name: 'Siapkan tautan berbagi' }).click();
  const xLink = page.getByRole('link', { name: /Buka X/ });
  assert.equal(new URL(await xLink.getAttribute('href')).searchParams.get('url'), link);
  assert.equal(new URL(await page.getByRole('link', { name: /Buka Facebook Pro/ }).getAttribute('href')).searchParams.get('u'), link);
  const popup = context.waitForEvent('page');
  await xLink.click();
  await (await popup).close();
  assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('affiliate-workspace:history:v1'))[0].platform), 'x');
  await page.goto('http://127.0.0.1:3000/share-history', { waitUntil: 'networkidle' });
  await page.getByText('Produk uji', { exact: true }).waitFor();
  await page.getByText('Tautan dibuka', { exact: true }).waitFor();
  await page.goto('http://127.0.0.1:3000/channels', { waitUntil: 'networkidle' });
  assert.equal(await page.getByText('Mode berbagi manual', { exact: true }).count(), 3);
  await page.goto('http://127.0.0.1:3000', { waitUntil: 'networkidle' });
  await page.evaluate(() => localStorage.clear());
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.getByRole('button', { name: 'Buka menu' }).click();
  assert.equal(await page.getByRole('button', { name: 'Tutup menu' }).getAttribute('aria-expanded'), 'true');
  await page.getByRole('navigation').getByRole('link', { name: 'Platform', exact: true }).click();
  await page.getByRole('heading', { name: 'Platform kamu' }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Buka menu' }).getAttribute('aria-expanded'), 'false');
  await page.goto('http://127.0.0.1:3000', { waitUntil: 'networkidle' });
  await page.screenshot({ path: 'qa/mobile.jpg', fullPage: true, type: 'jpeg', quality: 60 });
  assert.deepEqual(errors, []);
  console.log('UI_TESTS_PASSED: desktop/mobile layout, draft persistence, affiliate encoding, share handoff, history, channels, mobile navigation; no external posts.');
  // Export preview bytes through the read-only CI log connector.
  for (const name of ['desktop', 'mobile']) {
    console.log(`PREVIEW_${name.toUpperCase()}_BEGIN`);
    const image = (await fs.readFile(`qa/${name}.jpg`)).toString('base64');
    for (let i = 0; i < image.length; i += 8000) console.log('PREVIEW_DATA:' + image.slice(i, i + 8000));
    console.log(`PREVIEW_${name.toUpperCase()}_END`);
  }
  await browser.close();
})().catch((error) => { console.error(error); process.exit(1); });
