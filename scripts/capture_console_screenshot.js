// -*- coding: utf-8 -*-
// 截取本地中控台页面，输出适合飞书日报的 16:9 PNG。
const path = require('path');
const puppeteer = require(path.join(__dirname, '..', 'node_modules', 'puppeteer'));

async function main() {
  const url = process.argv[2];
  const outputPath = process.argv[3];
  const tab = process.argv[4] || 'dashboard';
  if (!url || !outputPath) {
    throw new Error('用法：node scripts/capture_console_screenshot.js <url> <outputPath> [dashboard|dataprep]');
  }

  const browser = await puppeteer.launch({
    headless: 'new',
    defaultViewport: { width: 1600, height: 900, deviceScaleFactor: 1 },
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--font-render-hinting=none'],
  });
  try {
    const page = await browser.newPage();
    await page.emulateMediaType('print');
    await page.goto(url, { waitUntil: 'networkidle0', timeout: 60000 });
    await page.evaluate((targetTab) => {
      if (targetTab && targetTab !== 'dashboard') {
        const tabEl = document.querySelector(`.tab-item[data-tab="${targetTab}"]`);
        if (tabEl) tabEl.click();
      }
    }, tab);
    await page.waitForSelector('.app', { timeout: 30000 });
    await page.waitForFunction(() => {
      const loadingText = document.body.innerText || '';
      return !loadingText.includes('载入中…') && !loadingText.includes('加载中');
    }, { timeout: 30000 }).catch(() => {});
    await page.addStyleTag({
      content: `
        html, body { width: 1600px; min-height: 900px; background: #fff !important; }
        .app { width: 1600px; min-height: 900px; }
        .modal-mask, .drawer, .drawer-mask, .apps-pop, .skin-panel { display: none !important; }
      `,
    });
    await page.screenshot({ path: outputPath, type: 'png', fullPage: false });
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
