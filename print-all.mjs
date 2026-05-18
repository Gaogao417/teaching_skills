import puppeteer from 'puppeteer';
import { glob } from 'glob';
import { dirname, basename, join } from 'path';

const htmlFiles = await glob('artifacts/**/0[23]*.html');
console.log(`Found ${htmlFiles.length} HTML files to print`);

const browser = await puppeteer.launch({
  headless: true,
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
});

for (const file of htmlFiles) {
  const dir = dirname(file);
  const pdfName = basename(file, '.html') + '.pdf';
  const pdfPath = join(dir, pdfName);
  console.log(`Printing: ${file} -> ${pdfPath}`);

  const page = await browser.newPage();
  await page.goto(`file://${new URL(file, import.meta.url).pathname}`, {
    waitUntil: 'networkidle0',
  });
  await page.pdf({
    path: pdfPath,
    format: 'A4',
    printBackground: true,
    margin: { top: '10mm', bottom: '10mm', left: '10mm', right: '10mm' },
  });
  await page.close();
}

await browser.close();
console.log('All done.');
