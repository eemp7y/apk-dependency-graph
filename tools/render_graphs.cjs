/* Render the generated local artifact pages in an isolated headless browser. */
const fs = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function render(page, folder) {
  await page.goto(pathToFileURL(path.join(folder, 'graph.html')).href);
  await page.waitForFunction(() => document.documentElement.dataset.rendered,
    null, { timeout: 60000 });
  const error = await page.locator('html').getAttribute('data-rendered');
  if (error !== 'true') throw new Error(await page.locator('#status').textContent());
  const expected = await page.locator('#graph-data').textContent().then(JSON.parse);
  const nodes = await page.locator('#diagram svg g.node').count();
  const edges = await page.locator('#diagram svg .edgePaths path').count();
  if (nodes !== expected.nodes || edges !== expected.edges) {
    throw new Error(`${folder}: topology mismatch ${nodes}/${edges}`);
  }
  const filledEdges = await page.locator('#diagram svg .edgePaths path').evaluateAll(
    paths => paths.some(element => getComputedStyle(element).fill !== 'none')
  );
  if (filledEdges) throw new Error('Diagram edges must not have a filled area');
  const svg = await page.locator('#diagram svg').evaluate(element => {
    const copy = element.cloneNode(true);
    copy.style.width = `${element.viewBox.baseVal.width}px`;
    copy.style.height = `${element.viewBox.baseVal.height}px`;
    return new XMLSerializer().serializeToString(copy);
  });
  await fs.writeFile(path.join(folder, 'graph.svg'), svg, 'utf8');
  await page.locator('#plus').click();
  await page.locator('#fit').click();
  const downloadEvent = page.waitForEvent('download');
  await page.locator('#download').click();
  const download = await downloadEvent;
  if (!(await download.suggestedFilename()).endsWith('.svg')) {
    throw new Error('SVG export did not produce an SVG file');
  }
  await page.locator('#viewport').evaluate(element => { element.style.maxHeight = 'none'; });
  await page.locator('main').screenshot({ path: path.join(folder, 'preview.png') });
  console.log(`${path.basename(folder)}: ${nodes} nodes, ${edges} edges; SVG and screenshot saved`);
}

async function main() {
  const root = path.resolve(process.argv[2] || 'generated/demos');
  const options = { headless: true };
  if (process.env.BROWSER_PATH) options.executablePath = process.env.BROWSER_PATH;
  else options.channel = 'chrome';
  const browser = await chromium.launch(options);
  try {
    const page = await browser.newPage({ viewport: { width: 1480, height: 1050 } });
    page.setDefaultTimeout(60000);
    for (const entry of await fs.readdir(root, { withFileTypes: true })) {
      if (entry.isDirectory()) await render(page, path.join(root, entry.name));
    }
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
