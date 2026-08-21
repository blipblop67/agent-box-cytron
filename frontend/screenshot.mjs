import { chromium } from 'playwright';
import fs from 'fs';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8822';
const OUT = '/home/claude/screenshots';
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

async function shot(name) {
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log('captured', name);
}

// 1. Login gate
await page.goto(BASE);
await page.waitForSelector('text=Enter the hub');
await shot('01-login-gate');

// 2. Log in as first user (becomes admin)
await page.fill('input[placeholder="e.g. Priya"]', 'Priya');
await page.click('text=Enter the hub');
await page.waitForSelector('text=New flow');
await page.waitForSelector('text=Start from a template');
await shot('02-flows-with-templates');

// 2b. Use a template directly
await page.click('text=Your first agent');
await page.waitForURL(/\/flows\/.+/);
await page.waitForSelector('.react-flow__node-llm');
await shot('02c-template-opened');
await page.goto(`${BASE}/flows`);
await page.waitForSelector('text=Start from a template');

// 3. Create a flow
await page.click('text=New flow');
await page.waitForSelector('text=Create flow');
await page.fill('input[placeholder="Support inbox summarizer"]', 'Handbook Q&A');
await page.fill('textarea', 'Answer questions using the team handbook');
await shot('03-new-flow-modal');
await page.click('button:has-text("Create flow")');
await page.waitForURL(/\/flows\/.+/);
await page.waitForSelector('text=Nodes');
await shot('04-flow-editor-empty');

// 4. Build a small flow by clicking palette items
await page.click('div[draggable="true"]:has-text("Input")');
await page.click('div[draggable="true"]:has-text("Knowledge base")');
await page.click('div[draggable="true"]:has-text("LLM")');
await page.click('div[draggable="true"]:has-text("Telegram")');
await page.click('div[draggable="true"]:has-text("Output")');
await page.waitForTimeout(300);
await shot('05-flow-editor-nodes-added');

// 4b. Telegram node config panel
await page.click('.react-flow__node-telegram');
await page.waitForSelector('text=Connect Telegram');
await shot('05b-flow-editor-telegram-config');

// 5. Click the LLM node to open the config panel
await page.click('.react-flow__node-llm');
await page.waitForSelector('text=System prompt');
await shot('06-flow-editor-config-panel');

// 6. Fill LLM config a bit
await page.fill('textarea[placeholder="You are a helpful assistant that..."]', 'Answer using only the provided context. Be concise.');
await shot('07-flow-editor-llm-configured');

// 7. Open run panel
await page.click('text=Run this flow');
await page.waitForTimeout(300);
await shot('08-flow-editor-run-panel');

// 7b. Actually run it (KB node has no KB selected yet, so this exercises the
// error-trace rendering path, not just the happy path)
await page.fill('textarea[placeholder="Type what the Input node should receive…"]', 'What is the stipend policy?');
await page.click('button:has-text("Run")');
await page.waitForSelector('text=Final output, text=has no knowledge base selected', { timeout: 15000 }).catch(() => {});
await page.waitForTimeout(800);
await shot('08b-flow-editor-run-result');

// 8c. Schedule modal
await page.click('text=Schedule');
await page.waitForSelector('text=Schedule this flow');
await shot('08c-schedule-modal-empty');
await page.click('text=Add schedule');
await page.waitForSelector('text=Minutes between runs');
await page.fill('textarea[placeholder="e.g. Summarize today\'s unread emails"]', 'Check the shared inbox for anything urgent');
await shot('08d-schedule-modal-form');
await page.click('button:has-text("Create schedule")');
await page.waitForTimeout(500);
await shot('08e-schedule-modal-created');
await page.click('[aria-label="Close"]');

// 8. Knowledge bases page
await page.goto(`${BASE}/knowledge-bases`);
await page.waitForSelector('text=New knowledge base');
await shot('09-knowledge-bases-empty');

await page.click('text=New knowledge base');
await page.fill('input[placeholder="Team handbook"]', 'Team Handbook');
await page.click('button:has-text("Create")');
await page.waitForTimeout(500);
await shot('10-knowledge-base-detail');

// 9. Connections page
await page.goto(`${BASE}/connections`);
await page.waitForSelector('text=Connections');
await page.waitForSelector('text=@BotFather');
await shot('11-connections');

// 9b. Trying to connect Gmail before Google creds are configured
await page.locator('button:has-text("Connect")').first().click();
await page.waitForSelector('text=Go to Settings');
await shot('11b-connections-error-links-to-settings');

// 10. Team page
await page.goto(`${BASE}/team`);
await page.waitForSelector('text=Team');
await shot('12-team');

// 11. Settings page
await page.goto(`${BASE}/settings`);
await page.waitForSelector('text=Settings');
await page.waitForSelector('text=Google integration');
await shot('13-settings');

await browser.close();
console.log('done');
